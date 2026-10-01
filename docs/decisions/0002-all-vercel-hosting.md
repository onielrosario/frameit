# ADR-0002 — Host everything on Vercel

**Date:** 2026-09-11 · **Status:** Accepted

## Context

The API is a FastAPI service whose request profile is one multi-second Gemini call and almost nothing
else. The initial engineering objection to running it on Vercel was the familiar one: serverless is a
poor fit for long I/O-bound requests — cold starts, duration caps, bundle limits, and paying for
wall-clock time spent waiting on a model.

Checking Vercel's current documentation rather than relying on that prior, the objection largely does
not hold in 2026:

- FastAPI is a **first-class zero-config backend framework** on Vercel. Vercel looks for a `FastAPI`
  instance named `app` at a supported entrypoint, or `tool.vercel.entrypoint` in `pyproject.toml`.
  Lifespan events are supported.
- **Fluid compute is the default**, and max duration is **300s by default on every plan** (800s
  maximum on Pro). A 6-second Gemini call is not close to a limit.
- **Time spent waiting on I/O does not count toward billed active CPU time.** Vercel bills active CPU
  plus provisioned memory time, and explicitly excludes waiting on AI models and database queries.
  Frame's workload is ~99% waiting — close to the ideal Fluid workload.
- **Python bundle limit is 500 MB** (5 GB via the Large Functions beta). `google-genai` + `pydantic`
  + an HTTP driver is nowhere near it.

Against that, the stated top priority is **ease of development**: one platform, one deploy story, one
dashboard, no second provider to learn.

## Decision

Host everything on Vercel. Two Vercel projects against the one repo, each with its own Root
Directory: `apps/web` (Next.js) and `services/api` (FastAPI).

## Consequences

**Good**

- One platform, one CI path, one set of environment-variable plumbing.
- Billing model genuinely favors this workload.
- Preview deployments per branch for both the web app and the API.

**Bad — these are the real constraints to design around**

- **Fluid runs concurrent invocations inside one instance.** Module-level mutable state is shared
  across concurrent requests. No request-scoped globals; any in-process cache must be
  concurrency-safe or must not exist. This is the most likely source of a confusing production bug.
- **1,024 file descriptors shared across concurrent executions.** No long-lived TCP connection pools.
  Use Upstash REST and the Neon serverless HTTP driver.
- **Shutdown cleanup is capped at ~500ms after SIGTERM.** Telemetry must be written inside the
  request, never deferred to shutdown.
- Single region by default (`iad1`).
- 4.5 MB request/response body cap — irrelevant at 5,000 characters, noted so it is not rediscovered.

## Mitigation: keep the decision reversible

`services/api` stays a **plain ASGI application with no Vercel-specific imports in business logic**.
Platform configuration lives only in `vercel.json` and `pyproject.toml`. Local development runs
`uvicorn`. If Fluid's shared-state model or anything else becomes painful, moving to a container is a
deploy-configuration change rather than a rewrite.

## Alternatives considered

- **Split hosting (Vercel web + Render/Fly API)** — a normal long-lived container, no shared-instance
  state model, no serverless idioms. Rejected: it adds a second platform for a workload that Vercel
  now handles well, against the ease-of-development priority. Remains the escape hatch.

## Sources

- [Deploy a FastAPI app on Vercel](https://vercel.com/docs/frameworks/backend/fastapi)
- [Vercel Functions Limits](https://vercel.com/docs/functions/limitations)
- [Python Vercel Functions bundle size limit increased to 500MB](https://vercel.com/changelog/python-vercel-functions-bundle-size-limit-increased-to-500mb)
