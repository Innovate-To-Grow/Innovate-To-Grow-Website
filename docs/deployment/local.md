# Local Development

## Prerequisites

- Python 3.11+
- Node.js 20+
- npm
- Docker if you want to validate the backend image locally

## Backend

1. Create and activate a virtual environment.
2. Install dependencies with `pip install -r src/requirements.txt`.
3. Run migrations with `python src/manage.py migrate`.
4. Start Django with `python src/manage.py runserver`.

## Frontend

1. Install packages with `cd pages && npm ci`.
2. Start Vite with `npm run dev`.
3. The frontend uses `/api` and relies on the Vite proxy in development.

## Full-stack check

- Run backend tests with `python src/manage.py test --settings=core.settings.dev`.
- Run frontend checks with `npm run lint`, `npx tsc --noEmit`, and `npm run build`.
