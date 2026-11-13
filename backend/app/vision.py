"""Photo checks.

1. Basic check, always on: is it a real photo (decodes, at least 320 px, not black, not blank).
   A failed basic check rejects the upload.
2. AI check, optional: a local vision model through Ollama (default qwen2.5vl:3b) answers
   whether the photo shows ice/snow/water and which danger signs are visible.
   The AI result is a hint: it can raise the observation's danger level, never lower it,
   and "no cracks found" is never treated as "safe" (snow hides cracks, a photo shows no thickness).
   If Ollama is not running, the photo is accepted with analysis_status="ai_unavailable".
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field

import cv2
import httpx
import numpy as np

from . import config

MIN_SIDE = 320
SIGNS = {"трещина": "risk", "вода на льду": "risk", "тонкий лёд": "danger", "промоина": "danger",
         "открытая вода": "danger", "отрыв льдины": "danger"}


class PhotoRejected(ValueError):
    pass


@dataclass
class VisionResult:
    looks_like_ice: bool | None = None
    signs: list[str] = field(default_factory=list)
    hazard: str = "none"
    confidence: float | None = None
    source: str = "basic"
    status: str = "done"


def basic_check(img: np.ndarray | None) -> None:
    if img is None:
        raise PhotoRejected("Файл не похож на фотографию")
    h, w = img.shape[:2]
    if min(h, w) < MIN_SIDE:
        raise PhotoRejected(f"Фото слишком маленькое: нужно хотя бы {MIN_SIDE} px по короткой стороне")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if gray.mean() < 18:
        raise PhotoRejected("Фото слишком тёмное: снимите ещё раз при свете")
    if gray.std() < 4:
        raise PhotoRejected("На фото ничего не видно: снимите лёд ещё раз")


def ai_check(jpeg: bytes) -> VisionResult:
    if config.flag("KL_OFFLINE") or config.flag("KL_DISABLE_LLM"):
        return VisionResult(status="ai_unavailable")
    prompt = (
        "Это фото от рыбака на льду. Ответь только JSON: "
        '{"looks_like_ice": true|false, "signs": [..], "confidence": 0..1}. '
        "looks_like_ice — видны ли лёд, снег на льду или вода водоёма. "
        f"signs — только из списка: {', '.join(SIGNS)}. Если признаков не видно, пустой список. "
        "Не оценивай, безопасен ли лёд."
    )
    try:
        r = httpx.post(f"{config.OLLAMA_URL}/api/generate", timeout=config.OLLAMA_VISION_TIMEOUT_S, json={
            "model": config.OLLAMA_VISION_MODEL, "prompt": prompt, "stream": False, "format": "json",
            "images": [base64.b64encode(jpeg).decode()], "options": {"temperature": 0},
        })
        r.raise_for_status()
        out = json.loads(r.json()["response"])
    except (httpx.HTTPError, KeyError, ValueError, TypeError):
        return VisionResult(status="ai_unavailable")

    signs = [s for s in out.get("signs", []) if isinstance(s, str) and s in SIGNS]
    order = {"none": 0, "risk": 1, "danger": 2}
    hazard = max((SIGNS[s] for s in signs), key=order.__getitem__, default="none")
    conf = out.get("confidence")
    looks = out.get("looks_like_ice")
    return VisionResult(
        looks_like_ice=looks if isinstance(looks, bool) else None,
        signs=signs, hazard=hazard,
        confidence=float(conf) if isinstance(conf, (int, float)) else None,
        source="ollama",
    )
