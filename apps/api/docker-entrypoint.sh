#!/bin/sh
set -e

# With arguments, run them instead of the server — this is how the ECS
# one-off migration task works (command: alembic upgrade head), and how
# any future operational one-off (a shell, a script) runs against the
# production image without a special build.
if [ "$#" -gt 0 ]; then
    exec "$@"
fi

# Startup migrations default ON so local development and docker-compose
# keep their existing single-container behavior unchanged. Production
# ECS sets RUN_MIGRATIONS_ON_STARTUP=false: with multiple/rolling API
# tasks, per-task startup migrations would race each other — migrations
# there run once, as an explicit one-off ECS task, BEFORE the service
# rolls (docs/aws-deployment.md, "Deploy flow").
if [ "${RUN_MIGRATIONS_ON_STARTUP:-true}" = "true" ]; then
    alembic upgrade head
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
