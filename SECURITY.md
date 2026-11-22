# Security review checklist

- [ ] Production `DEBUG=false`, HTTPS and secure cookies verified.
- [ ] PostgreSQL, Redis, signing keys, payment credentials and blockchain credentials stored outside source control.
- [ ] `/health/ready/` is monitored and Redis is required in production.
- [ ] Payment callbacks verify provider signatures and are idempotent.
- [ ] Offline batches are reconciled server-side before admission.
- [ ] Private attendee photographs are served only through authorized views.
- [ ] PostgreSQL concurrency tests run against the production database engine.
- [ ] Backup restoration and incident-response drills completed.
- [ ] Independent penetration/security review completed.
