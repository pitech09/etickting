# Development checklist

## Phase 1 — foundation

- [x] Django project and environment configuration
- [x] Custom email-based user model
- [x] Registration, login, logout and password validation
- [x] Organisation and membership roles
- [x] Base templates and authenticated dashboard
- [x] Health endpoint
- [x] Initial tests
- [x] Signed opaque ticket credentials and key rotation support
- [x] Server-side verification and public limited verification endpoint
- [x] Atomic admission, scanner device authorization and scan audit log
- [x] Ownership transfer and payment-gated resale primitives
- [x] Architecture and setup documentation

## Phase 2 — organisation and event management

- [x] Venue model with organisation association
- [x] Venue CRUD (create, read, update, list) with forms and templates
- [x] Organisation-level venue scoping (users only see their org's venues)
- [x] Expanded Event model (ticketing model, lifecycle status, admission policy, resale policy, refund policy, venue FK, sales dates, timezone, cover image)
- [x] EventForm with organisation-scoped venue queryset
- [x] Event CRUD views (list, create, detail, update)
- [x] Event publish action (draft → published) with validation via `can_publish()`
- [x] Event sales-open action (published → sales_open) with date timestamping
- [x] Event templates (list, detail, create/edit form)
- [x] Object-level permissions via `_RequiresOrganisationEventAccess` mixin
- [x] Quick-action cards on dashboard for events, venues, and ticket verification
- [x] Namespaced ticketing URLs (`ticketing:`)
- [x] All Phase 2 tests pass

## Phase 3 — ticketing and inventory (next)

- [ ] General Admission inventory model
- [ ] Ticket categories and pricing
- [ ] Quantity limits and sold-out handling
- [ ] Reserved seating models (Section, Row, Seat)
- [ ] Organiser seating builder
- [ ] Customer seating map
- [ ] Temporary seat reservations with 10-minute expiry
- [ ] Concurrency protection (PostgreSQL row-level locking)

## Phase 4 — orders and payments

- [ ] Customer checkout
- [ ] Order management
- [ ] Payment abstraction layer (M-Pesa, EcoCash, sandbox)
- [ ] Payment webhook processing
- [ ] Payment reconciliation

## Phase 5 — digital tickets and attendee profiles

- [x] Signed ticket issuance and QR generation
- [x] Ticket download and owner-scoped customer wallet
- [x] Attendee profile and ticket-specific photograph upload
- [x] Encrypted credential delivery and owner access controls

## Phase 6 — organiser live inventory dashboard

- [x] General Admission live inventory dashboard
- [x] Interactive seating occupancy map with accessible labels and status legend
- [x] Django Channels WebSocket integration with authenticated event access
- [x] Post-commit inventory update notifications and polling fallback
- [x] Occupancy, category sales and revenue metrics

## Phase 7 — scanner and admission

- [x] Scanner interface improvements
- [x] Admission state machine with single-entry and re-entry handling
- [x] Re-entry policies
- [x] Offline signed-scan upload with explicit pending reconciliation status

## Phase 8 — controlled resale marketplace

- [x] Resale eligibility and policies
- [x] Listing creation service and marketplace UI
- [x] Ownership transfer with QR invalidation
- [ ] Seller payout settlement (requires finance/provider settlement workflow)

## Phase 9 — notifications and finance

- [x] In-app notifications and notification service
- [x] Immutable-style balanced integer-minor-unit ledger foundation
- [x] Organisation finance report
- [ ] Email delivery and automated payout settlement

## Phase 10 — optional blockchain

- [x] Blockchain proof/reconciliation boundary
- [ ] Live Web3 provider, contract deployment and NFT minting

## Phase 11 — production readiness

- [x] Environment-based configuration and deployment documentation
- [x] Automated checks and migration consistency validation
- [ ] External-service load testing, backups, monitoring and final security review

## Known limitations

- Email verification, password reset UI, MFA, rate limiting and invitation workflows are planned security work, not yet complete.
- Channels and Celery are configured but have no consumers/tasks yet.
- Offline scanner reconciliation and photograph verification are not yet implemented.
- Concurrent PostgreSQL stress tests require a PostgreSQL test service.
- Redis and live PostgreSQL connectivity require external services and credentials.
- QR downloads are PNG credentials; native PDF generation is not yet implemented.
- A dedicated staff-only attendee-photo endpoint remains for the scanner UI.
- WebSocket delivery requires Redis; the dashboard automatically polls the database-backed snapshot when WebSockets are unavailable.
- Offline scans are accepted as signature-checked pending records; they are not silently admitted offline because revocation and duplicate state require server reconciliation.
- Marketplace purchases are sandbox-only when `DEBUG=true`; production purchases require a verified payment provider callback.
- Blockchain records are reconciliation placeholders; no NFT or transaction is claimed without configured Web3 infrastructure.
- Production readiness assets now include Redis readiness checks, offline reconciliation, operations runbooks, a healthcheck script, and a security review checklist. Backup restoration, monitoring, load testing and independent review still must be executed in the deployment environment.
