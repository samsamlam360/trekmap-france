import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Les secrets et paramètres de connexion restent hors du code source.
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL n'est pas défini. Exemple: "
        "postgresql+psycopg2://postgres:motdepasse@localhost:5432/trekmap"
    )

def env_int(name, default, minimum=0, maximum=100000):
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        raise RuntimeError(f"{name} doit être un entier.")
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} doit être compris entre {minimum} et {maximum}.")
    return value

POOL_SIZE = env_int("DB_POOL_SIZE", 5, 1, 50)
MAX_OVERFLOW = env_int("DB_MAX_OVERFLOW", 10, 0, 100)
POOL_TIMEOUT = env_int("DB_POOL_TIMEOUT", 10, 1, 120)
POOL_RECYCLE = env_int("DB_POOL_RECYCLE", 1800, 60, 86400)
CONNECT_TIMEOUT = env_int("DB_CONNECT_TIMEOUT", 10, 1, 120)

connect_args = {"connect_timeout": CONNECT_TIMEOUT}
sslmode = os.getenv("DB_SSLMODE", "").strip()
if sslmode:
    allowed_sslmodes = {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}
    if sslmode not in allowed_sslmodes:
        raise RuntimeError("DB_SSLMODE est invalide.")
    connect_args["sslmode"] = sslmode

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=POOL_RECYCLE,
    pool_size=POOL_SIZE,
    max_overflow=MAX_OVERFLOW,
    pool_timeout=POOL_TIMEOUT,
    connect_args=connect_args,
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
