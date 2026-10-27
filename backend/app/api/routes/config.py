"""Stakeholder configuration (PRD 4.18): lookups, rules, permissions, providers."""

import json

from fastapi import APIRouter, HTTPException, status
from pydantic import TypeAdapter, ValidationError
from pymongo.errors import DuplicateKeyError

from app.core import crypto
from app.core.deps import CurrentUser, Db, Stakeholder
from app.core.permissions import ACTIONS, RESOURCES, STAKEHOLDER_ONLY, full_matrix
from app.db import collections as c
from app.schemas.config import SETTING_SCHEMAS, EntityRules, LookupCreate, LookupUpdate, ProviderConfigUpsert
from app.services import audit
from app.services.app_settings import DEFAULT_SETTINGS, get_all_settings, get_setting, put_setting
from app.services.lookups import LOOKUP_TYPES, TARGET_METRICS
from app.utils.dates import utcnow
from app.utils.mongo import diff, get_or_404, serialize

router = APIRouter(prefix="/config", tags=["configuration"])


# ---------------------------------------------------------------- lookups

@router.get("/lookup-types")
async def lookup_types(_: CurrentUser):
    return {"types": LOOKUP_TYPES, "target_metrics": TARGET_METRICS}


@router.get("/lookups")
async def list_lookups(db: Db, _: CurrentUser, type: str | None = None, include_inactive: bool = False):
    query: dict = {}
    if type:
        query["type"] = type
    if not include_inactive:
        query["is_active"] = True
    docs = await db[c.LOOKUPS].find(query).sort([("type", 1), ("order", 1), ("label", 1)]).to_list()
    return serialize(docs)


def _check_lookup_attributes(lookup_type: str, attributes: dict):
    if lookup_type == "target_type" and attributes.get("metric") not in TARGET_METRICS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"target_type needs attributes.metric, one of {sorted(TARGET_METRICS)}",
        )
    if lookup_type == "health_field" and attributes.get("data_type") not in ("number", "text", "boolean", "select"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "health_field needs attributes.data_type: number|text|boolean|select"
        )


@router.post("/lookups", status_code=status.HTTP_201_CREATED)
async def create_lookup(body: LookupCreate, db: Db, actor: Stakeholder):
    if body.type not in LOOKUP_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown lookup type. Use one of {list(LOOKUP_TYPES)}")
    _check_lookup_attributes(body.type, body.attributes)
    now = utcnow()
    doc = {**body.model_dump(), "is_system": False, "created_at": now, "updated_at": now}
    try:
        res = await db[c.LOOKUPS].insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{body.type} '{body.code}' already exists")
    await audit.log(db, actor, "config_change", "lookup", res.inserted_id, f"Added {body.type} '{body.code}'")
    return serialize(doc)


@router.patch("/lookups/{lookup_id}")
async def update_lookup(lookup_id: str, body: LookupUpdate, db: Db, actor: Stakeholder):
    before = await get_or_404(db[c.LOOKUPS], lookup_id, "Lookup")
    updates = body.model_dump(exclude_unset=True)
    if "attributes" in updates:
        _check_lookup_attributes(before["type"], updates["attributes"])
    if not updates:
        return serialize(before)
    updates["updated_at"] = utcnow()
    await db[c.LOOKUPS].update_one({"_id": before["_id"]}, {"$set": updates})
    after = await db[c.LOOKUPS].find_one({"_id": before["_id"]})
    await audit.log(db, actor, "config_change", "lookup", before["_id"],
                    f"Updated {before['type']} '{before['code']}'", diff(before, after))
    return serialize(after)


# ---------------------------------------------------------------- settings

@router.get("/settings")
async def all_settings(db: Db, _: Stakeholder):
    return await get_all_settings(db)


@router.get("/settings/{key}")
async def one_setting(key: str, db: Db, _: Stakeholder):
    if key not in DEFAULT_SETTINGS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown setting")
    return await get_setting(db, key)


@router.put("/settings/{key}")
async def update_setting(key: str, value: dict, db: Db, actor: Stakeholder):
    from app.core.deps import is_super_admin
    if not is_super_admin(actor):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only Super Admin can change configuration settings")
    if key not in SETTING_SCHEMAS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown setting")
    schema = SETTING_SCHEMAS[key]
    try:
        if schema is None:
            clean = {k: v.model_dump() for k, v in TypeAdapter(dict[str, EntityRules]).validate_python(value).items()}
        else:
            clean = schema.model_validate(value).model_dump()
    except ValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, json.loads(exc.json(include_url=False)))
    before, after = await put_setting(db, key, clean, actor["_id"])
    await audit.log(db, actor, "config_change", "setting", key, f"Updated setting '{key}'", diff(before, after))
    return after


# ---------------------------------------------------------------- permissions

@router.get("/permissions")
async def permission_matrix(db: Db, _: CurrentUser):
    perms = await get_setting(db, "permissions")
    return {
        "resources": RESOURCES,
        "actions": ACTIONS,
        "stakeholder_only": sorted(STAKEHOLDER_ONLY),
        "matrix": full_matrix(perms.get("volunteer", {})),
        "notes": "Stakeholders always hold every permission. Volunteer access is limited to their assigned village.",
    }


# ---------------------------------------------------------------- providers

def _provider_out(doc: dict) -> dict:
    out = serialize(doc)
    secrets = {}
    for k, token in (doc.get("credentials_encrypted") or {}).items():
        plain = crypto.decrypt(token)
        secrets[k] = crypto.mask(plain) if plain else "<unreadable: encryption key changed>"
    out["credentials_masked"] = secrets
    return out


@router.get("/providers")
async def list_providers(db: Db, _: Stakeholder, provider_type: str | None = None):
    query = {"provider_type": provider_type} if provider_type else {}
    try:
        return [_provider_out(d) async for d in db[c.PROVIDER_CONFIGS].find(query).sort("provider_type", 1)]
    except crypto.CredentialsKeyMissing as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))


@router.put("/providers")
async def upsert_provider(body: ProviderConfigUpsert, db: Db, actor: Stakeholder):
    key = {"provider_type": body.provider_type, "provider_name": body.provider_name.lower()}
    existing = await db[c.PROVIDER_CONFIGS].find_one(key)
    encrypted = dict((existing or {}).get("credentials_encrypted") or {})
    try:
        for k, v in (body.credentials or {}).items():
            if v:
                encrypted[k] = crypto.encrypt(v)
            else:
                encrypted.pop(k, None)
    except crypto.CredentialsKeyMissing as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    now = utcnow()
    if body.is_default:
        await db[c.PROVIDER_CONFIGS].update_many({"provider_type": body.provider_type}, {"$set": {"is_default": False}})
    await db[c.PROVIDER_CONFIGS].update_one(
        key,
        {
            "$set": {
                "is_active": body.is_active,
                "is_default": body.is_default,
                "config": body.config,
                "credentials_encrypted": encrypted,
                "updated_by": actor["_id"],
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    doc = await db[c.PROVIDER_CONFIGS].find_one(key)
    await audit.log(
        db, actor, "config_change", "provider_config", doc["_id"],
        f"Updated {body.provider_type} provider '{body.provider_name}'",
        meta={"credential_keys_changed": sorted((body.credentials or {}).keys())},  # never log values
    )
    return _provider_out(doc)


@router.delete("/providers/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(provider_id: str, db: Db, actor: Stakeholder):
    from app.core.deps import check_can_delete
    check_can_delete(actor)
    doc = await get_or_404(db[c.PROVIDER_CONFIGS], provider_id, "Provider config")
    await db[c.PROVIDER_CONFIGS].delete_one({"_id": doc["_id"]})
    await audit.log(db, actor, "config_change", "provider_config", doc["_id"],
                    f"Deleted {doc['provider_type']} provider '{doc['provider_name']}'")
