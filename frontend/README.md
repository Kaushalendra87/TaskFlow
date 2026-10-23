# TaskFlow frontend

This is the React 18, TypeScript, and Vite frontend for TaskFlow. It calls the Django API and connects to the Django Channels WebSocket endpoint on port 8000 during local development.

From this directory:

```bash
npm ci
npm run dev
```

The development server normally opens at `http://localhost:3000`. Vite proxies `/api`, `/media`, and `/ws` requests to Django. For backend setup, Redis requirements, tests, and configuration, see the [project README](../README.md).

Optional local frontend overrides belong in `.env.local`; do not put secrets in `VITE_*` variables because they are embedded in browser code.
