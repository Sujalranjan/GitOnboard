import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker

from backend.config import settings

# Database URL from environment or config
raw_url = os.getenv("DATABASE_URL") or settings.database_url
is_test_mode = os.getenv("DEPLOYMENT_TYPE") == "TEST"

if not raw_url or not raw_url.strip():
    raise ValueError("DATABASE_URL must be configured")

SQLALCHEMY_DATABASE_URL = raw_url.strip()

# Normalize PostgreSQL URL formats (production/local dev)
if SQLALCHEMY_DATABASE_URL.startswith("postgresql://"):
    try:
        import psycopg
        SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgresql://", "postgresql+psycopg://")
    except ImportError:
        try:
            import psycopg2
            SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://")
        except ImportError:
            raise ImportError("psycopg or psycopg2 is required for PostgreSQL connections")
elif "postgresql" in SQLALCHEMY_DATABASE_URL:
    try:
        if "psycopg2" in SQLALCHEMY_DATABASE_URL:
            import psycopg2
        else:
            import psycopg
    except ImportError:
        raise ImportError("psycopg or psycopg2 is required for PostgreSQL connections")

# SQLite only allowed in test mode
if "sqlite" in SQLALCHEMY_DATABASE_URL.lower() and not is_test_mode:
    raise ValueError("SQLite is only allowed in TEST mode. Use PostgreSQL for production/local development.")

# Configure connection pool
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
