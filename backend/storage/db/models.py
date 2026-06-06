from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""
    pass


class User(Base):
    """User account for authentication."""

    __tablename__ = "users"

    id = Column(String, primary_key=True)
    username = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    sessions = relationship("Session", back_populates="user")
    resumes = relationship("Resume", back_populates="user")


class Session(Base):
    """Session metadata stored in SQLite."""

    __tablename__ = "sessions"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    profile_id = Column(String, nullable=False)
    status = Column(String, nullable=False, default="active")  # active, paused, completed, abandoned
    mode = Column(String, nullable=False, default="text")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_event_ts = Column(DateTime, nullable=True)
    event_count = Column(Integer, nullable=False, default=0)
    turn_count = Column(Integer, nullable=False, default=0)
    summary = Column(Text, nullable=True)  # JSON string of summary dict
    resume_id = Column(String, ForeignKey("resumes.id"), nullable=True, index=True)
    audio_seconds_in = Column(Float, nullable=False, default=0.0)
    audio_seconds_out = Column(Float, nullable=False, default=0.0)

    user = relationship("User", back_populates="sessions")


class Resume(Base):
    """Resume stored in SQLite."""

    __tablename__ = "resumes"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    file_name = Column(String, nullable=True)  # Original file name
    file_path = Column(String, nullable=True)  # File storage path
    file_type = Column(String, nullable=True)  # pdf, png, jpg
    content = Column(Text, nullable=False, default="")
    parsed_json = Column(Text, nullable=True)
    analysis_result = Column(Text, nullable=True)  # Cached analysis JSON
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="resumes")
