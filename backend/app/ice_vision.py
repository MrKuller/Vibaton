"""Model 2: what is on the ice photo — material, texture, cracks, water.

Two layers, results are merged (the more alarming one wins):

1. Computer vision without training (always on, CPU, ~50 ms):
   - material: share of snow / white ice / clear (dark, transparent) ice / water by colour in HSV,
     measured on the lower 70 % of the frame (the upper part is usually sky or shore);
   - texture: sharpness of detail (variance of the Laplacian): smooth / grainy / rough;
   - cracks: thin dark elongated lines found with a black-hat filter and contour shape analysis.
   These are heuristics with hand-set thresholds. They give hints, not a verdict, and must be checked
   against real photos from the bays before relying on them (see README, «Проверка моделей»).

2. Your trained model (optional): ICE_MODEL_PATH=models/ice.pt, any ultralytics YOLO model,
   classification or detection. Class names are mapped to signs by keywords:
   crack → трещина, water/wet → вода на льду, hole/polynya/open → промоина, thin → тонкий лёд.

Nothing here can declare ice safe: "no cracks found" never lowers a danger level.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field

import cv2
import numpy as np

from . import config

log = logging.getLogger(__name__)

SIGN_LEVEL = {"трещина": "risk", "вода на льду": "risk", "тонкий лёд": "danger", "промоина": "danger",
              "открытая вода": "danger", "отрыв льдины": "danger"}
ORDER = {"none": 0, "risk": 1, "danger": 2}

# thresholds (tune on real photos)
CRACK_SIGN_SCORE = 0.6      # total crack length / image diagonal
WATER_ON_ICE_SHARE = 0.10
OPEN_WATER_SHARE = 0.35

_lock = threading.Lock()
_model = None


@dataclass
class IceAnalysis:
    material: dict[str, float] = field(default_factory=dict)  # snow, white_ice, clear_ice, water, other (shares)
    texture: str = ""            # гладкая | зернистая | неровная
    texture_score: float = 0.0
    crack_score: float = 0.0
    crack_count: int = 0
    signs: list[str] = field(default_factory=list)
    hazard: str = "none"
    confidence: float = 0.3
    looks_like_ice: bool | None = None
    source: str = "cv"


def _hazard(signs: list[str]) -> str:
    return max((SIGN_LEVEL.get(s, "none") for s in signs), key=ORDER.__getitem__, default="none")


# ---------- layer 1: classic CV ----------
def material_shares(bgr: np.ndarray) -> dict[str, float]:
    h = bgr.shape[0]
    roi = bgr[int(h * 0.3):]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    H, S, V = hsv[..., 0].astype(int), hsv[..., 1].astype(int), hsv[..., 2].astype(int)
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    local_std = cv2.blur((gray.astype(np.float32) - cv2.blur(gray, (9, 9)).astype(np.float32)) ** 2, (9, 9)) ** 0.5

    snow = (V > 185) & (S < 45)
    white_ice = (V >= 110) & (V <= 185) & (S < 50) & ~snow
    blueish = (H >= 85) & (H <= 130) & (S >= 40)
    water = ((V < 70) | (blueish & (V < 120))) & (local_std < 6)          # dark and smooth
    clear_ice = blueish & (V >= 60) & ~water & ~snow & ~white_ice
    total = float(V.size)
    shares = {"snow": snow.sum() / total, "white_ice": white_ice.sum() / total,
              "clear_ice": clear_ice.sum() / total, "water": water.sum() / total}
    shares["other"] = max(0.0, 1.0 - sum(shares.values()))
    return {k: round(float(v), 3) for k, v in shares.items()}


def texture(bgr: np.ndarray) -> tuple[str, float]:
    """Structure, not sensor noise: measured on a 400 px, slightly blurred copy."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    k = 400 / max(gray.shape)
    if k < 1:
        gray = cv2.resize(gray, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    label = "гладкая" if score < 25 else "зернистая" if score < 150 else "неровная"
    return label, round(score, 1)


def cracks(bgr: np.ndarray) -> tuple[float, int]:
    """Thin dark lines. Returns (total length / image diagonal, number of crack-like shapes).

    A shape counts as a crack when it is long and thin: for a line, area ≈ length × width and
    perimeter ≈ 2 × length, so width ≈ 2·area/perimeter. Branching cracks stay thin, unlike blobs.
    """
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)                      # suppress sensor noise and snow grain
    blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_RECT, (17, 17)))
    level = max(25.0, float(blackhat.mean() + 4 * blackhat.std()))
    _, mask = cv2.threshold(blackhat, level, 255, cv2.THRESH_BINARY)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    diag = float(np.hypot(*gray.shape[:2]))
    total, count = 0.0, 0
    for c in contours:
        perimeter = cv2.arcLength(c, True)
        if perimeter < 2 * 0.08 * diag:
            continue
        length = perimeter / 2
        width = 2 * cv2.contourArea(c) / perimeter
        if width <= 8:
            total += length
            count += 1
    return round(total / diag, 3), count


def analyze_cv(bgr: np.ndarray) -> IceAnalysis:
    h, w = bgr.shape[:2]
    s = min(1.0, 800 / max(h, w))
    if s < 1:
        bgr = cv2.resize(bgr, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    mat = material_shares(bgr)
    tex, tex_score = texture(bgr)
    crack_score, crack_count = cracks(bgr)

    signs: list[str] = []
    if crack_score >= CRACK_SIGN_SCORE:
        signs.append("трещина")
    icy = mat["snow"] + mat["white_ice"] + mat["clear_ice"]
    if mat["water"] >= OPEN_WATER_SHARE and icy >= 0.15:
        signs.append("открытая вода")
    elif mat["water"] >= WATER_ON_ICE_SHARE and icy >= 0.15:
        signs.append("вода на льду")

    return IceAnalysis(
        material=mat, texture=tex, texture_score=tex_score, crack_score=crack_score, crack_count=crack_count,
        signs=signs, hazard=_hazard(signs),
        confidence=0.4 if signs else 0.3,
        looks_like_ice=(icy + mat["water"]) >= 0.4,
    )


# ---------- layer 2: optional trained model ----------
def _sign_for_class(name: str) -> str | None:
    n = str(name).lower()
    if "crack" in n or "трещ" in n:
        return "трещина"
    if "hole" in n or "polyn" in n or "open" in n or "промоин" in n:
        return "промоина"
    if "thin" in n or "тонк" in n:
        return "тонкий лёд"
    if "water" in n or "wet" in n or "slush" in n or "вод" in n:
        return "вода на льду"
    return None


def ice_model():
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                path = config.ICE_MODEL_PATH
                try:
                    if not path.exists():
                        raise FileNotFoundError(str(path))
                    from ultralytics import YOLO
                    _model = YOLO(str(path))
                except Exception as e:
                    _model = False
                    log.info("ice model not used (%s): only classic CV", e)
    return _model or None


def analyze_model(model, bgr: np.ndarray) -> tuple[list[str], float | None]:
    r = model.predict(source=bgr, conf=0.35, verbose=False)[0]
    signs: list[str] = []
    conf: float | None = None
    if getattr(r, "probs", None) is not None:  # classification model
        top = int(r.probs.top1)
        conf = float(r.probs.top1conf)
        s = _sign_for_class(model.names[top])
        if s and conf >= 0.5:
            signs.append(s)
    elif getattr(r, "boxes", None) is not None:  # detection / segmentation model
        for b in r.boxes:
            s = _sign_for_class(model.names[int(b.cls[0])])
            if s and s not in signs:
                signs.append(s)
                conf = max(conf or 0, float(b.conf[0]))
    return signs, conf


def analyze(bgr: np.ndarray) -> IceAnalysis:
    a = analyze_cv(bgr)
    model = ice_model()
    if model is not None:
        try:
            signs, conf = analyze_model(model, bgr)
            a.signs = sorted(set(a.signs) | set(signs))
            a.hazard = _hazard(a.signs)
            a.confidence = max(a.confidence, conf or 0)
            a.source = "cv+model"
        except Exception as e:
            log.exception("ice model failed: %s", e)
    return a
