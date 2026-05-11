# Technical Requirements Document (TRD)

## Architecture Overview

### Core design principles
- Modular architecture separated by concern: connections, dialects, models, fields, queries, transactions, migrations, caching, and observability.
- Framework-agnostic API surface so calls are independent of Flask/FastAPI/Django or desktop/mobile frameworks.
- Clear sync/async split through parallel interfaces: sync connection/pool and async connection/pool.
- Pluggable dialect abstraction for database-specific SQL generation and field translation.
- Use of `uv` for package management and developer automation.

## Package Layout

Proposed package layout:

- `miki_orm/`
  - `__init__.py`
  - `connections.py`
  - `dialects.py`
  - `models.py`
  - `fields.py`
  - `managers.py`
  - `query.py`
  - `queryset.py`
  - `unit_of_work.py`
  - `migrations.py`
  - `cache.py`
  - `async_support.py`
  - `security.py`
  - `observability.py`
  - `registry.py`
  - `exceptions.py`

- `tests/`
  - `test_fields.py`
  - `test_query.py`
  - `test_models.py`
  - `test_migrations.py`
  - `test_async.py`
  - `test_integration.py`

- `docs/` (PRD, TRD, quickstart, runbook)
- `.github/workflows/ci.yml`
- `docker-compose.yml`

## Component Design

### Connections

`connections.py`
- `ConnectionManager`
  - `register_adapter(name: str, adapter: Type[BaseAdapter])`
  - `get_connection(name: str) -> BaseConnection`
  - `close_all()`

- `BaseAdapter`
  - `connect(self, dsn: str, **options) -> BaseConnection`
  - `pool(self, **options) -> BasePool`

- `SQLiteSyncAdapter`, `PostgresSyncAdapter`, `MySQLSyncAdapter`
- `SQLiteAsyncAdapter`, `PostgresAsyncAdapter`

- `ConnectionPool`
  - `acquire(timeout: float = 30.0) -> Connection`
  - `release(connection: Connection) -> None`
  - `validate(connection) -> bool`
  - `close()`

### Dialects

`dialects.py`
- `BaseDialect`
  - `paramstyle: str`
  - `placeholder(index: int) -> str`
  - `quote_identifier(name: str) -> str`
  - `type_map: dict[str, str]`
  - `adapt_value(value) -> Any`

- `PostgresDialect(BaseDialect)`
  - placeholders `$1`, `$2`, ...
  - `JSONB`, `UUID`, `TIMESTAMPTZ`

- `SQLiteDialect(BaseDialect)`
  - `?` placeholders
  - fallback mapping for `JSONField`, `UUIDField`

- `MySQLDialect(BaseDialect)`
  - `%s` placeholders
  - MySQL-specific quoting and type mapping

### Models and Fields

`models.py`
- `ModelMeta(type)`
  - `__new__()` registers model classes
  - `resolve_foreign_keys()`
  - `fields` collection and primary key resolution

- `Model`
  - `save(self, connection: Connection | AsyncConnection) -> None`
  - `delete(self, connection: Connection | AsyncConnection) -> None`
  - `to_dict(self) -> dict[str, Any]`
  - `refresh_from_db(self, connection: Connection | AsyncConnection) -> None`

`fields.py`
- `Field`
  - `name: str`
  - `nullable: bool`
  - `default: Any`
  - `python_value(self, raw: Any) -> Any`
  - `db_value(self, python_value: Any) -> Any`

- Concrete field classes
  - `IntegerField`, `CharField`, `BooleanField`
  - `DateTimeField`, `DateField`, `TimeField`
  - `DecimalField`, `JSONField`, `UUIDField`
  - `ForeignKey(to: str | Type[Model])`

### Managers and QuerySets

`managers.py`
- `Manager`
  - `all(self) -> QuerySet`
  - `filter(self, *expressions) -> QuerySet`
  - `exclude(self, *expressions) -> QuerySet`
  - `get(self, *expressions) -> Model`
  - `count(self) -> int`
  - `exists(self) -> bool`
  - `first(self) -> Model | None`
  - `last(self) -> Model | None`
  - `update_or_create(self, defaults: dict, **kwargs)`
  - `bulk_create(self, objs: list[Model], batch_size: int = 1000)`
  - `update(self, **values) -> int`
  - `values(self, *fields) -> list[dict[str, Any]]`
  - `values_list(self, *fields) -> list[tuple[Any, ...]]`
  - `select_related(self, *fields) -> QuerySet`
  - `prefetch_related(self, *fields) -> QuerySet`

`queryset.py`
- `QuerySet`
  - `filter(*expressions) -> QuerySet`
  - `exclude(*expressions) -> QuerySet`
  - `order_by(*fields) -> QuerySet`
  - `annotate(**annotations) -> QuerySet`
  - `select_related(*related) -> QuerySet`
  - `prefetch_related(*related) -> QuerySet`
  - `all(self, connection: Connection) -> list[Model]`
  - `first(self, connection: Connection) -> Model | None`
  - `count(self, connection: Connection) -> int`
  - `exists(self, connection: Connection) -> bool`
  - `__iter__()` / `__await__()` for async execution

## Query Builder

`query.py`
- AST node classes
  - `Eq(field, value)`, `IContains(field, value)`, `In(field, values)`, `Range(field, start, end)`, `Not(expr)`, `And(*exprs)`, `Or(*exprs)`, `OrderBy(field, direction)`
  - `Join(left, right, on)`

- `QueryAST`
  - `to_dict(self) -> dict`
  - `compile(self, dialect: BaseDialect) -> tuple[str, list[Any]]`
  - `compile_cached(self, dialect: BaseDialect) -> tuple[str, list[Any]]`

- LRU cache
  - `compile_cached(ast, dialect)` uses fingerprint key from `to_dict()`
  - cache TTL and maxsize configurable in `cache.py`

## Caching

`cache.py`
- `LRUCache`
  - `get(key: str) -> Any`
  - `set(key: str, value: Any, ttl: timedelta | None = None)`
  - `invalidate(key: str)`
  - `clear()`
- Schema-aware invalidation on migration events.

## Unit of Work

`unit_of_work.py`
- `UnitOfWork`
  - `register_new(obj: Model)`
  - `register_dirty(obj: Model)`
  - `register_deleted(obj: Model)`
  - `commit(connection: Connection) -> None`
  - `rollback() -> None`

- Optimistic locking
  - `version` column support
  - `check_version(obj) -> bool`
  - `retry_on_conflict(func)` hook

## Migrations

`migrations.py`
- Schema diff engine
  - `compare_models_and_schema(models, schema) -> list[MigrationOperation]`

- Migration operations
  - `CreateTable`, `AlterTable`, `DropTable`, `AddColumn`, `AlterColumn`, `DropColumn`, `CreateIndex`, `DropIndex`, `CreateConstraint`, `DropConstraint`

- Migration files
  - JSON or structured YAML-like format with operations, metadata, timestamp, checksum.

- Application flow
  - `migrate.up(connection)`
  - `migrate.down(connection, steps=1)`
  - `migrate.status(connection)`

- SQLite strategy
  - Recreate table with backup preserving indexes and constraints when ALTER is unsupported.
  - Wrap operations in a transaction and use temporary backup tables.

- Postgres strategy
  - Use native `ALTER TABLE` when possible.
  - Fallback to recreate table with data copy and constraint preservation.
  - Advisory locks or lock table to serialize migration runs.

- Safety
  - Backup DDL/data before applying risky changes.
  - Rollback last migration using reverse operations.
  - Audit log migration metadata and change history.

## Async Support

`async_support.py`
- `AsyncConnectionPool`
  - `acquire(timeout: float = 30.0) -> AsyncConnection`
  - `release(connection: AsyncConnection) -> None`
  - `validate(connection) -> bool`
  - `close()`
  - `max_lifetime: float`
  - `min_size`, `max_size`, `acquire_timeout`

- `AsyncQuerySet`
  - `all(self, connection: AsyncConnection) -> Coroutine[list[Model], None, None]`
  - `first(self, connection: AsyncConnection) -> Coroutine[Model | None, None, None]`

- `AsyncAdapter`
  - `connect_async(self, dsn: str, **options) -> AsyncConnection`
  - `pool_async(self, **options) -> AsyncConnectionPool`

- Integration with `asyncpg` and `aiosqlite`.

## Security

`security.py`
- Parameterized SQL only.
- TLS support in adapter configuration.
- Secrets manager adapter interface:
  - `SecretProvider.get_secret(key: str) -> str`
  - `ConnectionConfig.from_secret(name: str)`
- Audit logging for migration and schema changes.
- Least privilege guidance for production DB users.

## Observability

`observability.py`
- Metrics collectors
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
  - `uv install`
  - `uv run test`
  - `uv run docs`
  - `uv run lint`

## Open Questions
- Should migrations be JSON-only or support a Python DSL as a later phase?
- How much of Django ORM syntax should be mirrored vs simplified for universality?
- How will connection secrets integration be exposed for desktop/mobile deployments?
