# Product Requirements Document (PRD)

## Project
**mikiORM** — A universal Django-inspired ORM for Python applications across web, desktop, mobile, and CLI.

## Vision
Build a framework-agnostic ORM with Django-like ergonomics, strong type-safe queries, and production-grade migration tooling. The library should be easy to adopt from any Python app while supporting both sync and async database workflows.

## Most do what is bellow
always read and study the django db folder to understand what this orm is all about and get some insight from the django codebase
- django db link: https://github.com/django/django/tree/main/django/db
- django backends link: https://github.com/django/django/tree/main/django/db/backends
- in real world use cases and example and how the orm should work all models most be registered to be found during makemigrations and migrate. migrations most be generated before migrated with migrate command before any table/field/columns changes is created,updated or altered.
- the orm should be be db backend aware . pools logic should be execute fast without hanging same with migrations and commands
- all table/field/columns creation,alter or drop should use the migration flow only no direct stuff
- users should user the models register function/decorator to register models



## Key objectives
- Deliver a consistent API surface for models, querysets, managers, migrations, and transactions.
- Expose a clean top-level package API such as `from mikiorm.models import Model`, `from mikiorm.managers import BaseManager`, and `from mikiorm.backends import Postgres`.
- Provide a CLI experience like Django management commands: `mikiorm makemigrations`, `mikiorm migrate`, `mikiorm check`, `mikiorm rollback`, and `mikiorm history`.
- Support SQLite, PostgreSQL, and MySQL in the MVP with a clear extensible architecture for Oracle and dummy/in-memory backends.
- Make migrations safe, atomic, and auditable with built-in rollback and backup support.

## Goals
- Enable developers to define models and access fields as `Model.field_name`.
- Support sync and async database interaction in the same library.
- Ensure secure parameterized SQL generation only, no string interpolation for queries.
- Provide a top-level configuration system for `DATABASES`, `DEFAULT_DATABASE`, `INSTALLED_APPS`, `MIGRATION_PATH`, and logging.
- Deliver production-ready defaults for connection pooling, retries, timeouts, and observability.
- Avoid framework lock-in while giving a familiar developer experience.

## Target users
- Python developers building applications with Flask, FastAPI, Pyramid, or framework-independent tools.
- Teams that want Django-style models without full Django framework dependency.
- Desktop/mobile app builders using PyQt/PySide, Kivy, BeeWare.
- Architects who need sync and async database support together.

## Problem statement
- Current ORMs are either too tied to one framework or too lightweight for real production use.
- Developers need reliable schema migration tooling that can diff models against an existing database and safely apply or rollback changes.
- Applications require a unified API for both synchronous and asynchronous data access with secure database connection handling.

## Success metrics
- `mikiorm` sync core works on SQLite and PostgreSQL.
- Async support works for PostgreSQL and SQLite.
- Migration diff, generate, apply, rollback, and history commands operate correctly.
- CI passes for SQLite sync, PostgreSQL sync, and PostgreSQL async scenarios.
- Documentation and examples demonstrate model definition, migrations, and multi-backend usage.

## In scope
1. Connections and backends
   - `mikiorm.backends` with `sqlite`, `postgresql`, `mysql`, `oracle`, and `dummy` modules.
   - Sync adapters: SQLite, PostgreSQL via `psycopg2`, MySQL via `pymysql`.
   - Async adapters: SQLite via `aiosqlite`, PostgreSQL via `asyncpg`.
   - Connection pooling with validation, timeouts, retry, and metrics.
   - TLS/SSL support and secret retrieval integration.

2. Dialects
   - Base dialect abstraction for placeholder style, quoting, and type mapping.
   - PostgreSQL dialect with `$1..$n`, JSONB, UUID, TIMESTAMPTZ.
   - SQLite dialect with `?` placeholders, JSON/UUID fallback to TEXT.
   - MySQL dialect with `%s`, JSON, and engine-specific SQL features.

3. Models and fields
   - Top-level `Model` class with `save()`, `delete()`, `to_dict()`, and `refresh_from_db()`.
   - Field classes such as `AutoField`, `IntegerField`, `CharField`, `TextField`, `BooleanField`, `DateTimeField`, `JSONField`, `UUIDField`, `ForeignKey`, `OneToOneField`, `ManyToManyField`.
   - Field conversions via `python_value()` and `db_value()`.
   - Model registry and metadata for migration generation.

4. Managers and querysets
   - Core manager methods: `all()`, `filter()`, `exclude()`, `get()`, `count()`, `exists()`, `first()`, `last()`.
   - Mutation helpers: `update_or_create()`, `bulk_create()`, `update()`.
   - Projection helpers: `values()`, `values_list()`.
   - Relationship helpers: `select_related()`, `prefetch_related()`.
   - Lazy querysets with sync and async execution paths.

5. Query builder
   - Expression AST nodes: `Eq`, `IContains`, `In`, `Range`, `Not`, `And`, `Or`, `OrderBy`, `Join`, `Contains`, `StartsWith`, `EndsWith`.
   - SQL compilation using dialect-specific placeholders.
   - Query fingerprinting and cached SQL generation.

6. Unit of work
   - Track new, dirty, and deleted entity states.
   - Atomic commit and rollback support.
   - Optimistic locking support for versioned rows.
   - Retry hooks for transient conflict handling.

7. Migrations
   - Diff model definitions against existing DB schema.
   - Generate migration files with operation metadata and checksum.
   - Apply migrations safely with transactions, backups, and migration history.
   - Support rollback of the last migration and queryable migration status.
   - Preserve indexes and constraints when altering SQLite schemas.

8. Observability and security
   - Structured logs for queries, migrations, and connection events.
   - Metrics for latency, pool usage, and cache hit/miss.
   - Strict parameterized query execution.
   - Audit logging for migration operations and schema changes.

9. Documentation and examples
   - Clear API docs and guide for setup, models, and migrations.
   - Real-world examples for CRUD, blog, ecommerce, and school use cases.
   - CLI usage examples and migrations workflow.

10. Testing and CI
   - Unit tests for fields, query builder, models, migrations, and async flows.
   - Integration tests across SQLite and PostgreSQL backends.
   - Docker Compose support for Postgres integration tests.

## Out of scope for MVP
- Multi-database routing and sharding.
- Second-level caching systems such as Redis.
- Read replica routing and automatic failover.
- Full plugin architecture for custom expressions.
- Enterprise permission enforcement and RBAC.

## Architecture and repo conventions
- Follow branch naming `feature/`, `bugfix/`, `chore/`.
- Commit messages should use `type(scope): summary`.
- Use GitHub Actions CI and require code formatting, linting, and tests.
- Keep `uv.lock` committed and prefer `uv run` for developer tasks.

## CLI and operational guidance
- Primary CLI entrypoint should be `mikiorm` with management commands like `makemigrations`, `migrate`, `check`, `history`, and `rollback`.
- Use safe defaults for production migrations and require backups for destructive changes.
- Document rollback and recovery steps in the runbook.
- Use environment-driven overrides for database settings and secret management.
