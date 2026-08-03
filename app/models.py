import datetime as dt

from sqlalchemy import (
    Column, Integer, String, Float, Text, Boolean, DateTime, ForeignKey, JSON
)
from sqlalchemy.orm import relationship

from app.database import Base


def utcnow():
    return dt.datetime.utcnow()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="user", nullable=False)  # "user" | "admin"
    created_at = Column(DateTime, default=utcnow)

    events = relationship("Event", back_populates="user", cascade="all, delete-orphan")
    recommendations = relationship("Recommendation", back_populates="user", cascade="all, delete-orphan")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String, index=True, nullable=False)
    price = Column(Float, default=0.0)
    level = Column(String, default="beginner")  # beginner | intermediate | advanced
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    # Tracks whether the vector store write succeeded, so dual-write drift is visible.
    vector_synced = Column(Boolean, default=False)


class Event(Base):
    """A single behavioral event: page view, search, click, time-spent ping, etc."""
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    event_type = Column(String, nullable=False)  # view | search | click | time_spent
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    query = Column(String, nullable=True)  # for search events
    metadata_json = Column(JSON, nullable=True)  # duration_ms, referrer, etc.
    created_at = Column(DateTime, default=utcnow, index=True)

    user = relationship("User", back_populates="events")


class Recommendation(Base):
    """A stored, cached recommendation payload for a user, refreshed as behavior evolves."""
    __tablename__ = "recommendations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    narrative = Column(Text, nullable=False)          # persuasive copy
    product_ids = Column(JSON, nullable=False)        # ordered list of recommended product ids
    trigger_reason = Column(String, nullable=True)     # why this refresh fired
    based_on_event_count = Column(Integer, default=0)  # event-count watermark used for caching
    created_at = Column(DateTime, default=utcnow, index=True)

    user = relationship("User", back_populates="recommendations")
