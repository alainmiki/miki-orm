# Technical Requirements Document (TRD)

## Architecture Overview

### Core design principles
- Modular architecture separated by concern: configuration, CLI, backends, migrations, models, fields, queries, transactions, and observability.
- Framework-agnostic API that is independent of Flask/FastAPI/Django or desktop/mobile frameworks.
- Clear sync/async split with parallel interfaces and shared model/field metadata.
- Pluggable dialect layer for safe SQL generation across database engines.
- Top-level CLI and package entrypoints for developer ergonomics.

## Package Layout

- `mikiorm/`
  - `__init__.py`
  - `conf/`
    - `__init__.py`
    - `settings.py`
    - `defaults.py`
    - `loader.py`
  - `cli/`
    - `__init__.py`
    - `commands.py`
    - `manage.py`
    - `migration_commands.py`
    - `health_commands.py`
  - `backends/`
    - `__init__.py`
    - `base/`
      - `__init__.py`
      - `base.py`
      - `adapter.py`
      - `pool.py`
      - `dialect.py`
    - `sqlite/`
      - `__init__.py`
      - `client.py`
      - `schema.py`
      - `creation.py`
      - `operations.py`
      - `introspection.py`
      - `features.py`
    - `postgresql/`
      - `__init__.py`
      - `client.py`
      - `compiler.py`
      - `schema.py`
      - `introspection.py`
      - `features.py`
    - `mysql/`
      - `__init__.py`
      - `client.py`
      - `compiler.py`
      - `schema.py`
      - `introspection.py`
      - `features.py`
    - `oracle/`
      - `__init__.py`
      - `client.py`
      - `schema.py`
      - `compat.py`
    - `dummy/`
      - `__init__.py`
      - `client.py`
      - `memory.py`
  - `migrations/`
    - `__init__.py`
    - `operations/`
      - `__init__.py`
      - `create_table.py`
      - `alter_table.py`
      - `drop_table.py`
      - `add_column.py`
      - `alter_column.py`
      - `drop_column.py`
      - `create_index.py`
      - `drop_index.py`
      - `constraints.py`
    - `engine.py`
    - `history.py`
    - `schema.py`
    - `editor.py`
    - `manager.py`
  - `models/`
    - `__init__.py`
    - `base.py`
    - `fields/`
      - `__init__.py`
      - `core.py`
      - `relational.py`
      - `validators.py`
    - `functions/`
    - `sql/`
    - `query.py`
    - `options.py`
    - `aggregates.py`
    - `constants.py`
    - `constraints.py`
  - `managers/`
    - `__init__.py`
    - `base.py`
    - `custom.py`
  - `transactions.py`
  - `utils.py`
  - `exceptions.py`
  - `registry.py`
  - `observability.py`
  - `cache.py`

- `tests/`
  - `unit/`
  - `integration/`
- `examples/`
- `docs/`
- `docker-compose.yml`
- `.github/workflows/ci.yml`

## Component Design

### Configuration
- `mikiorm.conf.settings`
  - Provides `DATABASES`, `DEFAULT_DATABASE`, `INSTALLED_APPS`, `MIGRATION_PATH`, `LOGGING`, and environment overrides.
  - Supports secure secret resolution and connection option injection.
  - Loads settings from Python modules and environment variables.

### CLI
- `mikiorm.cli.commands`
  - `makemigrations`
  - `migrate`
  - `check`
  - `dbcheck`
  - `history`
  - `rollback`
- `mikiorm.cli.manage`
  - Exposes top-level command entrypoints like `mikiorm` and optionally `miki`.
  - Includes command validation and safe execution.

### Backends
- Base backend abstractions in `mikiorm.backends.base`.
- Engine-specific backend packages under `sqlite`, `postgresql`, `mysql`, `oracle`, and `dummy`.
- Each backend includes client driver integration, schema introspection, creation, and engine-specific features.
- Backends expose consistent sync and async APIs.

### Models and fields
- `mikiorm.models.base.Model` is the core ORM model class.
- `mikiorm.models.fields` contains field definitions and conversions.
- Fields support database-aware type mapping and both Python-to-DB and DB-to-Python conversions.
- Model metadata supports relationship resolution and migration generation.

### Managers and querysets
- `BaseManager` exposes Django-like operations on models.
- `QuerySet` is lazy, composable, and can execute synchronously or asynchronously.
- Relationship helpers `select_related` and `prefetch_related` are supported at the query builder level.

### Query builder and compiler
- AST representation of filters, joins, ordering, and annotations.
- Dialect compilation produces safe parameterized SQL strings.
- Cached SQL generation uses query fingerprints and an LRU cache.

### Migrations
- Migration engine compares model metadata to the live database schema.
- Migration files are versioned with metadata, timestamp, and checksum.
- Apply and rollback flows are transactional by default, with backup strategies for SQLite.
- Migration history is stored in a dedicated schema table.

### Transactions and unit of work
- Transaction helpers in `mikiorm.transactions` provide context-managed atomic blocks.
- Unit of work tracks new, dirty, and deleted entities.
- Optimistic locking and retry semantics are supported for safe concurrent updates.

### Observability and security
- Structured logging for query execution and migration actions.
- Metrics for latency, pool usage, and cache hit rate.
- Parameterized SQL only; no raw string interpolation for queries.
- Secret manager integration for production credentials.

## Execution flows

### Model lifecycle
1. Define model classes under `mikiorm.models`.
2. Register models using the global registry.
3. Generate migrations based on model diffs.
4. Apply migrations to the target database.
5. Query and mutate data through manager/queryset APIs.

### Query execution
1. Build a queryset using manager methods.
2. Compile the AST to SQL via the selected dialect.
3. Execute parameterized SQL through the backend connection.
4. Hydrate rows into model instances.

### Migration flow
1. Load current model metadata and database schema.
2. Diff schema and generate migration operations.
3. Write migration artifacts and metadata.
4. Apply changes inside a transaction or backup workflow.
5. Record history and release migration locks.

### Async flow
1. Acquire an async connection from the backend pool.
2. Execute queries via `AsyncQuerySet`.
3. Await hydration into model objects.
4. Release the connection back to the pool.

## Non-functional requirements
- Secure defaults for production workloads.
- Clear error reporting and migration rollbacks.
- Maintainable module boundaries and concise public APIs.
- Strong documentation and example coverage.

## Technology assumptions
- Use `uv` for dependency management and developer tasks.
- Prefer built-in drivers and widely used async adapters.
- Keep the package compatible with Python 3.14+.

## Structure validation
- Imports should follow the top-level package shape: `from mikiorm.models import Model`, `from mikiorm.managers import BaseManager`, `from mikiorm.backends import Postgres`.
- The CLI should be discoverable from package entrypoints.
- Migrations should be safe, reversible, and audit-ready.

  - `QueriesPerSecond`, `LatencyHistogram`, `PoolUsageGauge`, `CacheHitRate`
- Logging
  - Structured logs with JSON-friendly fields.
  - Log levels for query execution, migration operations, and connection events.
- Tracing
  - `OpenTelemetryTracer` integration hooks.

## Execution Flows

### Model lifecycle
1. Define model class with fields and optional foreign keys.
2. Register model in global registry via `ModelMeta`.
3. Create migration with schema diff engine.
4. Apply migration to DB.
5. Use manager/queryset API to read/write data.

### Query compilation flow
1. User calls `Model.objects.filter(...)`.
2. Manager returns `QuerySet` with AST.
3. QuerySet calls `compile(dialect)` on iteration or `.all(connection)`.
4. `QueryAST.to_dict()` fingerprints the expression.
5. `compile_cached()` checks LRU cache.
6. Dialect formats SQL and placeholder style.
7. Connection executes parameterized SQL.
8. Rows hydrate into model instances.

### Sync connection flow
1. `ConnectionPool.acquire()` obtains a live connection.
2. `QuerySet.all(connection)` compiles SQL and executes.
3. Results return to caller.
4. `ConnectionPool.release(connection)` returns connection to pool.

### Async connection flow
1. `AsyncConnectionPool.acquire()` gets an async connection.
2. `await AsyncQuerySet.all(connection)` compiles SQL and executes asynchronously.
3. Results hydrate and return.
4. `await AsyncConnectionPool.release(connection)`.

### Migration apply flow
1. Load model registry and current DB schema.
2. Diff schema to create operations.
3. Generate migration file and write metadata.
4. Acquire migration lock.
5. Apply operations inside transaction or backup workflow.
6. On failure, rollback or restore backup.
7. Record migration history and release lock.

### Migration rollback flow
1. Read latest migration metadata.
2. Compute reverse operations.
3. Acquire migration lock.
4. Apply reverse operations in a safe transaction.
5. Update migration history.

## Class Diagrams (Textual)

- `ModelMeta` -> registers -> `Model`
- `Model` -> has many -> `Field`
- `Manager` -> builds -> `QuerySet`
- `QuerySet` -> uses -> `QueryAST`
- `QueryAST` -> compiled by -> `BaseDialect`
- `BaseDialect` -> implemented by -> `PostgresDialect`, `SQLiteDialect`, `MySQLDialect`
- `ConnectionPool` -> provides -> `Connection`
- `AsyncConnectionPool` -> provides -> `AsyncConnection`
- `UnitOfWork` -> tracks -> `Model`
- `Migrations` -> operates on -> `Registry`, `Schema`, `Connection`

## Method Signatures

### Connection interfaces
- `connect(connection_string: str, **options) -> Connection`
- `create_pool(min_size: int, max_size: int, acquire_timeout: float, max_lifetime: float, **options) -> ConnectionPool`
- `execute(sql: str, params: list[Any] | tuple[Any, ...]) -> CursorResult`
- `fetchall(sql: str, params: list[Any] | tuple[Any, ...]) -> list[tuple]`

### Model API
- `Model.save(connection: Connection | AsyncConnection, *, force_insert: bool = False) -> None`
- `Model.delete(connection: Connection | AsyncConnection) -> None`
- `Model.to_dict() -> dict[str, Any]`

### Query API
- `QuerySet.filter(*expressions: Expression) -> QuerySet`
- `QuerySet.order_by(*fields: str) -> QuerySet`
- `QuerySet.select_related(*related: str) -> QuerySet`
- `QuerySet.prefetch_related(*related: str) -> QuerySet`
- `QuerySet.all(connection: Connection) -> list[Model]`
- `QuerySet.all(connection: AsyncConnection) -> Coroutine[list[Model], None, None]`

### Migration API
- `MigrationManager.generate_migration(name: str) -> MigrationFile`
- `MigrationManager.apply(connection: Connection, steps: int | None = None) -> MigrationResult`
- `MigrationManager.rollback(connection: Connection, steps: int = 1) -> MigrationResult`
- `MigrationManager.status(connection: Connection) -> MigrationStatus`

## Dialect Adapters

### Placeholder adaptation
- `SQLiteDialect.placeholder(index)` -> `?`
- `PostgresDialect.placeholder(index)` -> `$1`, `$2`
- `MySQLDialect.placeholder(index)` -> `%s`

### Type mapping
- `UUIDField` -> `UUID` in Postgres, `TEXT` in SQLite, `CHAR(36)` in MySQL.
- `JSONField` -> `JSONB` in Postgres, `TEXT` in SQLite, `JSON` in MySQL.
- `BooleanField` -> `BOOLEAN` or `SMALLINT` depending on dialect.

## Async Pool Design

- `AsyncConnectionPool` should maintain separate min/max size counters.
- Acquire path uses wait queue and timeout.
- Connection validation on checkout and return.
- Automatic connection recycling after `max_lifetime`.
- Optional `max_uses` per connection.
- Support `pool.pre_ping` semantics for idle connections.

## Migration Strategies

### SQLite
- Use `ALTER TABLE` for simple adds when supported.
- For unsupported changes, create a temp table, copy data, drop old table, recreate new schema, restore data.
- Preserve indexes and constraints by introspecting `sqlite_master`.
- Wrap migration in transaction when possible.
- If transaction support is limited, use backup table fallback.

### PostgreSQL
- Use native DDL for adds/renames/nullable changes.
- Use advisory locks via `pg_advisory_lock()` to prevent concurrent migrations.
- Backup data if a destructive operation is needed.
- Write migration metadata with `miki_orm_migrations` history table.

## GitHub Actions and CI Flow

- Workflow triggers on `push` and `pull_request`.
- Matrix runs across supported Python versions.
- Job matrix includes:
  - `sqlite-sync`
  - `postgres-sync`
  - `postgres-async`
- Postgres jobs use `services: postgres` and `docker-compose` if needed.
- Steps:
  1. Checkout code.
  2. Set up Python.
  3. Install `uv` if missing and run `uv install`.
  4. Run `uv run lint`.
  5. Run `uv run test:unit` / `uv run test:integration`.
  6. Generate docs or run docs validation.

## Runbook and Disaster Recovery Notes

- Always back up production data before applying migrations.
- Use `miki-orm migrate --dry-run` to verify operations.
- If migration fails, restore from backup and run `miki-orm migrate rollback`.
- For corruption or failure in SQLite, restore from file copy and re-run migrations against restored data.
- For Postgres, use WAL backup and logical replication if available.

## Notes on `uv`

- Add `uv.lock` to source control for reproducible dependency resolution.
- Use `uv run` for commands rather than ad-hoc script execution.
- Example developer commands:
  - `uv sync`
  - `uv run test`
  - `uv run docs`
  - `uv run lint`

## Open Questions
- Should migrations be JSON-only or support a Python DSL as a later phase?
- How much of Django ORM syntax should be mirrored vs simplified for universality?
- How will connection secrets integration be exposed for desktop/mobile deployments?
