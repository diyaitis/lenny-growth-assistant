"""A vector column type that is pgvector on Postgres and a plain JSON list of
floats everywhere else (SQLite), so unit tests and local dev don't require a
running Postgres+pgvector instance. Production similarity search always runs
through Postgres (see app/services/retriever.py), where this type is a real
`vector(N)` column that pgvector can index and query with `<=>`.
"""
from __future__ import annotations

from sqlalchemy.types import JSON, TypeDecorator, UserDefinedType


class _PgVector(UserDefinedType):
    def __init__(self, dim: int):
        self.dim = dim

    def get_col_spec(self, **kw):
        return f"vector({self.dim})"

    def bind_processor(self, dialect):
        def process(value):
            if value is None:
                return None
            return "[" + ",".join(repr(float(v)) for v in value) + "]"

        return process

    def result_processor(self, dialect, coltype):
        def process(value):
            if value is None:
                return None
            if isinstance(value, str):
                return [float(v) for v in value.strip("[]").split(",") if v]
            return list(value)

        return process


class Vector(TypeDecorator):
    """Dialect-aware embedding column: pgvector on Postgres, JSON elsewhere."""

    impl = JSON
    cache_ok = True

    def __init__(self, dim: int):
        super().__init__()
        self.dim = dim

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(_PgVector(self.dim))
        return dialect.type_descriptor(JSON())

    # No process_bind_param/process_result_value overrides needed: the
    # dialect-specific impl above (pgvector's "[...]" wire format, or plain
    # JSON) already does the right (de)serialization on its own.
