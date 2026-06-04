#!/bin/sh

# Exit immediately if a command exits with a non-zero status.
set -e

echo "Waiting for database to be ready..."
# The healthcheck in docker-compose handles this, but an extra check here is good practice.
# This script assumes pg_isready is available in the container. If not, this part can be removed.

echo "Running database migrations..."
alembic upgrade head

echo "Starting server..."
# The 'exec' command is important, it replaces the shell process with the uvicorn process,
# allowing it to receive signals correctly (like CTRL+C).
exec uvicorn app.interfaces.main:app --host 0.0.0.0 --port 8000 --reload