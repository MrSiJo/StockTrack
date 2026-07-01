import asyncio

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from stocktrack.api.deps import get_session
from stocktrack.api.schemas import SettingsOut, SettingsUpdate
from stocktrack.bootstrap import get_settings
from stocktrack.services import gotify
from stocktrack.services.settings_service import (
    get,
    get_secret,
    gotify_config,
    set_value,
    truthy,
)

router = APIRouter()

_PLAIN_SETTING_KEYS = [
    "gotify_url",
    "gotify_priority",
    "restock_priority",
    "new_product_priority",
    "oos_priority",
    "gotify_send_retries",
    "default_interval_seconds",
    "failure_alert_after",
    "heartbeat_hours",
    "early_access_days",
    "price_drop_min_pct",
    "price_drop_min_abs",
    "price_drop_priority",
    "lead_time_priority",
    "alert_group_threshold",
    "cp_delivery_postcode",
    "cp_collection_branch_id",
]


async def _read_settings(session: AsyncSession, secret_key: str) -> SettingsOut:
    gotify_url = await get(session, "gotify_url", "") or ""
    token = await get_secret(session, "gotify_token", secret_key, "")
    return SettingsOut(
        gotify_url=gotify_url,
        gotify_token_set=bool(token),
        gotify_priority=int(await get(session, "gotify_priority", "7") or 7),
        restock_priority=int(await get(session, "restock_priority", "8") or 8),
        new_product_priority=int(await get(session, "new_product_priority", "8") or 8),
        oos_priority=int(await get(session, "oos_priority", "4") or 4),
        gotify_send_retries=int(await get(session, "gotify_send_retries", "3") or 3),
        default_interval_seconds=int(
            await get(session, "default_interval_seconds", "300") or 300
        ),
        failure_alert_after=int(
            await get(session, "failure_alert_after", "6") or 6
        ),
        heartbeat_hours=float(await get(session, "heartbeat_hours", "0") or 0),
        early_access_days=int(await get(session, "early_access_days", "30") or 30),
        ao_member=truthy(await get(session, "ao_member", "false")),
        price_drop_min_pct=float(await get(session, "price_drop_min_pct", "5") or 5),
        price_drop_min_abs=float(await get(session, "price_drop_min_abs", "5") or 5),
        price_drop_priority=int(await get(session, "price_drop_priority", "6") or 6),
        lead_time_priority=int(await get(session, "lead_time_priority", "5") or 5),
        alert_group_threshold=int(await get(session, "alert_group_threshold", "3") or 3),
        price_drop_in_stock_only=truthy(
            await get(session, "price_drop_in_stock_only", "true")
        ),
        cp_delivery_postcode=await get(session, "cp_delivery_postcode", "") or "",
        cp_collection_branch_id=await get(session, "cp_collection_branch_id", "") or "",
    )


@router.get("/settings", response_model=SettingsOut)
async def get_settings_endpoint(session: AsyncSession = Depends(get_session)):
    secret_key = get_settings().app_secret_key
    return await _read_settings(session, secret_key)


@router.put("/settings", response_model=SettingsOut)
async def update_settings(
    body: SettingsUpdate, session: AsyncSession = Depends(get_session)
):
    secret_key = get_settings().app_secret_key
    data = body.model_dump(exclude_none=True)

    for key in _PLAIN_SETTING_KEYS:
        if key in data:
            await set_value(session, key, str(data[key]),
                            is_secret=False, secret_key=secret_key)

    for bool_key in ("ao_member", "price_drop_in_stock_only"):
        if bool_key in data:
            await set_value(session, bool_key, str(data[bool_key]).lower(),
                            is_secret=False, secret_key=secret_key)

    # gotify_token: write-only; only update when a non-empty string is provided
    if data.get("gotify_token"):
        await set_value(session, "gotify_token", data["gotify_token"],
                        is_secret=True, secret_key=secret_key)

    await session.commit()
    return await _read_settings(session, secret_key)


@router.post("/settings/test")
async def test_gotify_connection(session: AsyncSession = Depends(get_session)):
    secret_key = get_settings().app_secret_key
    cfg = await gotify_config(session, secret_key)
    ok = await asyncio.to_thread(
        gotify.send,
        cfg,
        "StockTrack — test notification",
        "Gotify is configured and reachable.",
        click_url=None,
        markdown=False,
        priority=5,
        sleep=0,
    )
    return {"delivered": ok}
