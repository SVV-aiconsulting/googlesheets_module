"""Pydantic-схемы запросов/ответов FastAPI."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ----- clients -----


class ClientCreate(BaseModel):
    name: str = Field(..., min_length=1)
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    notes: Optional[str] = None
    status: str = "active"


class ClientUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1)
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None


class ClientOut(BaseModel):
    id: int
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    notes: Optional[str] = None
    status: str
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


# ----- deals -----


class DealCreate(BaseModel):
    title: str = Field(..., min_length=1)
    description: Optional[str] = None
    client_id: Optional[int] = None
    amount: float = 0.0
    currency: str = "RUB"
    status: str = "new"


class DealUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1)
    description: Optional[str] = None
    client_id: Optional[int] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    status: Optional[str] = None


class DealAttachClient(BaseModel):
    client_id: Optional[int] = None


class DealOut(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    client_id: Optional[int] = None
    amount: float
    currency: str
    status: str
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


# ----- tasks -----


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1)
    description: Optional[str] = None
    client_id: Optional[int] = None
    deal_id: Optional[int] = None
    due_at: Optional[str] = None
    is_done: bool = False


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1)
    description: Optional[str] = None
    client_id: Optional[int] = None
    deal_id: Optional[int] = None
    due_at: Optional[str] = None
    is_done: Optional[bool] = None


class TaskDoneBody(BaseModel):
    is_done: bool = True


class TaskOut(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    client_id: Optional[int] = None
    deal_id: Optional[int] = None
    due_at: Optional[str] = None
    is_done: int
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}
