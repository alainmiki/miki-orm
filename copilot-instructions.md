# miki-orm Copilot Instructions

## Project summary
`miki-orm` is a universal Django-style ORM library for Python. It must support sync and async database access, provide a familiar Django-like API, and work across SQLite, PostgreSQL, and MySQL in the MVP.

## What this project must prioritize
- Django-style model fields and manager/queryset methods.
- `makemigrations` to generate migration definitions and `migrate` to apply them, matching Django semantics.
- Unified database configuration and settings that feel like Django `settings.py`.
- Production-grade security and scalability features.
- Clean, documented code with strong API documentation and developer guidance.
- `uv` for dependency management and task execution, with `uv.lock` committed.

## Key architecture expectations
- Modular packages for `connections`, `dialects`, `models`, `fields`, `managers`, `query`, `queryset`, `migrations`, `unit_of_work`, `cache`, `async_support`, `security`, and `observability`.
- A dialect layer supporting SQLite, PostgreSQL, and MySQL by default.
- A migration engine that can diff model definitions and database schema, generate migration files, and apply/rollback safely.
- A configuration API for setting database engine, credentials, connection pooling, TLS, and secrets lookup.
- Strong support for parameterized queries and schema-safe operations.

## API and developer experience
- Model definitions should feel familiar to Django users.
- Manager methods should include the full Django-like set: `all`, `filter`, `exclude`, `get`, `count`, `exists`, `first`, `last`, `update_or_create`, `bulk_create`, `update`, `values`, `values_list`, `select_related`, `prefetch_related`.
- QuerySets should be lazy and support both sync `.all(connection)` and async `await .all(connection)`.
- Field classes should include Django-style names and conversions: `AutoField`, `IntegerField`, `BigIntegerField`, `CharField`, `TextField`, `BooleanField`, `DateTimeField`, `DateField`, `TimeField`, `DecimalField`, `JSONField`, `UUIDField`, `ForeignKey`, `OneToOneField`, `ManyToManyField`, `BinaryField`, `EmailField`, `URLField`, etc.

## Configuration and settings
- Provide a universal settings module or config object with keys like `DATABASES`, `DEFAULT_DATABASE`, `INSTALLED_APPS`, `MIGRATION_PATH`, and `LOGGING`.
- Support dictionary-based database configuration similar to Django:
  - `ENGINE` (`sqlite`, `postgresql`, `mysql`)
  - `NAME`, `USER`, `PASSWORD`, `HOST`, `PORT`
  - `OPTIONS`, `SSL`, `POOL`, `SECRETS`
- Allow environment-driven overrides and secure secret retrieval.

## Security and production readiness
- Use only parameterized queries; never build SQL via string interpolation.
- Support TLS-enabled connections and secret manager integration.
- Include audit logging for migrations and schema changes.
- Design connection pooling, retries, timeouts, and validation around production workloads.
- Make scalability and safety the default.

## Documentation expectations
- Every module, class, and public function should include clear docstrings.
- The README and docs must explain setup, configuration, model definition, migrations, and CLI usage.
- Code should be easy to navigate and maintain.

## CI and repository conventions
- Use GitHub Actions for CI, with matrix coverage for Python versions and database scenarios.
- Keep branch naming and PR conventions structured: `feature/`, `bugfix/`, `chore/`.
- Ensure `uv` commands are available for linting, testing, and docs.

## When working on this repository
- Respect the Django-inspired design while keeping the ORM framework-agnostic.
- Make sure any feature supports the MVP target databases before claiming readiness.
- Prefer explicit, safe behaviors over convenience hacks.
- Document new APIs and configuration options as part of the change.

## What to avoid
- Don’t implement database support only for one backend if the feature cannot work for SQLite, Postgres, and MySQL.
- Don’t bypass parameter binding or build SQL with raw string composition.
- Don’t assume the project is Django-specific; it must remain generic and adaptable.
