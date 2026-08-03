import datetime as dt
from typing import Optional, Any

from pydantic import BaseModel, EmailStr, Field


# ---- Auth ----
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)


class UserOut(BaseModel):
    id: int
    email: EmailStr
    role: str

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---- Products ----
class ProductCreate(BaseModel):
    title: str
    description: str
    category: str
    price: float = 0.0
    level: str = "beginner"


class ProductUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    level: Optional[str] = None
    is_active: Optional[bool] = None


class ProductOut(BaseModel):
    id: int
    title: str
    description: str
    category: str
    price: float
    level: str
    is_active: bool
    vector_synced: bool

    class Config:
        from_attributes = True


# ---- Events ----
class EventIn(BaseModel):
    event_type: str  # view | search | click | time_spent
    product_id: Optional[int] = None
    query: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class EventBatch(BaseModel):
    events: list[EventIn]


# ---- Recommendations ----
class RecommendationOut(BaseModel):
    id: int
    narrative: str
    products: list[ProductOut]
    trigger_reason: Optional[str]
    created_at: dt.datetime

    class Config:
        from_attributes = True
