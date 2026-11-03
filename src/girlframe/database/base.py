"""Shared metadata; application tables are registered by database.tables."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
