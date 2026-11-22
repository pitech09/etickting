# Architecture

## Application boundaries

`accounts` owns identity and authentication. `organisations` owns organisation records and memberships. `dashboard` is the authenticated presentation layer for cross-cutting summaries. `core` contains small shared infrastructure such as health checks. Future applications will own events, venues/seating, ticket inventory, orders, payments, attendees, check-in, resale, finance, notifications, analytics and audit records separately.

## Phase 1 relationships

One `User` can belong to many `Organisation` records through `OrganisationMembership`. Each membership has one server-enforced role. Organisation IDs are UUIDs, but UUIDs are not treated as authorization: every future object query must also filter through the authenticated user's membership and the required role.

## Security architecture

Django's password hashers, CSRF middleware, session authentication, secure cookie settings in production, clickjacking protection and ORM parameterization are enabled. Email is unique and normalized at registration. The dashboard is login-protected. Future sensitive operations require server-side membership/role checks, transaction boundaries, rate limiting and audit records; hiding UI controls will never be the control.

## Planned workflows

Phase 2 adds organisation administration, venues and events. Phase 3 adds independent general-admission inventory and PostgreSQL-authoritative reserved-seat reservations. Orders and provider adapters follow in Phase 4. Ticket issuance, check-in, resale and finance remain intentionally out of Phase 1.

## Ticket authenticity

Ticket credentials are opaque `key_id.payload.signature` values. The payload contains only a version, ticket UUID, event UUID, public ticket reference and random nonce—never attendee data. Ed25519 private keys are read from deployment secrets; the database stores only public key metadata and SHA-256 credential hashes. A key ID permits rotation while verification keys retain old signatures.

Issuance is only available through the service layer and requires a verified payment or explicit complimentary authorization. Verification checks the signature, payload binding, credential record, current credential state, event, and ticket status. Admission locks the ticket row inside a transaction and uses a one-to-one admission record to make replay visible. Scanner access requires a staff membership, event-bound active device ID, and is logged for every result.

Resale purchase locks the listing and verifies payment before ownership transfer. The previous credential is marked transferred, a new nonce-bearing credential is issued, and ownership history is retained. The public verification endpoint returns event, public ticket reference, seat label and status only; it never exposes the attendee name or owner.

## Infrastructure decisions

Production uses PostgreSQL, Redis, ASGI/Channels and Celery. SQLite fallback is only for a quick local foundation run. External payment providers will use explicit adapters and sandbox states; credentials and provider approval are prerequisites for claiming live operation.
