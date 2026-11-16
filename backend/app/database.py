"""
Database connection, session management, and base declarative class.
Supports both PostgreSQL and local SQLite with automatic graceful fallback.
"""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from typing import Generator
from backend.app.config import settings
from backend.app.utils.logger import logger

Base = declarative_base()

def get_engine():
    """
    Creates the SQLAlchemy engine based on DATABASE_URL.
    If PostgreSQL is specified but unreachable, falls back gracefully to SQLite.
    """
    db_url = settings.DATABASE_URL
    is_sqlite = db_url.startswith("sqlite")
    
    if not is_sqlite:
        try:
            logger.info(f"Connecting to production PostgreSQL at: {db_url.split('@')[-1] if '@' in db_url else db_url}")
            pg_engine = create_engine(db_url, pool_pre_ping=True, echo=False)
            with pg_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("[SUCCESS] Connected to PostgreSQL successfully.")
            return pg_engine
        except Exception as e:
            fallback_sqlite = f"sqlite:///{settings.BASE_DIR}/fraudshield.db"
            logger.warning(
                f"[DATABASE FALLBACK] PostgreSQL connection failed ({e}). "
                f"Falling back to local SQLite database at {fallback_sqlite}."
            )
            return create_engine(
                fallback_sqlite,
                connect_args={"check_same_thread": False},
                pool_pre_ping=True,
                echo=False
            )
    else:
        return create_engine(
            db_url,
            connect_args={"check_same_thread": False},
            pool_pre_ping=True,
            echo=False
        )

engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for yielding database sessions safely."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Create all tables registered in the Base metadata."""
    logger.info("Initializing database schema...")
    # Import all models so metadata knows about them
    import backend.app.models.user
    import backend.app.models.transaction
    import backend.app.models.alert
    import backend.app.models.log
    import backend.app.models.metric
    
    Base.metadata.create_all(bind=engine)
    logger.info("Database schema initialized successfully.")
