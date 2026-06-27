from sqlalchemy import select
from stocktrack.bootstrap import get_settings
from stocktrack.models import Watch


async def seed_default_watches(session) -> None:
    existing = (await session.execute(select(Watch.id))).first()
    if existing:
        return

    settings = get_settings()
    watches = []

    if settings.seed_ao_url:
        watches.append(
            Watch(store="ao", url=settings.seed_ao_url, label="AO — Meaco air-con",
                  include_filter="Meaco", exclude_filter="Heating")
        )

    if settings.seed_jl_url:
        watches.append(
            Watch(store="johnlewis", url=settings.seed_jl_url, label="John Lewis — Meaco Cirro",
                  include_filter="Cirro", exclude_filter="")
        )

    if watches:
        session.add_all(watches)
