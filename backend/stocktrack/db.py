from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from stocktrack.models.base import Base

def make_engine(database_url: str):
    return create_async_engine(database_url, echo=False)

def make_sessionmaker(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)

async def init_models(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)

def _default_clause(col) -> str:
    """Render a SQLite DEFAULT clause from a column's scalar Python default.

    Needed because ADD COLUMN on a populated table must supply a default for a
    NOT NULL column. Callable/non-scalar defaults yield no clause (added NULL).
    """
    default = col.default
    if default is None or not getattr(default, "is_scalar", False):
        return ""
    val = default.arg
    if isinstance(val, bool):
        return f" DEFAULT {1 if val else 0}"
    if isinstance(val, (int, float)):
        return f" DEFAULT {val}"
    if isinstance(val, str):
        return " DEFAULT '{}'".format(val.replace("'", "''"))
    return ""

def _add_missing_columns(sync_conn) -> None:
    """Additive, idempotent migration (no Alembic).

    For each existing table, ALTER TABLE ADD COLUMN for any model column the DB
    is missing. ``create_all`` only creates whole tables; it never alters an
    existing one, so additive columns on a pre-existing DB need this.
    """
    insp = inspect(sync_conn)
    existing_tables = set(insp.get_table_names())
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # brand-new table — create_all already built it in full
        have = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in have:
                continue
            ddl_type = col.type.compile(dialect=sync_conn.dialect)
            sync_conn.exec_driver_sql(
                f'ALTER TABLE "{table.name}" ADD COLUMN '
                f'"{col.name}" {ddl_type}{_default_clause(col)}'
            )
