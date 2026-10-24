"""API token management. Session plus CSRF only: no API token is on the
allowlist for these paths, so a token can never manage tokens."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from stocktrack.api.deps import get_session
from stocktrack.api.schemas import ApiTokenCreate, ApiTokenCreated, ApiTokenOut
from stocktrack.services.token_service import (
    DuplicateTokenName,
    create_token,
    list_tokens,
    revoke_token,
)

router = APIRouter()


@router.get("/tokens", response_model=list[ApiTokenOut])
async def get_tokens(session: AsyncSession = Depends(get_session)):
    return [ApiTokenOut.model_validate(t) for t in await list_tokens(session)]


@router.post("/tokens", response_model=ApiTokenCreated,
             status_code=status.HTTP_201_CREATED)
async def post_token(body: ApiTokenCreate, session: AsyncSession = Depends(get_session)):
    try:
        row, token = await create_token(session, body.name, body.expires_in_days)
    except DuplicateTokenName as exc:
        raise HTTPException(status_code=409,
                            detail="a token with this name already exists") from exc
    # The only response that ever carries the token itself.
    return ApiTokenCreated(**ApiTokenOut.model_validate(row).model_dump(), token=token)


@router.post("/tokens/{token_id}/revoke", response_model=ApiTokenOut)
async def post_revoke(token_id: int, session: AsyncSession = Depends(get_session)):
    row = await revoke_token(session, token_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Token not found")
    return ApiTokenOut.model_validate(row)
