"""Input errors in plain Russian ("защита от дурака").

FastAPI answers bad input with a technical 422 ("string_too_long", "loc": ["body", "thickness_cm"]).
People see these messages in the app, so every error is turned into "Поле: что не так и как исправить".
"""
from __future__ import annotations

import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

log = logging.getLogger("krepkiy")

FIELDS = {
    "email": "Email", "password": "Пароль", "display_name": "Имя", "website": "Форма",
    "type": "Что вы видите", "zone_id": "Участок", "thickness_cm": "Толщина льда", "method": "Как измерено",
    "ice_type": "Тип льда", "text": "Комментарий", "lat": "Широта", "lon": "Долгота",
    "gps_accuracy_m": "Точность GPS", "observed_at": "Время наблюдения", "anonymous": "Анонимно",
    "hide_point": "Скрывать точку", "mocked_location": "Геолокация", "kind": "Реакция", "file": "Фото",
    "radius_km": "Радиус", "hours": "Период", "limit": "Количество", "only_hazards": "Фильтр",
    "fresh_only": "Фильтр", "mine": "Фильтр", "obs_id": "Номер наблюдения", "zone_id_path": "Участок",
    "reason": "Причина", "comment": "Комментарий", "action": "Действие", "note": "Пояснение", "ban_days": "Срок блокировки",
}


def _message(err: dict) -> str:
    t, ctx = err.get("type", ""), err.get("ctx") or {}
    if t == "missing":
        return "не заполнено"
    if t == "json_invalid":
        return "запрос повреждён, повторите"
    if t == "string_too_long":
        return f"слишком длинно, не больше {ctx.get('max_length')} символов"
    if t == "string_too_short":
        return f"слишком коротко, не меньше {ctx.get('min_length')} символов"
    if t in ("greater_than_equal", "greater_than"):
        return f"должно быть не меньше {ctx.get('ge', ctx.get('gt'))}"
    if t in ("less_than_equal", "less_than"):
        return f"должно быть не больше {ctx.get('le', ctx.get('lt'))}"
    if t in ("int_parsing", "int_type", "int_from_float"):
        return "нужно целое число"
    if t == "finite_number":
        return "нужно обычное число"
    if t in ("float_parsing", "float_type"):
        return "нужно число"
    if t in ("bool_parsing", "bool_type"):
        return "нужно да или нет"
    if t == "literal_error":
        return "выберите вариант из списка"
    if t.startswith("datetime"):
        return "неверная дата и время"
    if t in ("string_type", "dict_type", "list_type", "model_attributes_type", "model_type"):
        return "неверный формат"
    return "неверное значение"


async def validation_error(_: Request, exc: RequestValidationError):
    errors = exc.errors()
    fields: dict[str, str] = {}
    for e in errors:
        loc = [str(x) for x in e.get("loc", ()) if x not in ("body", "query", "path", "header")]
        name = loc[-1] if loc else ""
        if e.get("type") == "json_invalid" or not name or name.isdigit():
            fields.setdefault("_", "Неверный формат данных. Обновите приложение и повторите.")
            continue
        fields.setdefault(name, f"{FIELDS.get(name, name)}: {_message(e)}")
    detail = next(iter(fields.values()), "Проверьте введённые данные")
    return JSONResponse({"detail": detail, "fields": fields}, status_code=422)


async def unexpected_error(_: Request, exc: Exception):
    log.exception("unhandled error: %s", exc)
    return JSONResponse({"detail": "Что-то пошло не так на сервере. Мы уже видим ошибку, повторите позже."},
                        status_code=500)
