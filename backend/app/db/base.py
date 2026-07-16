"""
Declarative base for all SQLAlchemy ORM models.

Import Base here in every model file and import all model
modules in alembic/env.py so Alembic can detect migrations.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
