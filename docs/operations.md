# Production operations checklist

## Redis and WebSockets

Production must set `REDIS_URL` to an authenticated, highly available Redis service. `/health/ready/` returns `not_ready` when Redis is unavailable in production. The live inventory dashboard still has a polling fallback, but production deployment should treat Redis readiness as required for WebSocket delivery.

## Offline admission

Offline devices upload signed scan records to `/tickets/events/<event-id>/scan/offline/`. Uploading does not admit anybody. A staff member must explicitly reconcile the batch at `/tickets/scan/offline/<batch-id>/reconcile/`; the server then rechecks current ticket state and performs atomic admission. Invalid, cancelled, refunded, transferred, and replayed records remain rejected/audited.

## Marketplace and payments

When `DEBUG=true`, the marketplace exposes an explicit sandbox confirmation. In production, the same route refuses browser confirmation. A verified M-Pesa/EcoCash provider callback must be wired to a payment record before resale ownership transfer is allowed.

## Blockchain

Blockchain minting fails closed unless `BLOCKCHAIN_RPC_URL`, `BLOCKCHAIN_CONTRACT_ADDRESS`, and `BLOCKCHAIN_PRIVATE_KEY` are configured. Configuration alone does not claim minting is operational: an approved Web3 worker, deployed contract ABI/address, transaction confirmation, retry policy, and reconciliation process must be enabled first.

## Backups, monitoring, and load testing

- Use managed PostgreSQL point-in-time recovery plus scheduled encrypted backups; test restoration regularly.
- Export application, database, Celery, Redis, WebSocket and payment-provider health metrics to the deployment monitoring system.
- Run load tests against PostgreSQL and Redis with realistic ticket, seat reservation, scanner and WebSocket workloads before production traffic.
- The repository includes `locustfile.py`; install the optional `ops` extra and run `locust -f locustfile.py` against a staging deployment. Extend the scenarios with authenticated checkout/scanning before relying on results.
- Keep secrets in the deployment secret manager; rotate signing, database, Redis and provider credentials.
- Complete an independent security review covering IDOR, CSRF, rate limits, private media access, payment callbacks, offline reconciliation, and concurrency before launch.
