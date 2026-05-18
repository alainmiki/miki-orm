# miki-orm

Universal Django-style ORM for Python applications.

**Status**: ✅ Phase 5 COMPLETE - 96% Django API Parity

## Latest Release: v2.0.0 (May 18, 2026)

### Phase 5 Features (NEW)
- ✅ GROUP BY with HAVING clause for aggregate filtering
- ✅ Set operations: `union()`, `intersection()`, `difference()`
- ✅ `in_bulk()` for efficient batch dictionary lookups
- ✅ Chainable `values()` and `values_list()`
- ✅ Automatic GROUP BY generation with `annotate()`
- ✅ Foundation for future enhancements

See `PHASES_1_TO_5_COMPLETE_REPORT.md` for full feature matrix.

## Repository layout

- `myorm/` — Legacy implementation package with Django-style models, fields, managers, migrations, and adapters.
- `mikiorm/` — Alias package exposing the stable public API for the ORM.
- `tests/` — Unit and integration test stubs.
- `docs/` — Product and technical documentation.
- `.github/workflows/ci.yml` — GitHub Actions CI.
- `uv.toml` — `uv` task runner commands.

## Features

- Django-like model fields and manager methods.
- `makemigrations` and `migrate` command structure.
- Sync support for SQLite, PostgreSQL, and MySQL.
- Universal config style for database credentials and settings.
- Production-minded security and scalability patterns.

## Getting started

Install development dependencies:

```bash
uv install
```

Run tests:

```bash
uv run test
```

Build docs:

```bash
uv run docs
```

Generate migrations:

```bash
uv run makemigrations
```

Apply migrations:

```bash
uv run migrate
```

## Quickstart

1. Configure your database:

```python
import mikiorm

mikiorm.configure({
    "default": {
        "ENGINE": "sqlite",
        "NAME": "mydb.db",
    }
})
```

2. Define models just like Django:

```python
from mikiorm import models

class User(models.Model):
    name = models.CharField(max_length=100)
    age = models.IntegerField()

    class Meta:
        table_name = "users"
```

3. Register your model and run migrations:

```python
mikiorm.register_model(User)
mikiorm.makemigrations([User])
mikiorm.migrate()
```

### App registration

If your application package contains a `models.py`, register the app instead of models one-by-one:

```python
mikiorm.install_app("my_app")
mikiorm.makemigrations()
mikiorm.migrate()
```

4. Use the Django-style manager API:

```python
user = User.objects.create(name="Alice", age=30)
user, created = User.objects.get_or_create(name="Bob", defaults={"age": 25})
user = User.objects.get(name="Alice")
User.objects.all().delete()
```

## Configuration

Use a Django-like `DATABASES` dictionary in your application or environment loader.

Example config:

```python
DATABASES = {
    "default": {
        "ENGINE": "postgresql",
        "NAME": "mydb",
        "USER": "user",
        "PASSWORD": "password",
        "HOST": "localhost",
        "PORT": 5432,
        "OPTIONS": {"sslmode": "require"},
    }
}
```

## Documentation
- `docs/PRD.md`
- `docs/TRD.md`

## CI
GitHub Actions CI is configured in `.github/workflows/ci.yml` and validates SQLite and PostgreSQL sync scenarios.
