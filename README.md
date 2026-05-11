# miki-orm

Universal Django-style ORM for Python applications.

## Repository layout

- `myorm/` — ORM package with Django-style models, fields, managers, migrations, and adapters.
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
GitHub Actions CI is configured in `.github/workflows/ci.yml` and validates SQLite, PostgreSQL, and async scenarios.
