"""Shared SQLAlchemy column types."""

import json

from sqlalchemy.types import Text, TypeDecorator


class JSONList(TypeDecorator):
    """Text column that stores a JSON array.

    Accepts a Python list (serialized on bind) or an already-serialized JSON
    string (stored verbatim); always returns a list on read. Used for the
    `photo_keys` columns on services and modifications.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else value
        except (ValueError, TypeError):
            return value
