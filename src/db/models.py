"""Database schema (SQLAlchemy 2.0). All user-owned records carry owner_id; case-derived records cascade on case deletion.
Timestamps are naive UTC. JSON columns are portable (JSON on SQLite, JSONB on PostgreSQL)."""
from datetime import datetime
from typing import Any, Dict, Optional

import sqlalchemy as sa
from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

PortableJSON = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.utcnow()


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(80))
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class AuthSession(Base):
    """Server-side session. Only the SHA-256 of the bearer token is stored, so a database leak does not yield usable tokens."""
    __tablename__ = "auth_sessions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)              # sliding idle expiry
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)     # hard cap
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    __table_args__ = (Index("ix_auth_sessions_user", "user_id"), Index("ix_auth_sessions_expires", "absolute_expires_at"))


class Case(Base):
    __tablename__ = "cases"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    data: Mapped[Dict[str, Any]] = mapped_column(PortableJSON, nullable=False)
    __table_args__ = (Index("ix_cases_owner_created", "owner_id", "created_at"),)


class Scenario(Base):
    __tablename__ = "scenarios"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    operations: Mapped[Any] = mapped_column(PortableJSON, nullable=False)   # requested operations (enough to reproduce the comparison)
    result: Mapped[Dict[str, Any]] = mapped_column(PortableJSON, nullable=False)
    __table_args__ = (Index("ix_scenarios_case", "case_id"), Index("ix_scenarios_owner", "owner_id"))


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    data: Mapped[Dict[str, Any]] = mapped_column(PortableJSON, nullable=False)
    export_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_exported_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    __table_args__ = (Index("ix_reports_case", "case_id"), Index("ix_reports_owner", "owner_id"))


class Draft(Base):
    __tablename__ = "drafts"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    review_state: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    data: Mapped[Dict[str, Any]] = mapped_column(PortableJSON, nullable=False)
    __table_args__ = (Index("ix_drafts_owner_updated", "owner_id", "updated_at"),)
