from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from contextlib import contextmanager
import config

# Create SQLAlchemy engine
engine = create_engine(
    config.DATABASE_URL,
    connect_args={"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {}
)

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@contextmanager
def get_db():
    """
    Context manager for database sessions.
    Ensures that sessions are closed after operations.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def init_db():
    """
    Initializes database tables.
    Importing models inside here avoids circular import issues.
    """
    from models.base import Base
    import models.auth
    import models.household
    import models.finance
    import models.budget
    import models.audit
    
    Base.metadata.create_all(bind=engine)
