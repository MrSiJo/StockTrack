from fastapi import APIRouter

from stocktrack.api.schemas import StoreOut
from stocktrack.sites import stores

router = APIRouter()


@router.get("/stores", response_model=list[StoreOut])
async def get_stores():
    return stores()
