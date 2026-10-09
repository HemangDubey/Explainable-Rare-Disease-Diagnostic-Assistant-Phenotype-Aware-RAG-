"""Alembic helpers. The CLI (`alembic upgrade head`) and `upgrade_head()` use the same scripts in ./migrations."""
import os

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from src.db.session import get_engine

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _config() -> Config:
    cfg = Config(os.path.join(ROOT, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(ROOT, "migrations"))
    return cfg


def head_revision() -> str:
    return ScriptDirectory.from_config(_config()).get_current_head()


def current_revision():
    with get_engine().connect() as c:
        return MigrationContext.configure(c).get_current_revision()


def upgrade_head() -> None:
    command.upgrade(_config(), "head")


def schema_is_current() -> bool:
    return current_revision() == head_revision()
