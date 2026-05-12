# Product Requirements Document (PRD)

## Project
**miki-orm** — Universal Django-style ORM for Python applications across web, desktop, mobile, and CLI.

## Vision & Objectives
A framework-agnostic ORM package that delivers Django-like developer ergonomics while integrating cleanly with any Python library or framework. It supports both sync and async workflows, protects data integrity, and provides production-grade migrations, observability, and security. 
Provide a consistent, high-level API for database access across frameworks.

Support multiple backends (PostgreSQL, MySQL, SQLite, MongoDB).

Offer lazy evaluation, query builder, migrations, and unit of work.

Achieve feature parity with Django ORM while remaining framework-agnostic.

## Goals
- Build a consistent data access layer usable by Flask, FastAPI, Django, Pyramid, PyQt/PySide, Kivy, BeeWare, and CLI tools.
- Provide a single API for models, query building, migrations, and transactions.
- Support SQLite for development and PostgreSQL for production with a path to MySQL and other dialects.
- Enable both synchronous and asynchronous database access.
- Deliver a developer experience that feels familiar to Django users.
- Ensure production readiness with audit logging, rollback-safe migrations, metrics, and CI validation.

## Target users
- Python full-stack developers building web applications with Flask, FastAPI, Django, Pyramid.
- Desktop/mobile app developers using PyQt/PySide, Kivy, BeeWare.
- Teams that want ORM behavior without framework lock-in.
- Developers who need sync and async database support from one package.

## Problem statement
- Existing ORMs are either framework-specific or not expressive enough for modern async/data safety needs.
- Developers need a unified ORM interface that works across environments without sacrificing migrations, observability, or production-grade behavior.
- Projects require a package with strong query abstractions, caching, and secure connection management.

## Success metrics
- Working sync ORM against SQLite and PostgreSQL.
- Working async ORM against PostgreSQL and async SQLite.
- Migration diff/apply/rollback feature set implemented.
- CI passing for SQLite sync, Postgres sync, and Postgres async.
- Docs and quickstart examples for both SQLite and Postgres.

## In-Scope
1. Connections
   - Sync adapters: SQLite, PostgreSQL via `psycopg2`, MySQL via `pymysql`.
   - Async adapters: SQLite via `aiosqlite`, PostgreSQL via `asyncpg`.
   - Connection pooling, validation, timeouts, retries, metrics.
   - TLS support and secrets manager integration.

2. Dialect Abstraction
   - Base dialect interface with paramstyle, quoting, type mapping.
   - PostgreSQL dialect: `$1..$n`, JSONB, UUID, TIMESTAMPTZ.
   - SQLite dialect: `?` placeholders, TEXT fallback for JSON/UUID.
   - Extensible design for MySQL and SQL Server.

3. Models
   - `ModelMeta`, model registration, field resolution.
   - Base model methods: `save()`, `delete()`, `to_dict()`.
   - Registry for introspection and migration generation.
   - ForeignKey resolution via `resolve_foreign_keys()`.

4. Fields
   - Core fields: `IntegerField`, `CharField`, `BooleanField`.
   - Extended fields: `DateTimeField`, `DateField`, `TimeField`, `DecimalField`, `JSONField`, `UUIDField`, `ForeignKey`.
   - `python_value()` and `db_value()` conversions.

5. Managers
   - Core query operations: `all()`, `filter()`, `exclude()`, `get()`.
   - Helpers: `count()`, `exists()`, `first()`, `last()`.
   - Mutation: `update_or_create()`, `bulk_create()`, `update()`.
   - Projection: `values()`, `values_list()`.
   - Relationship helpers: `select_related()`, `prefetch_related()`.

6. Query Builder
   - AST nodes: `Eq`, `IContains`, `In`, `Range`, `Not`, `And`, `Or`, `OrderBy`, `Join`,`Contains`,`StartsWith`,`EndsWith` etc.
   - Fingerprinting via `QueryAST.to_dict()`.
   - SQL compilation with placeholder adaptation.
   - `compile_cached()` using LRU cache.

7. QuerySet
   - Lazy evaluation until `.all(connection)` or iteration.
   - Row hydration into model instances.
   - Join hydration and related model attachment.
   - Prefetch hydration.

8. Unit of Work
   - Tracking object states: new, dirty, deleted.
   - Atomic commit and rollback with transaction boundaries.
   - Optimistic locking support.
   - Conflict retry hooks.

9. Migrations
   - Schema diff between model registry and DB schema.
   - Migration files with operation definitions.
   - Apply operations safely for SQLite and Postgres.
   - Transactional safety with backup and rollback.
   - Locking to prevent concurrent migration runs.
   - Rollback of last migration.

10. Caching
   - LRU cache for compiled SQL keyed by AST fingerprint.
   - Configurable TTL and maxsize.
   - Invalidate on schema change.

11. Async Support
   - Async connections and pools.
   - `AsyncQuerySet` and awaitable query execution.

12. Security
   - Parameterized queries only.
   - TLS-enabled DB connections.
   - Secrets manager support.
   - Audit logging for migrations.

13. Observability
   - Query metrics, latency, pool usage, cache hit/miss.
   - Structured logging and OpenTelemetry tracing.

14. Documentation
   - API docs generated from docstrings via Sphinx or MkDocs.
   - Quickstart guide generator script.
   - Operational runbook for backup/restore and recovery.

15. Testing and CI
   - Unit tests for AST, field conversions, cache.
   - Integration tests for migrations, relations, backup/restore.
   - Async tests via `pytest-asyncio`.
   - Docker Compose for a Postgres service.

## Out-of-Scope for MVP
- Multi-database routing and sharding.
- Second-level cache like Redis.
- Read-replica routing and automated failover.
- Full plugin system for custom expressions.
- Enterprise features such as built-in role-based permission enforcement.

## Git and GitHub Workflow
- Use git feature branches for each ticket/feature.
- Prefix branch names as `feature/`, `bugfix/`, `chore/`.
- Commit messages should follow a simple convention: `type(scope): summary`.
- Main branches: `main`, `develop`, `release/*`.
- Pull requests must include a summary, testing notes, and relevant issue link.
- Use GitHub Actions for CI and enforce checks on pull requests.

## Dependency Management with uv
- Use `uv` as the dependency and task runner.
- Keep `uv.lock` committed for reproducible environments.
- Run `uv install` to sync dependencies.
- Use `uv run` for scripts such as linting, testing, and docs generation.

## GitHub Actions CI Requirements
- Validate code formatting and linting.
- Run unit tests on Python matrix: `3.14`, `3.15`, `3.16`.
- Run SQLite sync tests, Postgres sync tests, Postgres async tests.
- Build docs and optionally run docs link checks.
- Use service container `postgres:latest` in workflow.

## Quickstart Deliverables
- Example `models.py` showing model definition, relationships, and migrations.
- Example SQLite app lifecycle.
- Example Postgres app lifecycle.
- Quickstart README or script that uses `uv` commands.

## Operational Runbook Summary
- Use `miki-orm migrate` to generate and apply schema changes.
- Back up the database before running production migrations.
- In case of failure, use `miki-orm migrate rollback` to revert the last migration.
- Monitor metrics and logs for query latency and pool health.
- Keep secrets in a managed vault and use TLS for production DB connections.
