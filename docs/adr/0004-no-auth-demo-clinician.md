# ADR 0004: No Authentication — Demo Clinician Identity

**Date:** 2026-06-11
**Status:** Accepted
**Deciders:** Product owner (via design interview, 2026-06-11)
**Relates to:** ADR-0001 (Initial Architecture)

---

## Context

The app needs to decide how to handle clinician identity and access control for the demo
deployment.

---

## Decision

**No authentication is implemented.** A fixed Demo Clinician identity ("Dr. Sarah Chen") is
displayed in the navigation bar. All patients from the FHIR server are visible to any user
who accesses the app. There is no login flow, no session management, and no role-based
access control.

---

## Rationale

- The FHIR server contains **synthetic data only** — no real PHI at risk
- Authentication setup (Clerk account, JWKS integration, protected routes, JWT validation)
  is estimated at ~2–4 hours of work that gates nothing in the core matching feature
- The app is intended as a demo / proof-of-concept, not a production system
- All synthetic patients are relevant to the matching use case — patient scoping by clinician
  does not apply to a demo scenario

---

## Consequences

- No `CLERK_JWKS_URL`, `CLERK_ISSUER`, or auth middleware in the backend
- No `ProtectedRoute` or `useAuth` hooks in the frontend
- All FastAPI endpoints are unauthenticated — suitable only for local dev or private demo
  environments, not for public deployment
- Adding Clerk auth later requires: backend JWT middleware, frontend ClerkProvider +
  ProtectedRoute, and removing the hardcoded Demo Clinician display name — no other
  structural changes

---

## Revisit Trigger

This decision must be revisited before any deployment that connects to real patient data
(non-synthetic FHIR server). At that point, Clerk (matching the Patient Management App
pattern) is the recommended auth provider.
