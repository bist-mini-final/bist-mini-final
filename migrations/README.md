# Database migrations

Alembic is the versioned source of truth for schema changes. The initial revision
adopts the existing idempotent runtime DDL without dropping or renaming user data.
Add every future schema change as a new revision; do not edit an applied revision.

Runtime `ensure_schema` calls remain temporarily as a compatibility safety net for
older installations and will be removed only after every deployment path runs
`alembic upgrade head` before application startup.
