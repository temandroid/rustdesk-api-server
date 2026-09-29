FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .

# The container runs as the user set in docker-compose (the deploy user), so
# the database it creates on the host belongs to that user
ENV DB_PATH=/app/db/db.sqlite3 \
    HOME=/tmp
EXPOSE 21114
CMD ["gunicorn", "rustdesk_server_api.wsgi:application", "--bind", "0.0.0.0:21114", "--workers", "2", "--access-logfile", "-"]
