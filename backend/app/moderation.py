"""Moderation of what people publish.

Text of an observation goes through three checks:
1. rules, always on — rejected at once with a message saying what to fix:
   swearing, links / phone numbers / messenger handles, advertising, keyboard mashing;
2. a local language model (Qwen via Ollama), if running — suspicious text (insults, spam, off-topic)
   is published "на проверке": counted for safety, but its text and photo are hidden until a moderator looks;
3. people's reports — 3 reports from different users send a post to the moderator queue.

Safety rule: moderation never hides a danger. A danger report that is on review or reported still
counts in the zone status; only its text and photo are hidden. A calm "без тревог" post on review
does not count until approved (otherwise anyone could paint the map "safe" with spam).

Photos: a perceptual hash (dHash) catches the same picture uploaded again — by another account or
from an old trip.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

import cv2
import httpx
import numpy as np

from . import config

# Roots of Russian swearing (matched inside words, so "охуенный", "распиздяй" etc. are caught) and a few
# English ones. Kept short and conservative to avoid false positives on ordinary words.
_PREFIX = r"(?:о|об|на|по|за|от|до|вы|у|при|раз|рас|про|недо|пере|с|въ|съ|под)?"
_SWEAR = re.compile(
    # short roots: only at the start of a word or after a usual prefix ("охуенный", "заебал")
    rf"(?<![а-яё]){_PREFIX}(?:х[уy][йияеёю]|[её]б[аеиоуыл]|[её]бн|бл[яa](?:[дтхь]|(?![а-яё])))"
    r"|(?<![а-яё])сук[аиеуо]?(?![а-яё])"
    # long roots: anywhere inside a word ("распиздяй", "долбоёб")
    r"|п[иi]зд|муд[ао]к|пид[оа]р|гандон|шлюх|залуп|долбо[её]б|мраз[ьи]|fuck|shit|bitch",
    re.I,
)
_SWEAR_EXCEPT = re.compile(r"(?<![а-яё])(употреб|потребл|хлеб|колеб|гребл|ребят|себя|тебя|скребл|бляха-муха)", re.I)
_LINK = re.compile(r"(https?://|www\.|\b[a-z0-9-]+\.(ru|com|net|org|рф|su|me|io|info|online|site|pro)\b|t\.me/|@[a-z0-9_]{4,})", re.I)
_PHONE = re.compile(r"(\+7|8)[\s\-(]*\d{3}[\s\-)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}")
_ADS = re.compile(r"продам|продаю|куплю|скидк|акци[яи]|реклам|казино|ставк[иа] на|заработ|кредит|займ|подписывайт|"
                  r"пишите в (лс|личк|телег|вк|whatsapp|ватсап)|звоните", re.I)
_MASH = re.compile(r"(.)\1{5,}")


@dataclass
class Verdict:
    action: str          # allow | review | reject
    reason: str = ""     # for the person (reject) or for the moderator (review)
    source: str = "rules"


def has_swearing(text: str) -> bool:
    t = text.lower().replace("ё", "е")
    t = _SWEAR_EXCEPT.sub(" ", t)
    return bool(_SWEAR.search(t))


def check_rules(text: str) -> Verdict:
    t = (text or "").strip()
    if not t:
        return Verdict("allow")
    if has_swearing(t):
        return Verdict("reject", "Уберите нецензурные слова: наблюдение увидят все рыбаки.")
    if _LINK.search(t) or _PHONE.search(t):
        return Verdict("reject", "Ссылки, телефоны и контакты в наблюдениях запрещены.")
    if _ADS.search(t):
        return Verdict("reject", "Реклама и объявления в наблюдениях запрещены.")
    letters = sum(ch.isalpha() for ch in t)
    if _MASH.search(t) or (len(t) >= 12 and letters / len(t) < 0.3):
        return Verdict("reject", "Текст похож на случайный набор символов. Опишите, что вы видите на льду.")
    return Verdict("allow")


def check_llm(text: str) -> Verdict:
    if not text.strip() or config.flag("KL_OFFLINE") or config.flag("KL_DISABLE_LLM"):
        return Verdict("allow")
    prompt = (
        "Ты модератор приложения о состоянии льда для рыбаков. Оцени сообщение и ответь JSON "
        '{"label": "ok"|"insult"|"spam"|"offtopic", "why": "коротко"}. '
        "ok — о льде, погоде, рыбалке, обстановке на месте (даже грубовато). insult — оскорбления людей. "
        "spam — реклама, объявления. offtopic — не о льде и не о рыбалке. "
        f"Сообщение: «{text[:500]}»"
    )
    try:
        r = httpx.post(f"{config.OLLAMA_URL}/api/generate", timeout=config.OLLAMA_TIMEOUT_S, json={
            "model": config.OLLAMA_MODEL, "prompt": prompt, "stream": False, "format": "json",
            "options": {"temperature": 0}})
        r.raise_for_status()
        out = json.loads(r.json()["response"])
    except (httpx.HTTPError, KeyError, ValueError, TypeError):
        return Verdict("allow")
    label = out.get("label")
    if label in ("insult", "spam", "offtopic"):
        names = {"insult": "оскорбление", "spam": "спам", "offtopic": "не по теме"}
        return Verdict("review", f"ИИ: {names[label]}. {str(out.get('why', ''))[:150]}".strip(), "ollama")
    return Verdict("allow")


def check_text(text: str) -> Verdict:
    v = check_rules(text)
    return v if v.action != "allow" else check_llm(text)


# ---------- photos ----------
def dhash(img: np.ndarray) -> str:
    """64-bit difference hash: survives resizing, recompression and small edits."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    small = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)
    bits = (small[:, 1:] > small[:, :-1]).flatten()
    return f"{int(''.join('1' if b else '0' for b in bits), 2):016x}"


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


DUPLICATE_MAX_DISTANCE = 10  # of 64 bits: resized/recompressed copies 7–8, different photos ~25–35

REPORT_REASONS = {
    "spam": "Спам или реклама",
    "insult": "Оскорбления",
    "fake": "Неправда или фейк",
    "not_ice": "Фото не про лёд",
    "personal": "Личные данные: лица, номера, адреса",
    "other": "Другое",
}
REPORTS_TO_REVIEW = 3
