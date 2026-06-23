from __future__ import annotations

from fastapi import HTTPException, Request, status


def get_bearer_token_from_request(request: Request) -> str:
    authorization = request.headers.get("Authorization") or request.headers.get("authorization")

    if not authorization or not authorization.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header. Please login again.",
        )

    authorization = authorization.strip()
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Expected: Bearer <token>.",
        )

    token = authorization[7:].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token. Please login again.",
        )
    return token
