"""
TracePlay Database Session and Engine Initializer.
Defaults to SQLite with WAL mode for fast local development,
supports PostgreSQL via DATABASE_URL environment variable.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from apps.api.models import Base

DEFAULT_DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../traceplay.db"))
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH}")

# For SQLite, ensure connect_args allows multi-threading
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)


# Auto initialize tables on module load
init_db()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
