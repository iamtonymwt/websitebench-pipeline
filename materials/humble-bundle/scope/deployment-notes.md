# Deployment preparation notes — humble-bundle (phases 11–12)

Phase 11 deliverable record. Nothing here authorizes publication; see the
authorization line at the bottom.

## Frozen deployment identity

| Field | Value | Source of truth |
| --- | --- | --- |
| `site_id` | `humble-bundle` | `backend/runtime.json` → `site.id` |
| Site label | `Humble Bundle` | `backend/runtime.json` → `site.label` |
| Cloudflare Worker | `websitebench-humble-bundle-demo` | `deploy/generic-offline-clone/deployment.humble-bundle.v2.json` → `cloudflare.worker_name` |
| Public origin | `https://humble-bundle.website-bench.com` | `backend/runtime.json` → `site.public_origin` (the descriptor carries no domain) |
| Custom-domain route | `humble-bundle.website-bench.com` (`custom_domain: true`) | derived by `scripts/config.mjs` from the public origin |
| Concurrency group | `public-demo-humble-bundle` | `.github/workflows/deploy-humble-bundle-public.yml` |
| Deployment profile | `cloudflare-review` | descriptor → `deployment_profile` |
| Persistence | `ephemeral-reset` | `backend/runtime.json` → `deployment.profiles.cloudflare-review.persistence` |
| Container port / health | `10000` / `GET /healthz` | descriptor → `runtime` |
| Python pins | `fastapi==0.139.2`, `uvicorn==0.51.0` | descriptor → `runtime.python_requirements` |

Files owned by this phase:

- `deploy/generic-offline-clone/deployment.humble-bundle.v2.json`
- `.github/workflows/deploy-humble-bundle-public.yml`

One change was required outside those two files: `backend/runtime.json`
still carried the backend-scaffold placeholder
`https://humble-bundle.offline.invalid` as `site.public_origin`. The generated
Worker derives both `PUBLIC_HOST` and its custom-domain route from that value,
so the placeholder would have bound the Worker to an unresolvable host while
the dispatcher health-checked the real one. It is now
`https://humble-bundle.website-bench.com`, matching
`docs/public-demo-new-site-deployment.md`, the ASPCA precedent and this site's
own `scope/derived-task-brief.json` → `target_origin`. Nothing else in the
runtime contract changed.

## Local gates (2026-08-20, macOS, node v26.7.0, wrangler 4.122.0)

All commands run from `deploy/generic-offline-clone/` unless noted. No network
publication, no `--yes`, no workflow dispatch.

| Command | Exit code | Warnings |
| --- | --- | --- |
| `npm ci` | 0 | 6 `npm warn` lines, all one advisory: "3 packages have install scripts not yet covered by allowScripts" (`esbuild`, `fsevents`, `workerd`). Harmless here — the platform binaries ship as optional deps (`@esbuild/darwin-arm64`, `@cloudflare/workerd-darwin-arm64`), so wrangler ran normally. |
| `npm test` | 0 | 0 test warnings — 25 tests: 23 pass, 0 fail, 2 skipped (`deployment.edx.v2.json` / `deployment.petfinder.v2.json` descriptors absent from this export; skips are guarded by `descriptorPresent`). |
| `node scripts/prepare.mjs --config deployment.humble-bundle.v2.json --check-only` | 0 | `"warnings": []` (0). `status: valid`, `compatibility: v2`, `persistence: ephemeral-reset`. |
| `node scripts/deploy.mjs --config deployment.humble-bundle.v2.json --dry-run` | 0 | `"warnings": []` (0); wrangler emitted no `▲`/deprecation lines. `status: dry-run-complete`. |

Supporting repo gates re-run after the `runtime.json` edit:

| Command (repo root) | Exit code | Result |
| --- | --- | --- |
| `.venv/bin/python -m pytest tests/project -q` | 0 | 15 passed, 5 skipped — includes `test_each_explicit_deploy_dispatcher_targets_an_existing_site[deploy-humble-bundle-public.yml]`. |
| `.venv/bin/python -m pytest materials/humble-bundle/clone/tests -q` | 0 | 38 passed. |

Candidate identity recorded by the dry-run (local artifact, regenerated per
run — not a deployment identity to reuse):

- `candidate_sha256` `7167bbe9b6cd81d9dcb6d244e33cf6e83b109f7d76eee25b9f066929db0bc4bc`
- `deployment_sha256` `c6fc53fcbef9047c0a1187cb7a3a20216d603cc6810e29dd10a18b0a0c8cd02b`

`wrangler.generated.jsonc`, `.container-context/` and `.wrangler/` are
gitignored build output. They now hold humble-bundle values because the
dry-run regenerated them; they must never be treated as another site's
deployment identity.

## Persistence disclosure (binding wording)

The `cloudflare-review` profile is **ephemeral**: `persistence` is
`ephemeral-reset`. The Cloudflare Container local disk is rebuilt from seed, so
accounts, carts, purchases, keys, wishlists and any other SQLite state may be
lost at any sleep, restart, redeploy or rebuild. This demo must never be
described as durable, persistent, or a place to keep data. It is an anonymous,
Basic-Auth-gated, `noindex` offline-clone sandbox — not a Humble Bundle
service and not affiliated with the source brand.

## Secrets

The descriptor and the dispatcher contain no secret values — only binding
names, and those are emitted by the generator, not written by hand. The
generated config declares `secrets.required`:
`BASIC_AUTH_PASSWORD`, `REDIS_REST_URL`, `REDIS_REST_TOKEN`,
`RESEND_API_KEY`, `RESEND_FROM_EMAIL`. Turnstile is off
(`AUTH_REQUIRE_TURNSTILE=false`): this candidate serves registration behind the
shared Basic Auth boundary and does not require a Turnstile keypair.
Payments stay on `local-sandbox`; `stripe_test` is `null`, so no Stripe secret
binding is requested.

## Authorization

```text
PUBLIC_DEPLOYMENT_AUTHORIZED=false
```

No publication has been performed and none may be. `wrangler deploy` (without
`--dry-run`), `--yes`, a `workflow_dispatch` with `deploy=true`, and any
DNS/domain change all remain forbidden until a human explicitly grants
publication authority for **this exact candidate** in the task where it is
used. No diagnostic `clean`, passing test, Harbor score or dry-run in this file
is an acceptance, rights, redistribution or deployment decision.

## Known blockers for a future real deployment

1. `humble-bundle.website-bench.com` must exist as a Cloudflare custom domain
   on the account that owns `websitebench-humble-bundle-demo`. The dry-run
   validates the route's shape, never its existence.
2. Repository-scope secrets above must be present. `redis-resend` mail fails
   closed without `REDIS_REST_URL` / `REDIS_REST_TOKEN` / `RESEND_API_KEY` /
   `RESEND_FROM_EMAIL`, which would break registration and password reset.
3. A real publish builds the container image; that needs a working Docker
   builder on the runner. The local dry-run only enumerates the Dockerfile.
4. Phase 12 requires a recoverable Worker version recorded **before** the
   publish. The shared workflow auto-rolls back only when the deploy command
   itself fails — a post-deploy health, functional or visual failure needs an
   explicit rollback under the same authorization. Do not publish when a
   recoverable version cannot be confirmed.
5. Rights review for redistributing the humblebundle.com snapshot subset is a
   separate human decision and is not covered by any gate above.
