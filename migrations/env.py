import os
import sys

from alembic import context

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db.models import Base  # noqa: E402
from src.db.session import database_url, get_engine  # noqa: E402

target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(url=database_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    with get_engine().connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=connection.dialect.name == "sqlite")
        with context.begin_transaction():
            context.run_migrations()
        connection.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
