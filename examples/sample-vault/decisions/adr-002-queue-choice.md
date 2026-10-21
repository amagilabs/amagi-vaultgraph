---
title: ADR-002 Queue Choice
type: decision
---

# ADR-002: Queue choice
Status: accepted. Use a database-backed queue until volume justifies a broker.
Consumers must handle duplicates ([[idempotency-keys]]). Context: [[tidepool-api]].
