# Production Architecture

## Backend

- Backend deploys to AWS ECS Fargate from the Docker image built in `src/`.
- Production commonly uses PostgreSQL, Redis, S3-compatible static storage, and environment-managed secrets.
- Health and CORS smoke checks remain part of deployment validation.

## Frontend

- Frontend deploys to AWS Amplify from the Vite build output in `pages/dist/`.
- `VITE_API_BASE_URL` points the SPA at the production backend.

## Environment areas

- Django secret key and host/origin settings
- Database connection settings
- Redis URL
- SES and Gmail credentials
- Google Sheets credentials or API key
- Storage bucket configuration
