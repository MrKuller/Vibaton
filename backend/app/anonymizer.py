"""Model 1: blurs faces and car number plates; strips EXIF (GPS, phone model) by re-encoding.

Primary detector: your YOLO model for faces and licence plates (ultralytics), the same approach as
the team's test_anonymizer.py: boxes expanded by 25 %, pixelation + strong Gaussian blur, an oval
feathered mask for faces and a rectangle for plates.
    FACE_LP_MODEL_PATH=models/yolo26m_face_lp.pt   (default, relative to backend/)
    pip install -r requirements-ai.txt              (ultralytics + PyTorch)

Fallback when the model file or ultralytics is missing: OpenCV Haar cascades (weaker, CPU only).
The detector in use is reported in /health and stored with every photo.

No detector finds everything: a photo without detections is "NO_DETECTIONS", not "guaranteed anonymous".
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field

import cv2
import numpy as np

from . import config

log = logging.getLogger(__name__)

CONFIDENCE = 0.25
IOU_THRESHOLD = 0.5
PADDING = 0.25
PIXEL_SIZE = 20

_lock = threading.Lock()
_yolo = None            # loaded model, or False when unavailable
_yolo_error: str | None = None
_CASCADES: dict[str, cv2.CascadeClassifier] = {}


@dataclass
class Detection:
    kind: str  # face | plate
    confidence: float | None
    box: tuple[int, int, int, int]  # x1, y1, x2, y2 after padding


@dataclass
class AnonymizeResult:
    jpeg: bytes
    face_count: int
    plate_count: int
    width: int
    height: int
    detector: str  # yolo | haar
    detections: list[Detection] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "NO_DETECTIONS" if not self.detections else "PROCESSED_REQUIRES_REVIEW"


# ---------- detectors ----------
def object_type(class_name: str) -> str | None:
    name = str(class_name).lower().replace("_", "-").replace(" ", "-")
    if "face" in name:
        return "face"
    if "plate" in name or "license" in name or "licence" in name:
        return "plate"
    return None


def yolo_model():
    """Loads the YOLO model once; returns None when it cannot be used."""
    global _yolo, _yolo_error
    if _yolo is None:
        with _lock:
            if _yolo is None:
                path = config.FACE_LP_MODEL_PATH
                try:
                    if not path.exists():
                        raise FileNotFoundError(f"нет файла модели models/{path.name}")
                    from ultralytics import YOLO  # heavy import: only when the model exists
                    _yolo = YOLO(str(path))
                    log.info("face/plate model loaded: %s, classes %s", path, getattr(_yolo, "names", None))
                except Exception as e:  # missing package, broken file, wrong torch: fall back to Haar
                    _yolo, _yolo_error = False, str(e)
                    log.warning("YOLO face/plate model unavailable (%s), using Haar cascades", e)
    return _yolo or None


def detector_name() -> str:
    return "yolo" if yolo_model() else "haar"


def detector_error() -> str | None:
    yolo_model()
    return _yolo_error


def _pad(x1: int, y1: int, x2: int, y2: int, w: int, h: int) -> tuple[int, int, int, int]:
    px, py = int((x2 - x1) * PADDING), int((y2 - y1) * PADDING)
    return max(0, x1 - px), max(0, y1 - py), min(w, x2 + px), min(h, y2 + py)


def detect_yolo(model, img: np.ndarray) -> list[Detection]:
    h, w = img.shape[:2]
    result = model.predict(source=img, conf=CONFIDENCE, iou=IOU_THRESHOLD, verbose=False)[0]
    out: list[Detection] = []
    if result.boxes is None:
        return out
    for det in result.boxes:
        kind = object_type(model.names[int(det.cls[0])])
        if kind is None:
            continue
        x1, y1, x2, y2 = map(int, det.xyxy[0].tolist())
        out.append(Detection(kind, round(float(det.conf[0]), 3), _pad(x1, y1, x2, y2, w, h)))
    return out


def _cascade(name: str) -> cv2.CascadeClassifier:
    if name not in _CASCADES:
        c = cv2.CascadeClassifier(cv2.data.haarcascades + name)
        if c.empty():
            raise RuntimeError(f"OpenCV cascade {name} not found: install opencv-python-headless<5")
        _CASCADES[name] = c
    return _CASCADES[name]


def detect_haar(img: np.ndarray) -> list[Detection]:
    h, w = img.shape[:2]
    gray = cv2.equalizeHist(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    side = min(h, w)
    fmin = (max(24, side // 40),) * 2

    def run(g, cascade, min_size, nb):
        found = _cascade(cascade).detectMultiScale(g, scaleFactor=1.1, minNeighbors=nb, minSize=min_size)
        return [tuple(map(int, b)) for b in found] if len(found) else []

    faces = run(gray, "haarcascade_frontalface_default.xml", fmin, 5) + run(gray, "haarcascade_profileface.xml", fmin, 5)
    faces += [(w - x - fw, y, fw, fh) for x, y, fw, fh in run(cv2.flip(gray, 1), "haarcascade_profileface.xml", fmin, 5)]
    plates = run(gray, "haarcascade_russian_plate_number.xml", (max(40, side // 30), max(12, side // 100)), 4)
    return ([Detection("face", None, _pad(x, y, x + bw, y + bh, w, h)) for x, y, bw, bh in faces]
            + [Detection("plate", None, _pad(x, y, x + bw, y + bh, w, h)) for x, y, bw, bh in plates])


# ---------- blurring (as in test_anonymizer.py) ----------
def blur_region(image: np.ndarray, box: tuple[int, int, int, int], kind: str) -> None:
    x1, y1, x2, y2 = box
    crop = image[y1:y2, x1:x2].copy()
    if crop.size == 0:
        return
    h, w = crop.shape[:2]
    small = cv2.resize(crop, (max(1, w // PIXEL_SIZE), max(1, h // PIXEL_SIZE)), interpolation=cv2.INTER_LINEAR)
    blurred = cv2.GaussianBlur(cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST), (99, 99), 50)
    if kind == "face":
        mask = np.zeros((h, w), dtype=np.uint8)
        cv2.ellipse(mask, (w // 2, h // 2), (max(1, int(w * 0.48)), max(1, int(h * 0.48))), 0, 0, 360, 255, -1)
        feather = max(11, min(w, h) // 5) | 1  # odd kernel size
        alpha = (cv2.GaussianBlur(mask, (feather, feather), 0).astype(np.float32) / 255.0)[:, :, None]
        image[y1:y2, x1:x2] = (crop.astype(np.float32) * (1 - alpha) + blurred.astype(np.float32) * alpha).astype(np.uint8)
    else:
        image[y1:y2, x1:x2] = blurred


def decode(data: bytes) -> np.ndarray | None:
    """Any bytes in, an image or None out: empty, broken or exotic files must not crash the server."""
    if not data:
        return None
    try:
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    except cv2.error:
        return None
    if img is None or img.ndim != 3 or img.shape[2] != 3 or min(img.shape[:2]) == 0:
        return None
    return img


def anonymize(img: np.ndarray, max_side: int = 1600) -> AnonymizeResult:
    h, w = img.shape[:2]
    scale = min(1.0, max_side / max(h, w))
    if scale < 1.0:
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    img = img.copy()

    model = yolo_model()
    detections, detector = [], "haar"
    if model is not None:
        try:
            detections, detector = detect_yolo(model, img), "yolo"
        except Exception as e:  # never publish an unblurred photo because the model crashed
            log.exception("YOLO failed, falling back to Haar: %s", e)
            detections = detect_haar(img)
    else:
        detections = detect_haar(img)

    for d in detections:
        blur_region(img, d.box, d.kind)

    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 82])  # a new file: no EXIF at all
    if not ok:
        raise ValueError("cannot encode image")
    return AnonymizeResult(
        jpeg=buf.tobytes(), width=img.shape[1], height=img.shape[0], detector=detector, detections=detections,
        face_count=sum(d.kind == "face" for d in detections), plate_count=sum(d.kind == "plate" for d in detections),
    )
