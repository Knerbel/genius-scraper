from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .models import Base


def make_session_factory(database_url: str) -> sessionmaker:
    engine = create_engine(database_url)
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(database_url: str) -> None:
    Base.metadata.create_all(create_engine(database_url))
