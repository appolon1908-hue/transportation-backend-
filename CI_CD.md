# CI/CD authority

## Repository

- Repository: `appolon1908-hue/transportation-backend-`
- Class: `backend`
- Purpose: freight-platform backend
- Current default branch: governance/documentation only
- Buildable application authority: `be/release-readiness-v6`

## Persistent branches

```text
development
test
staging
production
main
```

Promotion order:

```text
feature/fix -> development -> test -> staging -> production -> main
```

The initial bootstrap places the CI/CD policy on every persistent branch. That does not promote the backend or authorize deployment.

## Required CI

`.github/workflows/required-ci.yml` runs on every push, pull request, and manual dispatch. It proves exact source identity, runs checksum-verified secret scanning, validates repository data and documentation, installs Python dependencies in an isolated virtual environment, compiles Python, runs tests, checks installed dependency consistency, validates Compose, builds Dockerfiles, and publishes sanitized evidence.

A pull request from `be/release-readiness-v6` into `development` will be validated against that exact application head by the base branch's required workflow.

## Every-branch audit

`.github/workflows/all-branches-audit.yml` runs daily and manually. It validates every current branch tip in an isolated worktree without changing branch history.

## Continuous delivery

`.github/workflows/continuous-delivery.yml` runs only on the persistent branch train. It creates deterministic source/build bundles, records exact SHA/tree evidence and SHA-256 checksums, and may publish an immutable GHCR image from `staging`, `production`, or `main` when reproducible build inputs are present.

Runtime deployment, database migrations, provider calls, and external effects remain unauthorized. A separate protected-environment deployment must prove backup/restore, migration safety, health/readiness/version readback, monitoring, exact digest, and rollback.

## Current source gate

`main` does not contain the buildable freight backend. Delivery on policy-only persistent branches fails closed until `be/release-readiness-v6` is independently reviewed and promoted into `development`, then through `test`, `staging`, `production`, and `main`.

## Required GitHub settings

Protect all five persistent branches or apply equivalent rulesets. Require `required-ci`, approving review, resolved conversations, linear history, no force pushes, no deletion, and up-to-date protected promotions.
