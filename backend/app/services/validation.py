"""Apply Stakeholder-configured mandatory fields and validation rules."""

import re
from typing import Any

from fastapi import HTTPException, status
from pymongo.asynchronous.database import AsyncDatabase

from app.services.app_settings import get_setting


def _get_path(doc: dict, path: str) -> Any:
    cur: Any = doc
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


async def validate_entity(db: AsyncDatabase, entity: str, doc: dict) -> None:
    rules_cfg = (await get_setting(db, "validation_rules")).get(entity)
    if not rules_cfg:
        return
    errors = []
    for field in rules_cfg.get("required", []):
        if _get_path(doc, field) in (None, "", []):
            errors.append(f"'{field}' is required")
    for field, rule in (rules_cfg.get("rules") or {}).items():
        value = _get_path(doc, field)
        if value in (None, ""):
            continue
        if "min" in rule and isinstance(value, (int, float)) and value < rule["min"]:
            errors.append(f"'{field}' must be >= {rule['min']}")
        if "max" in rule and isinstance(value, (int, float)) and value > rule["max"]:
            errors.append(f"'{field}' must be <= {rule['max']}")
        if "pattern" in rule and isinstance(value, str) and not re.fullmatch(rule["pattern"], value):
            errors.append(f"'{field}' has an invalid format")
        if "options" in rule and value not in rule["options"]:
            errors.append(f"'{field}' must be one of {rule['options']}")
    if errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, {"validation_errors": errors})
