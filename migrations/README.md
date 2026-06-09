Schema is currently initialized by `app.db.init_db()` for SQLite and PostgreSQL-compatible deployments.

Alembic is included now so future schema changes can be moved into versioned migrations without changing the application architecture.
