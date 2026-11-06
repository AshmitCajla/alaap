from dataclasses import dataclass

from fastapi import Header, HTTPException

from .. import auth


@dataclass
class Owner:
    user_id: int
    business_id: int


def current_owner(authorization: str | None = Header(default=None)) -> Owner:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Not signed in")
    data = auth.read_token(authorization.split(" ", 1)[1])
    if not data:
        raise HTTPException(401, "Session expired; sign in again")
    return Owner(int(data["sub"]), int(data["biz"]))
