"""Engine / session management. DATABASE_URL selects the backend (SQLite for local development, PostgreSQL for deployment)."""
import logging
import os
import threading
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger("db")
DEFAULT_URL = "sqlite:///data/app.db"
_engine = None
_factory = None
_lock = threading.Lock()


def database_url() -> str:
    url = os.environ.get("DATABASE_URL") or DEFAULT_URL
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def is_sqlite(url: str = None) -> bool:
    return (url or database_url()).startswith("sqlite")


def safe_url(url: str = None) -> str:
    """URL with the password masked (for logs and diagnostics)."""
    from sqlalchemy.engine import make_url
    return make_url(url or database_url()).render_as_string(hide_password=True)


def get_engine():
    global _engine, _factory
    with _lock:
        if _engine is None:
            url = database_url()
            kw = {"pool_pre_ping": True}
            if is_sqlite(url):
                path = url.split("///", 1)[-1]
                if path and path != ":memory:" and os.path.dirname(path):
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                kw["connect_args"] = {"check_same_thread": False, "timeout": 15}
            else:
                kw.update(pool_size=int(os.environ.get("DB_POOL_SIZE", 5)), max_overflow=int(os.environ.get("DB_MAX_OVERFLOW", 10)))
            _engine = create_engine(url, **kw)
            if is_sqlite(url):
                @event.listens_for(_engine, "connect")
                def _pragmas(conn, _):          # foreign keys give cascades; WAL gives safe concurrent readers and a writer
                    cur = conn.cursor()
                    cur.execute("PRAGMA foreign_keys=ON")
                    cur.execute("PRAGMA journal_mode=WAL")
                    cur.execute("PRAGMA busy_timeout=15000")
                    cur.close()
            _factory = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
        return _engine


def reset_engine():
    """Dispose the engine (tests, restart simulation). The next get_engine() call re-reads DATABASE_URL."""
    global _engine, _factory
    with _lock:
        if _engine is not None:
            _engine.dispose()
        _engine, _factory = None, None


def new_session() -> Session:
    get_engine()
    return _factory()


@contextmanager
def session_scope():
    """One transaction: commit on success, roll back on any error."""
    s = new_session()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def ping() -> bool:
    from sqlalchemy import text
    try:
        with get_engine().connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception as e:  # noqa: BLE001
        logger.error("database ping failed: %s", type(e).__name__)
        return False
