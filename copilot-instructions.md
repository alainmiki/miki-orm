# mikiorm Copilot Instructions

## Project summary
`mikiorm` is a universal Django-style ORM for Python. The library should feel familiar to Django users while remaining framework-agnostic, and support both sync and async workflows across SQLite, PostgreSQL, and MySQL in the MVP.

## What this project must prioritize
- A clean top-level package shape with imports like `from mikiorm.models import Model`, `from mikiorm.managers import BaseManager`, and `from mikiorm.backends import Postgres`.
- A CLI management experience that supports `mikiorm makemigrations`, `mikiorm migrate`, `mikiorm check`, `mikiorm dbcheck`, `mikiorm history`, and `mikiorm rollback`.
- Django-style model fields, managers, querysets, and migration semantics.
- Secure, production-ready query execution with parameterized SQL only.
- Clear, documented code and API surface with user-friendly docs and examples.
- `uv` for dependency management and task automation, with `uv.lock` committed.

## Architecture expectations
- Modular packages for `conf`, `cli`, `backends`, `migrations`, `models`, `managers`, `transactions`, `utils`, `cache`, `observability`, and `exceptions`.
- A backend structure that separates `base`, `sqlite`, `postgresql`, `mysql`, `oracle`, and `dummy` implementation details.
- A migration engine capable of diffing model definitions vs. database schema, generating migration files, and applying/rolling back with safety.
- A configuration layer for engine, credentials, pooling, TLS, and secret resolution.
- Sync and async adapters with a shared model metadata layer.

## API expectations
- Model definitions should feel natural and support field access as attributes on instances.
- Manager methods should include `all()`, `filter()`, `exclude()`, `get()`, `count()`, `exists()`, `first()`, `last()`, `update_or_create()`, `bulk_create()`, `update()`, `values()`, `values_list()`, `select_related()`,`delete()`,'`aggregate()`, `annotate()`,`get_or_create()`,`get_object_or_404`,`sum`, and `prefetch_related()`.
- QuerySets should be lazy and support both synchronous execution and async execution with `await`.
- Core fields should include `AutoField`, `IntegerField`, `BigIntegerField`, `CharField`, `TextField`, `BooleanField`, `DateTimeField`, `DateField`, `TimeField`, `DecimalField`, `JSONField`, `UUIDField`, `ForeignKey`, `OneToOneField`, `ManyToManyField`, `BinaryField`, `EmailField`, and `URLField`.

## Configuration requirements
- Provide a unified settings module with `DATABASES`, `DEFAULT_DATABASE`, `INSTALLED_APPS`, `MIGRATION_PATH`, `LOGGING`, and environment overrides.
- Support Django-style database dictionaries with `ENGINE`, `NAME`, `USER`, `PASSWORD`, `HOST`, `PORT`, `OPTIONS`, `SSL`, `POOL`, and `SECRETS`.
- Allow secure secret retrieval and environment-driven config.

## Security requirements
- Parameterized SQL must be enforced everywhere.
- Avoid raw string query composition.
- Support TLS/SSL configuration and secret manager integration.
- Add audit logging for migration execution and schema changes.
- Build connection pooling, retries, and validation with production defaults.

## Documentation expectations
- Public modules, classes, and functions should include descriptive docstrings.
- The README and docs should cover package setup, configuration, model definition, migrations, CLI usage, and examples.
- Examples must demonstrate real-world patterns like CRUD, relations, select-related/prefetch-related, and migrations.

## CI and conventions
- Use GitHub Actions to run linting, formatting, and tests across Python versions.
- Maintain branch naming and PR conventions: `feature/`, `bugfix/`, `chore/`.
- Ensure `uv run` commands are available for linting, testing, and docs generation.

## Implementation guidance
- Use the desired package structure from `structure.md` as the basis for refactoring.
- Keep backend implementations isolated and engine-specific behavior in dedicated submodules.
- Treat migrations as first-class functionality: generation, apply, history, and rollback.
- Prefer explicit, safe behavior over convenience shortcuts.

## What to avoid
- Do not build features only for a single backend unless they can be extended to SQLite, Postgres, and MySQL.
- Do not bypass parameter binding or compose SQL by concatenating user input.
- Do not assume the package is tied to Django; keep the API framework-agnostic.
- Do not use terminal file operations for restructuring; prefer Python-based refactoring when moving files.
