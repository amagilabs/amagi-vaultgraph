---
title: Lighthouse App
type: project
tags: [mobile, active]
---

# Lighthouse App
Mobile check-in app for marina staff. Backend is [[tidepool-api]]; marketing site is [[harbor-site]].
Design partner: [[ines-duarte]]. Contractor on the offline sync: [[tomas-reyes]].
- Offline-first sync uses [[event-sourcing]] on the device, replayed on reconnect.
- Ship behind [[feature-flags]]; see [[adr-004-monorepo]] for repo layout.
- Open question: push notifications via [[webhooks]] or polling?
