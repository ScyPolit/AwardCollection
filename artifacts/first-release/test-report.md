# First Release Test Report

Date: 2026-11-06 (Asia/Shanghai)

## Passed

- Django checks, migration consistency, and five backend workflow tests.
- A real PDF with two incremental pyHanko signatures and its PNG output.
- Pure Admin TypeScript check and production build.
- Docker Compose configuration parsing.
- Browser login, CSRF-protected competition creation, database refresh, and visual template editor.

## Not Passed Or Blocked

- No target-server deployment because the supplied credential file is absent.
- No PostgreSQL concurrency, worker interruption, container rebuild, or backup restore drill.
- No real 5000-certificate run.
- Revocation/emergency workflows, ZIP download, rate limiting, and several administration screens remain incomplete.

See `docs/implementation-status.md` for A01-A30 evidence.
