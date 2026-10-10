# Migrations (scaffold)

Alembic migrations for the PAZUZU-API v2.0 Postgres schema. The backend
agents will generate real revision scripts here once the models are defined.

Current state:

- `alembic.ini` — scaffold stub. The `sqlalchemy.url` and `script_location`
  entries must be filled in when the first real migration is written.

Do not apply anything from this directory until the schema contracts are
finalized.
