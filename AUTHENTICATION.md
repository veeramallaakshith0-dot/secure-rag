# Authentication and RBAC

The API mounts authentication routes below `/api/v1/auth`.

## First administrator

Set these optional settings in `backend/.env` before the first server start:

```dotenv
INITIAL_ADMIN_USERNAME=admin
INITIAL_ADMIN_EMAIL=admin@example.local
INITIAL_ADMIN_PASSWORD=use-a-unique-password-of-at-least-12-characters
```

Startup creates this account only if the username and email do not already exist. The password is hashed before storage. After the first successful startup, remove `INITIAL_ADMIN_PASSWORD` from `.env`; the account remains in PostgreSQL. Keep the existing `DATABASE_URL` and `SECRET_KEY` settings private.

If a `user` already exists from earlier database initialization, registration and role setup still work. The bootstrap account is only created when the configured username and email are both unused.

## Endpoints

- `POST /api/v1/auth/register` — create an active account with the `user` role; password must be 12–128 characters.
- `POST /api/v1/auth/login` — submit OAuth2 form fields `username` (username or email) and `password`; returns a bearer token.
- `GET /api/v1/auth/me` — return the authenticated account and role.
- `GET /api/v1/auth/users` — admin only; list accounts.
- `PATCH /api/v1/auth/users/{user_id}/role` — admin only; JSON body such as `{"role":"admin"}` or `{"role":"user"}`.
- `PATCH /api/v1/auth/users/{user_id}/active` — admin only; JSON body such as `{"is_active":false}`.

Use the token as `Authorization: Bearer <access_token>`. Roles are seeded idempotently at startup. Admins cannot deactivate their own account.
