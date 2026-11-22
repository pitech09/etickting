# eTickting

Secure, Lesotho-focused event ticketing platform built with Django. Development is intentionally phased; this repository currently contains Phase 1 only.

## Phase 1 foundation

- Custom email-based user model.
- Registration, login, logout, CSRF protection and password validation.
- Organisation and organisation membership models with owner, event manager and event staff roles.
- Authenticated dashboard and health endpoint.
- PostgreSQL-ready configuration with SQLite fallback for local development.
- Redis, Channels and Celery configuration ready for later phases; no payment or real-time feature is represented as operational yet.
- Signed ticket credentials with Ed25519 key rotation, server-side verification, atomic admission, scanner devices, audit scans, public limited verification, and payment-gated resale transfer primitives.
- Phase 5 customer wallet, encrypted credential delivery, QR image downloads, attendee profiles and owner-controlled attendee photographs.
- Phase 6 organiser inventory dashboard with general-admission metrics, reserved-seat occupancy, authenticated WebSockets and polling fallback.
- Phase 7 admission/re-entry and explicit offline scan reconciliation records.
- Phase 8 controlled resale marketplace UI and transfer-safe credential invalidation.
- Phase 9 in-app notifications and balanced finance ledger/reporting foundations.
- Phase 10 blockchain proof boundary without pretending external chain activity is live.
- Production operations: `/health/ready/`, Redis readiness, offline reconciliation, sandbox payment gating, blockchain fail-closed checks, security checklist and Locust load-test starter.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
python manage.py migrate
python manage.py test
python manage.py runserver
```

Visit http://127.0.0.1:8000/accounts/register/.

For production, set a strong `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=false`, `DJANGO_ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, and a PostgreSQL `DATABASE_URL`. Redis is required before enabling Channels/Celery workers.

Ticket signing keys are deployment secrets, not database records or source files. `TICKETING_SIGNING_KEYS` contains active private keys as JSON; `TICKETING_VERIFY_KEYS` can retain public keys for rotated credentials. Never put either value in Git. Generate keys with `Ed25519PrivateKey.generate()` and store the URL-safe base64 raw private key in the deployment secret manager.

## Architecture and security notes

See `docs/architecture.md` for the phased application boundaries, model relationships, security design and workflow decisions. `DEVELOPMENT_CHECKLIST.md` records the current phase and known limitations.
