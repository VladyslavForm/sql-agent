"""Pydantic schemas of entities in the corresponding JSON file."""

from datetime import datetime
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field, StringConstraints, field_validator

ANADEA_DOMAINS = ["anadea.info", "anadeainc.com"]


class ClickUpUser(BaseModel):
    id: int
    username: Annotated[str, StringConstraints(strip_whitespace=True)]
    email: str
    initials: str
    role: Literal["member", "admin", "owner"]
    date_joined: datetime

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        if not any(value.endswith(domain) for domain in ANADEA_DOMAINS):
            raise ValueError("not Anadea's email")
        return value


class ClickUpVacationRequest(BaseModel):
    id: str
    name: Annotated[str, StringConstraints(strip_whitespace=True)]
    description: Annotated[Optional[str], StringConstraints(strip_whitespace=True)]
    status: str
    url: str
    start_date: datetime
    due_date: datetime
    type: str
    requester: int
    assignees_ids: list[int] = Field(min_length=1)
    date_created: datetime
    date_updated: datetime
    date_closed: Optional[datetime]


class Snapshot(BaseModel):
    n_users: int
    n_requests: int
    users: list[ClickUpUser]
    requests: list[ClickUpVacationRequest]
