# Events and Health API

## Event registration

- `GET /event/registration-options/` returns the active event, ticket options, and custom questions.
- `POST /event/registrations/` creates a registration for the authenticated member.
- `GET /event/my-tickets/` lists the current member's tickets.
- `POST /event/my-tickets/<id>/resend-email/` resends a ticket email.

## Health and maintenance

- `GET /health/` returns health status, database status, and maintenance messaging.
- `POST /maintenance/bypass/` allows a temporary maintenance bypass when enabled.
- The frontend health provider polls health status and conditionally shows maintenance UI.

## Operational assumptions

- Event display pages still source schedule and archive data from Google Sheets.
- Event registration endpoints remain the only public event write APIs.
- Health endpoints must stay lightweight because they are called from middleware, the SPA, and deployment smoke tests.
