"""
Database connection, session management, and base declarative class.
Supports both PostgreSQL and local SQLite seamlessly.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from typing import Generator
from backend.app.config import settings
from backend.app.utils.logger import logger

# Detect database engine type for connection args
is_sqlite = settings.DATABASE_URL.startswith("sqlite")
connect_args = {"check_same_thread": False} if is_sqlite else {}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

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
