# Alembic Database Migrations

This directory contains database migration scripts managed by Alembic.

## Setup

1. Initialize Alembic (already done):
   ```bash
   cd api
   alembic init alembic
   ```

2. Configure database URL in `alembic.ini` or via environment variable.

## Usage

### Create a new migration
```bash
alembic revision --autogenerate -m "Description of change"
```

### Apply all pending migrations
```bash
alembic upgrade head
```

### Rollback one version
```bash
alembic downgrade -1
```

### View migration history
```bash
alembic history
```

### View current version
```bash
alembic current
```

## Migrations in Docker

The `deploy.sh` script automatically runs migrations when deploying:
```bash
docker compose exec api alembic upgrade head
```
