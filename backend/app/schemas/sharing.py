from datetime import datetime

from pydantic import BaseModel, Field


class ShareCreateOut(BaseModel):
    share_id: int
    token: str
    expires_at: datetime


class ShareStatusOut(BaseModel):
    share_id: int
    expires_at: datetime
    redeemed_at: datetime | None
    redeemed_by_username: str | None
    revoked_at: datetime | None


class ShareListOut(BaseModel):
    document_id: int
    shares: list[ShareStatusOut]


class RedeemShareRequest(BaseModel):
    token: str = Field(min_length=32, max_length=128)


class RedeemShareOut(BaseModel):
    document_id: int
    filename: str
    owner_username: str
