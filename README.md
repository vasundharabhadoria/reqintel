# ReqIntel

ReqIntel is an AI-powered enterprise requirement intelligence platform designed to help teams manage, analyze, and understand software requirements more effectively.

The platform aims to provide a centralized workspace where requirements can be collected, structured, analyzed, and tracked throughout the software development lifecycle. It combines requirement management with intelligent analysis to help identify inconsistencies, ambiguities, dependencies, and other issues that may affect project quality.

## Overview

Software projects often involve requirements coming from multiple stakeholders and evolving throughout development. Managing these requirements manually can make it difficult to maintain consistency, trace changes, and identify potential conflicts.

ReqIntel is being developed as a platform that assists teams in organizing requirements and applying automated analysis to improve requirement quality and visibility.

## Key Features

The project is designed to support features such as:

- User authentication and secure access
- Requirement creation and management
- Structured requirement storage
- Requirement version tracking
- Requirement analysis
- Detection of ambiguous or conflicting requirements
- Requirement relationships and dependencies
- Project-based requirement organization
- AI-assisted requirement intelligence
- Traceability and change tracking
- Enterprise-oriented access and data management

## Technology Stack

### Backend

- Python
- FastAPI
- Pydantic
- Supabase
- PostgreSQL

### Authentication

- Supabase Auth
- JWT-based authentication
- HTTP Bearer authentication

### API Documentation

- Swagger UI
- OpenAPI

### Development Tools

- Visual Studio Code
- Git
- GitHub

## Authentication Setup

ReqIntel uses **Supabase Auth** as the only identity provider. The backend verifies every
JWT, reads the caller's role and `is_active` flag from `public.users`, and never shares
authentication state between requests (each Auth call uses its own short-lived client).

**Features:** email/password sign-up with email confirmation and resend, login with
*Remember me* (checked = `localStorage`, unchecked = `sessionStorage`), automatic access-token
refresh with one retry on `401`, forgot/reset password, Google and GitHub sign-in (PKCE),
logout, role-protected admin routes, and rate limiting on sensitive endpoints.

### Environment variables

| File | Variable | Purpose |
|---|---|---|
| `backend/.env` | `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_SECRET` | Supabase project |
| `backend/.env` | `SUPABASE_SERVICE_ROLE_KEY` | Server only (storage + global rule config reads). Never expose to the browser |
| `backend/.env` | `DATABASE_URL` | Postgres connection (use the least-privilege app role, not `postgres`) |
| `backend/.env` | `FRONTEND_URL` | Redirect target for emails and OAuth (default `http://localhost:5173`) |
| `backend/.env` | `TRUST_PROXY_HEADERS` | `true` only behind a trusted reverse proxy |
| `frontend/.env` | `VITE_API_BASE_URL` | Backend URL |

Copy `backend/.env.example` and `frontend/.env.example` and fill in the values. Never commit `.env`.

### Supabase dashboard configuration

1. **Authentication > URL Configuration:** set *Site URL* to your `FRONTEND_URL` and add these
   *Redirect URLs* (add the production equivalents when you deploy):
   - `http://localhost:5173/auth/callback`
   - `http://localhost:5173/reset-password`
2. **Authentication > Sign In / Providers:** enable *Email* with *Confirm email* on, and enable
   *Google* and *GitHub*. Their client IDs and secrets are entered **only** in Supabase.
3. **Google:** create an OAuth client in Google Cloud Console with the authorized redirect URI
   `https://<project-ref>.supabase.co/auth/v1/callback`.
4. **GitHub:** create an OAuth App with the same callback URL. The GitHub account needs a
   verified email, otherwise sign-in fails with a clear message (the profile row requires an email).
5. **Authentication > Emails > SMTP:** configure a custom SMTP provider (e.g. Resend).

### Verify the configuration (read-only)

```bash
cd backend
python scripts/check_auth_config.py
```

Checks, against your live Supabase project and without printing any secret: email
confirmation, sign-ups allowed, Google/GitHub enabled, a client ID saved for each, and the exact
redirect URI Supabase sends to each provider. It also lists what only you can confirm in a
dashboard (redirect allow-list, Google "Test users", GitHub app type).

Provider notes:

- **Google:** while the consent screen is in *Testing*, add every tester's Gmail under *Test users*.
- **GitHub:** a classic *OAuth App* works as-is. If you registered a *GitHub App* (the type with
  "Expire user authorization tokens"), also set *Account permissions > Email addresses = Read-only*;
  without it GitHub accounts cannot be matched to an email and sign-in fails.
- Email deliverability (confirmation mails in Spam): see `docs/EMAIL_DELIVERABILITY.md` and the
  templates in `docs/email-templates/`.
- Optional SQL: `sql/16_auth_trigger_name_handling.sql` (long/blank provider names, GitHub display
  name). Apply manually in the Supabase SQL editor; instructions are inside the file.

### Known limitations

- **Email delivery:** Supabase's built-in mailer is limited to a few emails per hour and is meant
  for testing. With a custom SMTP provider, delivery needs a verified sending domain (a
  `*@resend.dev` sender can only deliver to the account owner). Confirmation, resend and reset
  emails are therefore only as reliable as your SMTP setup; verify delivery end to end.
- **Rate limiting** is in-memory per process. With several workers/containers each counts
  separately; add a limiter at the reverse proxy for production. Supabase also applies its own limits.
- **Logout** revokes the session for the device (`local` scope). If the access token has already
  expired, the server-side session is not revoked, only the local tokens are cleared.
- **Tokens** are stored in the browser (`localStorage`/`sessionStorage`), so XSS protection
  matters; there is no `HttpOnly` cookie session.

### Running the tests

```bash
# Backend (unit + auth; no database needed)
cd backend && pip install pytest pytest-asyncio httpx uvicorn
python -m pytest tests/test_auth.py tests/test_auth_flows.py -q

# Backend integration tests need a disposable local Postgres: see backend/tests/README.md

# Frontend
cd frontend && npm install && npm run test && npm run lint && npm run build
```

## Project Structure

```text
reqintel/
│
├── backend/
│   ├── api/
│   ├── auth/
│   ├── core/
│   └── main.py
│
├── database/
│
├── docs/
│
└── README.md