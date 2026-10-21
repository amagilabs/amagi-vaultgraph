---
title: Tidepool API
type: project
tags: [backend, active]
---

# Tidepool API
REST API behind [[lighthouse-app]] and [[driftwood-cli]].
- Storage decision: [[adr-001-use-sqlite]]. Queue: [[adr-002-queue-choice]].
- Every write endpoint takes [[idempotency-keys]]; clients use [[retry-with-backoff]].
- Public endpoints have [[rate-limiting]] (token bucket, 60/min).
- Logs follow [[structured-logging]]; dashboards in [[observability]].
- Auth: [[adr-003-auth-provider]].
