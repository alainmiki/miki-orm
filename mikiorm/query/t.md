## Plan

I’ve mapped the requested fix list to the current repo structure and the files that need the most work. Below is a concrete implementation plan, broken down by area.

---

## 1. Complete Query / SQL safety

### What to implement
- central SQL builder / compiler
- safe identifier quoting
- Django-style lookups
- remove raw table/column interpolation

### Files
- builder.py
- compiler.py
- queryset.py
- base.py
- base.py

### Tasks
- Create a `SQLCompiler` / `QueryBuilder` that:
  - quotes identifiers for SQLite/Postgres/MySQL
  - normalizes placeholders by dialect
  - only assembles SQL from safe pieces
- Replace raw SQL string building like `f"INSERT INTO {table}"` with helper methods that quote names
- Implement lookup parsing in `QuerySet.filter()`:
  - `field=value`
  - `field__gt=value`, `field__lt=value`, `field__gte`, `field__lte`
  - `field__in=[...]`
  - `field__icontains=value`, `field__contains=value`
  - `field__startswith`, `field__endswith`
- Ensure `QuerySet.update()`, `.delete()`, `.count()`, `.values()`, `.values_list()` use the same safe builder

---

## 2. Finish migration engine

### What to implement
- real schema diffing
- alter-table operations
- reversible migrations
- transactional apply/rollback
- migration locking

### Files
- engine.py
- operations.py
- history.py
- possibly add `myorm/migrations/schema.py`

### Tasks
- Add schema introspection for each adapter:
  - existing tables
  - columns
  - indexes
  - null/default constraints
- Compare registry model metadata to DB schema
- Generate operations:
  - `CreateTable`
  - `AddField`
  - `AlterField`
  - `DropField`
  - `CreateIndex`
  - `DropIndex`
- Add `reversible()` or reverse SQL for each operation
- Use DB transactions during migrate / rollback
- Add migration lock table/mechanism to prevent concurrent runs
- Replace file-removal rollback with reverse operation execution

---

## 3. Integrate unit of work / transactions

### What to implement
- wire transaction manager into model persistence
- atomic batch operations

### Files
- base.py
- transaction.py
- commit.py
- tracker.py

### Tasks
- Add `transaction.atomic()` context manager
- In `Model.save()` and `Model.delete()`, use `TransactionManager` if no connection passed
- Register objects in `UnitOfWorkTracker` on create/update/delete
- Commit/during transaction with `CommitManager`
- Ensure rollback clears state and rolls back DB transaction

---

## 4. Build async support

### What to implement
- async adapters
- `AsyncQuerySet`
- async tests/docs

### Files
- add `myorm/async_support/*` or `myorm/connections/async_*.py`
- queryset.py
- base.py
- __init__.py

### Tasks
- Add `AsyncConnection` interface and async adapter implementations for:
  - SQLite (`aiosqlite`)
  - PostgreSQL (`asyncpg`)
- Create `AsyncQuerySet` with `async def all()`, `async def get()`, etc.
- Update manager to expose `objects.async_all()` or a separate `async_objects`
- Add async support to the docs and test suite
- Ensure safe parameter binding in async path

---

## 5. Harden configuration

### What to implement
- validate database settings
- real `MIGRATION_PATH` and `LOGGING`
- TLS/secret enforcement

### Files
- settings.py
- __init__.py
- README/docs

### Tasks
- Add config schema validation in `settings.configure()`
- Add first-class `DEFAULT_DATABASE`, `INSTALLED_APPS`, `MIGRATION_PATH`, `LOGGING`
- Implement `SSL`, `POOL`, `SECRETS` handling in `DatabaseConfig.get_connection_config()`
- Add TLS enforcement support in `PostgresAdapter` and `MySQLAdapter`
- Add config docs and examples

---

## 6. Implement relationship support

### What to implement
- real FK/M2M functionality
- join queries and related hydration
-  onetoone relationship

### Files
- relationships.py
- builder.py
- queryset.py
- engine.py

### Tasks
- Make `ForeignKey`, `OneToOneField`, `ManyToManyField` carry enough metadata
- Generate FK columns and M2M join tables in migrations
- Add query join support for `select_related()` and `prefetch_related()`
- Hydrate related objects in returned model instances

---

## 7. Add observability / audit logging

### What to implement
- structured logging
- audit events for migrations/query execution

### Files
- logging.py
- engine.py
- query execution paths

### Tasks
- Remove all `print()` debug statements
- Use `get_logger()` for DB, migration, and transaction events
- Log migration generation, apply, rollback
- Add hooks for query latency and execution metrics

---

## 8. Expand tests/CI

### What to implement
- unit tests
- integration tests
- async coverage

### Files
- `tests/test_query.py`
- test_migrations.py
- `tests/test_transactions.py`
- perhaps `tests/test_async.py`
- uv.toml and GitHub workflow updates

### Tasks
- Add test cases for lookup operators, SQL safety, and query compilation
- Add migration generation/apply/rollback tests against SQLite and Postgres
- Add async tests after async path is built
- Add CI matrix coverage for target Python versions/backends

---

## Execution notes

I cannot directly modify files from this Ask-only session, but I can give you the exact patch plan or help turn any one of the above areas into code changes step-by-step.

### Recommended next step
Start with **Query / SQL safety** first. That fixes the foundation and reduces risk for every other area.

If you want, I can now produce the exact code design for `QueryBuilder` + lookup operators and the first patch set for builder.py, compiler.py, and queryset.py.