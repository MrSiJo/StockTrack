"""Delivery-safe Gotify push notification sender."""
import logging
import time
from typing import Optional

log = logging.getLogger(__name__)

def send(
    cfg: dict,
    title: str,
    message: str,
    *,
    click_url: Optional[str] = None,
    markdown: bool = False,
    priority: int = 5,
    sleep: Optional[float] = None,
) -> bool:
    """Send a Gotify push notification. Returns True on success, False on failure.

    Never raises — callers use the return value to decide whether to persist
    the event (delivery-safe pattern).

    4xx responses are not retried (a misconfigured token won't fix itself).
    5xx responses and network errors are retried up to ``cfg['retries']`` times
    with a backoff of ``3 * attempt`` seconds between attempts. Pass
    ``sleep=0`` to skip sleeping (useful in tests).
    """
    url = (cfg.get("url") or "").rstrip("/")
    token = cfg.get("token") or ""
    retries = int(cfg.get("retries") or 3)

    if not url or not token:
        log.debug("Gotify not configured — skipping notification: %s", title)
        return True  # treat unconfigured as success (no alert to deliver)

    import httpx

    extras: dict = {}
    if markdown:
        extras["client::display"] = {"contentType": "text/markdown"}
    if click_url:
        extras["client::notification"] = {"click": {"url": click_url}}

    payload: dict = {"title": title, "message": message, "priority": priority}
    if extras:
        payload["extras"] = extras

    for attempt in range(1, retries + 1):
        try:
            resp = httpx.post(
                f"{url}/message",
                headers={"X-Gotify-Key": token},
                json=payload,
                timeout=10,
            )
            if resp.status_code < 300:
                return True
            if 400 <= resp.status_code < 500:
                log.warning(
                    "Gotify HTTP %d — client error, not retrying: %s",
                    resp.status_code, title,
                )
                return False
            log.warning("Gotify HTTP %d (attempt %d/%d)", resp.status_code, attempt, retries)
        except Exception as e:
            log.warning("Gotify send error (attempt %d/%d): %r", attempt, retries, e)
        if attempt < retries:
            delay = sleep if sleep is not None else 3 * attempt
            if delay:
                time.sleep(delay)
    return False
