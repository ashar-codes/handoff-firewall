from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


_url = settings().database_url
engine = create_engine(
    _url,
    pool_pre_ping=True,
    **(
        {}
        if _url.startswith("sqlite")
        else {"pool_size": settings().db_pool_size, "max_overflow": settings().db_max_overflow}
    ),
)
if engine.dialect.name == "sqlite":

    @event.listens_for(engine, "connect")
    def enable_fk(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")


SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_db():
    with SessionLocal() as db:
        yield db
