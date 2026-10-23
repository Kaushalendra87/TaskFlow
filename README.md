# TaskFlow

TaskFlow is a local-first CSV job processing application. It uses Django REST Framework and Django Channels for the API and live updates, Celery for background processing, Redis for the task queue and channel layer, and React/Vite for the web interface.

## Requirements

- Python 3.12 or newer
- Node.js 18 or newer and npm
- Docker with Docker Compose, or a locally installed Redis 7+

The default development database is SQLite. PostgreSQL is optional.

## Run locally

Run each long-lived process in its own terminal from the project root.

### 1. Start Redis

With Docker:

```bash
docker compose up -d redis
```

Alternatively, start a local Redis 7+ server and leave it running.

### 2. Set up the backend

Linux/macOS:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver 8000
```

Windows PowerShell:

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py runserver 8000
```

The Django development server uses Daphne (installed by the project) to serve the ASGI application and WebSockets.

### 3. Start the Celery worker

Open another terminal:

```bash
cd backend
```

Activate the backend virtual environment as above, then run:

```bash
celery -A config worker --loglevel=info
```

Keep this worker running while submitting jobs. Redis stores queued jobs, but
the worker is what actually reads and processes the uploaded CSV files. Running
Celery Beat alone does not process jobs.

Uploads must be comma-separated `.csv` files with a header row and UTF-8
encoding. UTF-8 files with a BOM and Windows-style line endings are supported.

Celery Beat is only needed for scheduled daily summaries and runs in a separate
terminal:

```bash
celery -A config beat --loglevel=info
```

### 4. Set up the frontend

Open another terminal:

```bash
cd frontend
npm ci
```

The Vite configuration proxies API, media, and WebSocket traffic to Django on port 8000. The checked-in `.env.example` is optional; copy it to `.env.local` only if you need to override the WebSocket URL:

```bash
cp .env.example .env.local
npm run dev
```

Open the URL printed by Vite (normally `http://localhost:3000`).

## Configuration

Backend settings are read from `backend/.env`. The example file selects SQLite and local Redis so a fresh checkout does not require cloud credentials.

- `DJANGO_DEBUG`: development mode; keep enabled only for local development.
- `DJANGO_SECRET_KEY`: optional for local development; set a unique, private value for any non-debug deployment.
- `DJANGO_ALLOWED_HOSTS`: comma-separated hostnames for the backend.
- `DB_ENGINE`: `sqlite` by default; set to `postgresql` to use the PostgreSQL variables below.
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_SSLMODE`: PostgreSQL connection settings.
- `REDIS_URL`: Redis URL used by Celery and Channels.

To create a Django secret key for a deployment, run `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` in the backend environment, then store the result in your deployment's secret manager or private environment configuration. Do not commit it.

Frontend variables must not contain secrets because Vite embeds `VITE_*` values in browser code. `VITE_WS_URL` defaults to `ws://127.0.0.1:8000` for local development.

## Tests and production build

```bash
cd backend
python manage.py check
python manage.py test users jobs realtime config
```

```bash
cd frontend
npm run build
```

For a deployment, configure a production ASGI server, HTTPS/WSS, a private `DJANGO_SECRET_KEY`, production `DJANGO_ALLOWED_HOSTS`, a managed PostgreSQL database and Redis service, and static/media storage. Set `DJANGO_DEBUG=False`; the backend refuses to start in that mode without a non-development secret key. Do not use the development server as a production server.

## Example CSV files

The `sample_csv/` directory contains small sample task, customer, inventory, and order CSVs for trying the upload flow. These are examples, not required application data.
# TaskFlow
