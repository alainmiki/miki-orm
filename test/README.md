# miki-orm Test Suite

## Overview

The test suite is located in `tests/` with the following structure:

```
tests/
├── conftest.py           # pytest configuration and fixtures
├── unit/
│   ├── __init__.py
│   ├── test_core_fields.py    # all field types, CRUD
│   ├── test_relationships.py  # FK, M2M, on_delete behaviors
│   ├── test_queryset.py       # filters, ordering, aggregation, values, get_object_or_404
│   ├── test_transactions.py   # sync atomic and async_atomic
│   ├── test_async_crud.py     # async model operations
│   └── test_migrations.py     # migration engine operations
└── integration/
    └── test_all_backends.py  # comprehensive integration tests (WIP)
```

## Running Tests

First install dependencies:

```bash
pip install -r requirements.txt
```

For PostgreSQL tests, ensure a local database is running:

```bash
# Using Docker
docker-compose up -d
```

Run tests against both backends (SQLite + PostgreSQL if available):

```bash
python run_tests.py                # all tests
python run_tests.py --unit-only    # unit test modules only
python run_tests.py --async-only   # only async tests
python run_tests.py --migrations   # include migration tests
```

Select a specific backend:

```bash
python run_tests.py --backend=sqlite      # only SQLite (default)
python run_tests.py --backend=postgres    # only PostgreSQL
```

## Test Environment Variables

No special environment variables required. The PostgreSQL config is hard-coded in test fixtures:

- Database: `miki_orm_test`
- User: `postgres`
- Password: `admin`
- Host: `localhost`
- Port: `5432`

Update these in the test files if your setup differs.

## What’s Covered

- **Field types**: Char, Text, Boolean, Integer, BigInteger, SmallInteger, PositiveInteger, PositiveSmallInteger, Float, Decimal, DateTime, Date, Time, Duration, UUID, JSON, Binary, Email, URL, Slug, GenericIPAddress, FilePath
- **Relationships**: ForeignKey with CASCADE, SET_NULL, SET_DEFAULT, PROTECT, DO_NOTHING; ManyToManyField through auto-generated join table
- **QuerySet API**: `all`, `first`, `last`, `count`, `exists`, `get`, `filter`, `exclude`, `order_by`, `values`, `values_list`, `get_or_create`, `update_or_create`, `update`, `delete`, `bulk_create`
- **Transactions**: sync `atomic()`, async `async_atomic()`, nesting, rollback on exception, UnitOfWork tracking
- **Migrations**: schema introspection, diff generation, operation creation (CreateTable, AddField, AlterField, DropField, CreateIndex, DropIndex, RenameField, DeleteTable), apply and rollback
- **Edge cases**: null vs empty string, default values, unique constraints, positive integer enforcement, decimal rounding, JSON storage, binary data, auto timestamps, UUID primary keys

## pytest Configuration

`pytest.ini` sets `asyncio_mode = auto` so async tests run without explicit loop fixtures in most cases.

## Notes

- Some DB-specific behavior (e.g., PostgreSQL vs SQLite) is exercised via parametrized fixtures; both backends run all applicable tests.
- Async tests use `pytest-asyncio` and the `@pytest.mark.asyncio` marker.
- The test suite self-creates tables using Model._ensure_table_exists() in fixtures.
