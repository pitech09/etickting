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

- [ ] Ticket issuance and QR generation
- [ ] Ticket download and customer dashboard
- [ ] Attendee information and photograph upload
- [ ] Photograph access controls

## Phase 6 — organiser live inventory dashboard

- [ ] General Admission live inventory dashboard
- [ ] Interactive seating occupancy map
- [ ] Django Channels WebSocket integration
- [ ] Real-time occupancy updates
- [ ] Analytics

## Phase 7 — scanner and admission

- [ ] Scanner interface improvements
- [ ] Admission state machine
- [ ] Re-entry policies
- [ ] Offline scanning

## Phase 8 — controlled resale marketplace

- [ ] Resale eligibility and policies
- [ ] Listing creation and marketplace
- [ ] Ownership transfer with QR invalidation
- [ ] Seller payout

## Phase 9 — notifications and finance

- [ ] Email and in-app notifications
- [ ] Financial ledger and organiser reports

## Phase 10 — optional blockchain

- [ ] Blockchain architecture and NFT minting

## Phase 11 — production readiness

- [ ] Security review
- [ ] Performance testing
- [ ] Production deployment

## Known limitations

- Email verification, password reset UI, MFA, rate limiting and invitation workflows are planned security work, not yet complete.
- Channels and Celery are configured but have no consumers/tasks yet.
- Offline scanner reconciliation and photograph verification are not yet implemented.
- Concurrent PostgreSQL stress tests require a PostgreSQL test service.
- Redis and live PostgreSQL connectivity require external services and credentials.
