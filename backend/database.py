import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

# Get connection string from environment variable
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

if SQLALCHEMY_DATABASE_URL:
    # Remove potential quotes or whitespace that might have been pasted in cloud settings
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.strip().strip('"').strip("'")
else:
    # Local fallback
    SQLALCHEMY_DATABASE_URL = "sqlite:///./payflow.db"

# For PostgreSQL compatibility
if SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql://", 1)

# PGBouncer Cleanup: psycopg2 doesn't like the '?pgbouncer=true' parameter
if "postgresql" in SQLALCHEMY_DATABASE_URL and "?" in SQLALCHEMY_DATABASE_URL:
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.split("?")[0]

# PGBouncer / Supabase specific tuning
engine_args = {}
if "postgresql" in SQLALCHEMY_DATABASE_URL:
    # If using PGBouncer, we should be careful with connection pooling
    engine_args = {"pool_pre_ping": True}
else:
    # SQLite cleanup
    engine_args = {"connect_args": {"check_same_thread": False}}

engine = create_engine(SQLALCHEMY_DATABASE_URL, **engine_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
