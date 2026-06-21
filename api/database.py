import os
# pyrefly: ignore [missing-import]
from sqlalchemy import create_engine
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import sessionmaker

# Default to the local docker-compose setup if not provided
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "mysql+pymysql://sre_user:sre_password@localhost:3306/sre_db"
)

# Connect with pymysql
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
