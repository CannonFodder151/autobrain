"""Shared SQLAlchemy column types."""

import json

from sqlalchemy.types import Text, TypeDecorator


class StringArray(TypeDecorator):
    """A list-of-strings column: native postgres ARRAY in prod, JSON text
    elsewhere (sqlite test engines can't compile ARRAY)."""

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from sqlalchemy import String
            from sqlalchemy.dialects.postgresql import ARRAY

            return dialect.type_descriptor(ARRAY(String(32)))
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return list(value)
        return json.dumps(list(value))

    def process_result_value(self, value, dialect):
        if value is None:
            return []
        if isinstance(value, list):
            return value
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return []


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
