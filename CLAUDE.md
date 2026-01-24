# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **cloud storage/file management application** built with Django 5.2. Users access their files through native OS file browsers (macOS Finder, iOS Files app, Windows File Explorer) via SFTP/WebDAV protocols. Files are stored in S3-compatible storage (MinIO for development, S3 for production), with metadata and tagging managed through Django models.

**What makes this unique**: Custom SFTP/WebDAV server bridges native OS file access with Django ORM and S3 storage, enabling rich metadata (tags, search) while maintaining familiar file browsing experience.

For product requirements and architecture decisions, see **[APPMANIFEST.md](APPMANIFEST.md)**.

This project follows strict code quality standards enforced by wemake-python-styleguide, ruff, and mypy.

**Key technologies:**
- Python 3.12.11 (use pyenv)
- Django 5.2 with PostgreSQL 18
- S3-compatible storage (MinIO/S3) via django-storages
- SFTP/WebDAV protocol server (TBD: WsgiDAV or paramiko)
- Poetry for dependency management
- Docker/Docker Compose for containerization
- pytest for testing with 100% coverage requirement

**Dependencies**: See `pyproject.toml` for full list. Key packages: django-storages, boto3, python-magic, moto (testing).

## Development Commands

**IMPORTANT: Backend Command Execution**

All backend-related commands (Django management commands, Poetry dependency management, database operations, testing, etc.) **MUST** be executed inside the Docker Compose container using:

```bash
docker compose exec web <command>
```

**Examples:**
- `docker compose exec web python manage.py migrate`
- `docker compose exec web poetry add package-name`
- `docker compose exec web pytest tests/`
- `docker compose exec web python manage.py createsuperuser`

This ensures commands run in the correct environment with all dependencies and services (database, MinIO, etc.) available. The `--rm` flag automatically removes the container after execution.

**Exception**: Local development setup commands (if not using Docker) can be run directly on the host machine.

### Initial Setup (Docker)

```bash
# Start all services (automatically loads docker-compose.override.yml)
docker compose up

# Run migrations in container
docker compose run --rm web python manage.py migrate

# Execute any command in container
docker compose run --rm web <command>
```

### Testing

**Note**: Run all test commands inside Docker container.

```bash
# Run all tests with coverage (requires 100% coverage)
docker compose run --rm web pytest

# Run specific test file
docker compose run --rm web pytest tests/test_main.py

# Run specific test
docker compose run --rm web pytest tests/test_main.py::test_function_name

# Run tests without coverage (faster)
docker compose run --rm web pytest --no-cov
```

All tests have a 5-second timeout (configured in setup.cfg). Tests run with random order via pytest-randomly for better reliability.

### Code Quality

**Note**: Code quality tools can be run locally (faster) or in Docker container. For consistency, prefer Docker.

```bash
# Run ruff linter
docker compose run --rm web ruff check .
# Or locally: ruff check .

# Run ruff formatter
docker compose run --rm web ruff format .
# Or locally: ruff format .

# Run type checking
docker compose run --rm web mypy server/ tests/
# Or locally: mypy server/ tests/

# Run wemake-python-styleguide
docker compose run --rm web flake8
# Or locally: flake8

# Lint Django templates
docker compose run --rm web djlint server/ --check
# Or locally: djlint server/ --check

# Format Django templates
docker compose run --rm web djlint server/ --reformat
# Or locally: djlint server/ --reformat

# Lint YAML files
docker compose run --rm web yamllint .
# Or locally: yamllint .

# Check dependencies for security issues
docker compose run --rm web safety check
# Or locally: safety check

# Lint .env files
docker compose run --rm web dotenv-linter config/
# Or locally: dotenv-linter config/
```

### Database Management

**Note**: Run all Django management commands inside Docker container.

```bash
# Create migrations
docker compose run --rm web python manage.py makemigrations

# Apply migrations
docker compose run --rm web python manage.py migrate

# Check for migration issues
docker compose run --rm web python manage.py lintmigrations

# Create Django superuser
docker compose run --rm web python manage.py createsuperuser
```

### Dependency Management

**Note**: Run all Poetry commands inside Docker container to ensure consistency.

```bash
# Add production dependency
docker compose run --rm web poetry add package-name

# Add development dependency
docker compose run --rm web poetry add -G dev package-name

# Add docs dependency
docker compose run --rm web poetry add -G docs package-name

# Update dependencies
docker compose run --rm web poetry update

# Export requirements (rarely needed)
docker compose run --rm web poetry export -f requirements.txt --output requirements.txt
```

After adding dependencies, rebuild the Docker image:
```bash
docker compose build web
```

## Architecture

### Settings Architecture (django-split-settings)

Settings are split across multiple files in `server/settings/`:
- `components/common.py` - Base Django settings
- `components/logging.py` - Structured logging with structlog
- `components/csp.py` - Content Security Policy configuration
- `components/caches.py` - Cache configuration
- `environments/development.py` - Development environment
- `environments/production.py` - Production environment
- `environments/local.py` - Optional local overrides (not committed)

Environment is controlled via `DJANGO_ENV` variable (defaults to "development").

### Application Structure

Django apps live in `server/apps/`. Each app follows this structure:
- `models.py` - Database models
- `views.py` - View functions/classes
- `urls.py` - URL routing
- `admin.py` - Django admin configuration
- `logic/` - Business logic (domain layer)
- `infrastructure/` - External integrations
- `templates/` - App-specific templates
- `static/` - App-specific static files
- `migrations/` - Database migrations

### URL Routing

Main URL configuration is in `server/urls.py`. It includes:
- App URLs via `include()` (e.g., `main/` namespace)
- Health checks at `/health/`
- Django admin at `/admin/`
- Admin documentation at `/admin/doc/`
- Static text files (robots.txt, humans.txt)
- Debug toolbar in development mode

### Key Design Decisions

Critical architectural constraints to respect when implementing features:

1. **Multi-user isolation**: User ID is first path component (`{user.id}/folder/file.ext`). Always filter queries by user. Protocol server validates user owns paths.

2. **Shared database**: Protocol server and Django share PostgreSQL, import models directly. Use database-level constraints and transactions to avoid race conditions.

3. **Transaction safety**: Upload = S3 first, DB second (rollback S3 on failure). Delete = DB first, S3 second (cleanup job for orphans). Never leave inconsistent state.

4. **No Folder model**: Folders implicit from `storage_path` field. List with `storage_path__startswith`. Don't create Folder records.

5. **Storage abstraction**: Use Django storage backend, never boto3 directly in business logic. Config switches MinIO (dev) / S3 (prod) via `STORAGES['default']`. Storage ops in `infrastructure/` layer.

6. **Authentication**: Direct Django password auth initially. Protocol server validates against User model. App-specific passwords deferred to Phase 2.

For detailed file operations, data models, and architecture, see **[APPMANIFEST.md](APPMANIFEST.md)**.

## Code Style Requirements

This project uses **extremely strict** linting:

1. **Line length**: 80 characters maximum
2. **Complexity**: McCabe complexity max 6
3. **Quotes**: Single quotes for Python strings
4. **Type hints**: Required on all functions (mypy strict mode)
5. **Docstrings**: Google-style docstrings (though not required on all functions per ruff config)
6. **Import order**: Managed by ruff isort
7. **Final classes**: Use `@final` decorator for classes that shouldn't be subclassed
8. **Override methods**: Use `@override` decorator when overriding parent methods

### Common Patterns

**Model constants:**
```python
from typing import Final

_CONSTANT_NAME: Final = value
```

**Model class structure:**
```python
from typing import final, override

@final
class MyModel(models.Model):
    """Model docstring."""

    field = models.CharField(max_length=255)

    class Meta:
        verbose_name = 'MyModel'  # type: ignore[mutable-override]

    @override
    def __str__(self) -> str:
        """String representation."""
        return self.field
```

### Ignored Linting Rules

Some rules are intentionally ignored (see pyproject.toml):
- Django migration files: line length and docstrings
- `server/settings/` files: specific WPS rules for configuration
- Test files: WPS432 (magic numbers) and S101 (assert)

## Environment Variables

Configuration is loaded from `config/.env` using python-decouple. Use `config/.env.template` as reference for required variables.

Key variables:
- `DJANGO_ENV` - Environment name (development/production)
- `DJANGO_SECRET_KEY` - Django secret key
- `DJANGO_DATABASE_HOST` - Database host
- Database credentials (POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD)

## Testing Requirements

- **Coverage**: 100% required (--cov-fail-under=100)
- **Timeout**: 5 seconds per test
- **Django**: Use pytest-django fixtures and helpers
- **Migrations**: Test with django-test-migrations
- **Templates**: Tests fail on undefined template variables (--fail-on-template-vars)

Coverage config includes django_coverage_plugin for template coverage.

**S3 Testing**: Use `moto` to mock S3 (never make real S3 calls). Use `@mock_aws` decorator, create mock buckets before tests. Mock S3 underneath Django storage backend, not the storage backend itself.

## Docker

Development uses multi-stage Dockerfile at `docker/django/Dockerfile`:
- `development_build` target for local development
- Separate production target
- Health checks configured in docker-compose.yml
- Postgres 18 in separate container with health checks
- Shared networks: `postgres-net` for database access, `web-net` for internal services
