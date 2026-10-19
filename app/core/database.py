from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import get_settings

Base = declarative_base()

_engine = None
_SessionLocal = None


def _init_engine() -> None:
    global _engine, _SessionLocal
    if _engine is not None:
        return
    settings = get_settings()
    connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    _engine = create_engine(settings.database_url, connect_args=connect_args)
    _SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)


def get_engine():
    _init_engine()
    return _engine


def init_db() -> None:
    from app.models.upload_session import UploadSession  # noqa: F401

    _init_engine()
    Base.metadata.create_all(bind=get_engine())


def get_db() -> Generator[Session, None, None]:
    _init_engine()
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()


def reset_db_engine() -> None:
    """Dispose engine so a new process/fixture can reconnect (tests)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
