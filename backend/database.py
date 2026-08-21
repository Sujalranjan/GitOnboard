import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker

from backend.config import settings

# Support both the legacy DATABASE_URL env var and the config-backed database URL.
# Docker Compose still injects DATABASE_URL, while local development uses settings.database_url.
raw_url = os.getenv("DATABASE_URL") or settings.database_url or ""
SQLALCHEMY_DATABASE_URL = raw_url.strip() if raw_url else "sqlite:///data/local.db"

if SQLALCHEMY_DATABASE_URL.startswith("postgresql://"):
    try:
        import psycopg
        SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgresql://", "postgresql+psycopg://")
    except ImportError:
        try:
            import psycopg2
            SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://")
        except ImportError:
            SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
elif "postgresql" in SQLALCHEMY_DATABASE_URL:
    try:
        if "psycopg2" in SQLALCHEMY_DATABASE_URL:
            import psycopg2
        else:
            import psycopg
    except ImportError:
        SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine_args = {}
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    from sqlalchemy.pool import StaticPool
    engine_args["connect_args"] = {"check_same_thread": False}
    if ":memory:" in SQLALCHEMY_DATABASE_URL:
        engine_args["poolclass"] = StaticPool
else:
    engine_args["pool_pre_ping"] = True

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    **engine_args
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
