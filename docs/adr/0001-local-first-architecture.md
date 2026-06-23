# ADR 0001: Local-first architecture

Status: accepted.

The application uses a React frontend and a Python FastAPI monolith. SQLAlchemy 2 and Alembic own a SQLite database configured for foreign keys, WAL, and a busy timeout. APScheduler is the initial job trigger; simulation state remains in application tables. This avoids Redis and distributed-worker operations for a single-user product while preserving a migration path to PostgreSQL and RQ.

Tournament rules are pure domain functions. Market observations are consolidated into a correlated prior and log-pooled with an independent Poisson/Elo model. Completed simulation inputs and outputs are immutable and versioned.
