"""Storage failure type + decorator: any database error becomes StorageError (mapped to HTTP 503 by the API). Messages never carry SQL or data."""
import functools
import logging

from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger("db")


class StorageError(RuntimeError):
    """The database could not complete the operation."""


def guarded(fn):
    @functools.wraps(fn)
    def wrapper(*a, **k):
        try:
            return fn(*a, **k)
        except SQLAlchemyError as e:
            logger.error("storage error in %s: %s", fn.__name__, type(e).__name__)
            raise StorageError(type(e).__name__) from None
    return wrapper
