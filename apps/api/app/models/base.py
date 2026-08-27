from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base — every ORM model's metadata lives here so
    Alembic autogenerate sees one combined schema. See docs/database.md."""
