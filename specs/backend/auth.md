# Backend — Authentication

## v1: No Auth
- All endpoints are publicly accessible.
- Intended for local / single-user usage only.

## v2: JWT Auth (future)
- REQ-BAU-001: `POST /api/auth/login` — returns JWT access token.
- REQ-BAU-002: `POST /api/auth/register` — creates user account.
- REQ-BAU-003: All `/api/*` endpoints (except health and auth) require `Authorization: Bearer <token>`.
- REQ-BAU-004: Documents are scoped per user.

## Notes
- Auth is explicitly out of scope for MVP.
- Backend should be structured so auth middleware can be added without refactoring routes.
