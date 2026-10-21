---
title: Idempotency Keys
type: concept
---

# Idempotency Keys
The client sends a unique key per write; the server stores the response and replays it on retry. Required on all [[tidepool-api]] POSTs. Makes retry with backoff safe.
