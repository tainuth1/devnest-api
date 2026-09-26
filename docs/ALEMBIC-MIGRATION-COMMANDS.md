```
# Apply all pending migrations (run after any new migration file)
docker exec dev-nest-api-api-1 alembic upgrade head

# Check what revision the DB is currently at
docker exec dev-nest-api-api-1 alembic current

# View full migration history
docker exec dev-nest-api-api-1 alembic history --verbose

# Roll back one step
docker exec dev-nest-api-api-1 alembic downgrade -1

# Roll back to a specific revision
docker exec dev-nest-api-api-1 alembic downgrade 002_session_auth\
```
