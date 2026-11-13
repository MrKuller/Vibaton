"""Message analysis and bay warnings.

Primary path: a local LLM through Ollama (e.g. Qwen). Fallback path: keyword rules.
The fallback is always available, so the app works on a laptop without a GPU.

Safety rules from the spec review:
- AI only raises a danger level, never lowers it (enforced in status.py);
- a warning is published only with concrete sources (observation ids + weather numbers);
- forbidden wording ("безопасно", "выдержит", "можно идти") is rejected and replaced by a template.
"""
from __future__ import annotations

import json
import re

import httpx

from .config import OLLAMA_MODEL, OLLAMA_TIMEOUT_S, OLLAMA_URL, flag

HAZARDS = ("danger", "risk", "none")
FORBIDDEN = re.compile(r"безопасн|выдерж|можно\s+(идти|выходить|ходить)|надёжн|надежн", re.I)

_DANGER = re.compile(r"промоин|полынь|провал|провалил|отрыв|оторвал|унесл|открыт\w* вод|разлом|ломает", re.I)
_RISK = re.compile(r"трещин|вода на льду|вода сверху|мокр|тонк|хруст|треск|подтаял|оттепел|сочится|наледь", re.I)
_TAGS = {
    "трещина": re.compile(r"трещин", re.I),
    "промоина": re.compile(r"промоин|полынь|открыт\w* вод", re.I),
    "вода на льду": re.compile(r"вода на льду|вода сверху|сочится|мокр", re.I),
    "отрыв": re.compile(r"отрыв|оторвал|унесл", re.I),
    "тонкий лёд": re.compile(r"тонк", re.I),
}


def _ollama_disabled() -> bool:
    return flag("KL_OFFLINE") or flag("KL_DISABLE_LLM")


def classify_rules(text: str) -> dict:
    hazard = "danger" if _DANGER.search(text) else "risk" if _RISK.search(text) else "none"
    tags = [t for t, rx in _TAGS.items() if rx.search(text)]
    return {"hazard": hazard, "tags": tags, "source": "rules"}


def _ollama_json(prompt: str) -> dict | None:
    if _ollama_disabled():
        return None
    try:
        r = httpx.post(f"{OLLAMA_URL}/api/generate", timeout=OLLAMA_TIMEOUT_S, json={
            "model": OLLAMA_MODEL, "prompt": prompt, "stream": False, "format": "json",
            "options": {"temperature": 0},
        })
        r.raise_for_status()
        return json.loads(r.json()["response"])
    except (httpx.HTTPError, KeyError, ValueError, TypeError):
        return None


def classify(text: str) -> dict:
    """Hazard level hinted by free text. Combined with rules: the higher level wins."""
    text = (text or "").strip()
    rules = classify_rules(text)
    if not text:
        return rules
    out = _ollama_json(
        "Ты помогаешь рыбакам на льду. Прочитай сообщение и ответь JSON "
        '{"hazard": "danger"|"risk"|"none", "tags": [строки]}. '
        "danger — промоина, отрыв льдины, провал, открытая вода. "
        "risk — трещина, вода на льду, тонкий или подтаявший лёд. none — тревог нет. "
        f"Сообщение: «{text[:500]}»"
    )
    if not out or out.get("hazard") not in HAZARDS:
        return rules
    order = {"none": 0, "risk": 1, "danger": 2}
    hazard = max(out["hazard"], rules["hazard"], key=order.__getitem__)
    tags = sorted(set(rules["tags"]) | {str(t)[:30] for t in out.get("tags", []) if isinstance(t, str)})[:6]
    return {"hazard": hazard, "tags": tags, "source": "ollama"}


def is_clean(text: str) -> bool:
    return not FORBIDDEN.search(text or "")


def bay_warning(bay: str, weather, hazard_obs: list, offshore: bool) -> dict | None:
    """A warning exists only when facts support it; wording may come from the LLM."""
    facts: list[str] = []
    if offshore and weather.wind_ms >= 8:
        facts.append(f"Отжимной ветер {weather.wind_ms:.0f} м/с")
    if weather.warming_c >= 8 or weather.crosses_zero:
        hi = max((d["t_max"] for d in weather.days if d.get("t_max") is not None), default=None)
        facts.append(f"Потепление до {hi:+.0f} °C" if hi is not None else "Потепление")
    if len(hazard_obs) >= 2:
        n = len(hazard_obs)
        word = "сообщение" if n % 10 == 1 and n % 100 != 11 else "сообщения" if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else "сообщений"
        facts.append(f"{n} {word} об опасности за сутки")
    if not facts:
        return None

    template = (f"{bay}: " + "; ".join(facts) + ". Вдоль кромки возможен отрыв льдин, у берега — трещины. "
                "Проверяйте лёд и не уходите далеко от берега.")
    text, source = template, "rules"
    out = _ollama_json(
        "Сформулируй короткое (до 2 предложений) предупреждение для рыбаков по фактам ниже. "
        "Нельзя писать, что лёд безопасен, выдержит или что можно идти. Не добавляй фактов. "
        f'Ответ JSON {{"text": "..."}}. Залив: {bay}. Факты: {"; ".join(facts)}.'
    )
    if out and isinstance(out.get("text"), str) and 20 < len(out["text"]) < 400 and is_clean(out["text"]):
        text, source = out["text"].strip(), "ollama"
    return {
        "bay": bay,
        "text": text,
        "facts": facts,
        "observation_ids": [o.id for o in hazard_obs],
        "weather": {"wind_ms": weather.wind_ms, "wind_from_deg": weather.wind_from_deg,
                    "temp_c": weather.temp_c, "source": weather.source},
        "source": source,
        "disclaimer": "Подсказка ИИ, а не оценка прочности льда. ИИ может ошибаться.",
    }
