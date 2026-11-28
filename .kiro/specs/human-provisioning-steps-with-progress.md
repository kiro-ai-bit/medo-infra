# Ticket 30 — Human provisioning: steps + progress

**Single consolidated ops file** (merged 27-11-26 from `provisioning.md` + `human-provisioning-steps.md` + `provisioning-completion.md` — those three are superseded by this file). Ticket: `.scratch/medo-impl/issues/30-provisioning-accounts-repos-secrets.md`. Owner: `kiro-ai-bit`. Domains: `simmaps.com` (`app.`, `api.`, `photos.`, `notify.`).

## How to read

- **Status legend:** `RESOLVED` = done · `RESOLVED-BY-AGENT` = agent executed via MCP/CLI on user's behalf · `PARTIAL` = some done, some pending · `PENDING` = not started.
- **Actor tags in checklists:** `[U]` = user did it manually (dashboard/CLI) · `[A]` = agent did it (MCP server / script / SSH) · `[UA]` = both contributed.
- **Global rules:** never paste passwords/tokens/keys/`.pem` into chat; secrets go only to SSM `/medo/prod/*`, `D:\medo\.env`, gitignored service `.env`, or `D:\medo\AppHub\.secrets\`; copy dashboard-shown secrets immediately; tell agent `done N` or `stuck at <step>`.

## Prepared for you (already done)

- 9 GitHub repos exist + pushed; local clones `D:\medo\AppHub\<repo>`; `AppHub/` gitignored in docs repo.
- Keys: `AppHub\.secrets\medo-dev-keys.json` (dev), `medo-prod-keys.json` (prod → SSM source), per-service gitignored `.env` files, `.env.example` in all 9 repos.
- Secrets vault convention: `AppHub\.secrets\` — ALL files present: AWS files + `cloudflare.json` + `vercel.json` + `resend.json`.
- Tooling: `aws-mcp` + `cloudflare` MCP servers configured (`.devin/mcp_config.local.json` + `.kiro/settings/mcp.json`); AWS CLI fallback at `C:\Users\admin\AppData\Local\Programs\Amazon\AWSCLIV2\aws.exe` (`--profile medo`); SSH fallback `ssh -i "D:\medo\AppHub\.secrets\medo-prod-key.pem" ubuntu@52.63.127.50`.

---

## Task 1 — GitHub Packages PAT + npm publish — **RESOLVED 27-11-26**

Goal: `@kiro-ai-bit/*` packages publishable to GitHub Packages so services stop using `file:` deps.

Steps (execution order):
1. `[U]` Create classic PAT at github.com/settings/tokens as `kiro-ai-bit`: name `medo-packages`, scopes `repo` + `read:packages` + `write:packages`. — **DONE**
2. `[U]` Store token as `GITHUB_PAT=` in `D:\medo\.env` (gitignored). — **DONE**
3. `[A]` Configure `C:\Users\admin\.npmrc`: `@kiro-ai-bit:registry=https://npm.pkg.github.com` + `//npm.pkg.github.com/:_authToken=${GITHUB_PAT}`. — **DONE** (`npm whoami` → `kiro-ai-bit`)
4. `[U/A]` Ensure PAT has **Packages write** — publish returned 403 `permission_denied`; either PAT lacks `write:packages` or loop never ran. Verify/edit token scopes if needed.
5. `[A]` Run publish loop, then verify.

Checklist:
- [x] `[U]` Classic PAT created with `repo` + `read:packages` + `write:packages`; never pasted in chat.
- [x] `[U]` `GITHUB_PAT` in `D:\medo\.env`; `.env` gitignored.
- [x] `[A]` Git push/pull works all 9 `kiro-ai-bit/medo-*` repos (parity `origin/main...HEAD = 0 0` at provisioning; `medo-identity` origin sanitized to token-free URL — push via `https://x-access-token:$GITHUB_PAT@github.com/kiro-ai-bit/<repo>.git`).
- [x] `[A]` `.npmrc` auth configured; `npm whoami` OK.
- [x] `[A]` **`npm publish` DONE 27-11-26** — all 6 packages live at v0.1.0 on npm.pkg.github.com. Required **classic PAT** (`ghp_...`, scopes `repo`+`write:packages`+`read:packages`) — fine-grained PATs (`github_pat_...`) are unsupported by GitHub Packages (GH issue #558). `~/.npmrc` + `D:\medo\.npmrc` use `${GITHUB_PAT}`; must `export GITHUB_PAT` (e.g. `set -a; source /d/medo/.env; set +a`) before npm commands or GETs 401.

Task 1 fully resolved — `npm view @kiro-ai-bit/contracts version` → `0.1.0`.

---

## Task 2 — AWS EC2 + SSM Parameter Store + Docker — **RESOLVED**

Goal: one always-on server for backend + secure secret storage.

Executed 26–27-11-26 by agent via `shared/scripts/infra/aws/` automation (guide `AWS-EC2-SETUP-GUIDE.md`, CFN `medo-ec2-infrastructure`) + aws-mcp + SSH; human dashboard steps were done by agent on user's behalf.

Checklist:
- [x] `[UA]` EC2 `medo-prod` `i-02a877587f196d8e4` running — `t3.micro`, Ubuntu 24.04 LTS, 20 GiB gp3, `ap-southeast-2`.
- [x] `[UA]` Elastic IP `52.63.127.50` allocated + associated (`elastic-ip.json`).
- [x] `[UA]` Security group `medo-prod-sg` (`sg-00ab2971516d6e06c`): inbound 80/443 open, 22 restricted.
- [x] `[UA]` IAM role `medo-ec2-role` + instance profile: `AmazonSSMManagedInstanceCore` + inline `ssm:GetParameter(s)/GetParametersByPath` on `/medo/prod/*` + KMS decrypt `aws/ssm`.
- [x] `[UA]` SSH key pair `medo-prod-key`; private key `AppHub\.secrets\medo-prod-key.pem`.
- [x] `[UA]` CloudFormation `medo-ec2-infrastructure` CREATE_COMPLETE.
- [x] `[A]` **33 SSM SecureStrings `/medo/prod/*`**: `/db/POSTGRES_PASSWORD` + `/db/<service>_PASSWORD` ×6 + `/db/BROKER_PASSWORD`; `/jwt/JWT_PRIVATE_KEY` + `/jwt/JWT_PUBLIC_KEYS`; `/services/<service>/SERVICE_PRIVATE_KEY` + `SERVICE_PUBLIC_KEYS` ×6; `/notification/VAPID_{PUBLIC,PRIVATE}_KEY` + `VAPID_SUBJECT` + `RESEND_API_KEY` + `EMAIL_FROM`; `/medicine/R2_{ENDPOINT,ACCESS_KEY_ID,SECRET_ACCESS_KEY,BUCKET_NAME,PUBLIC_BASE_URL}`; `/sentry/DSN`.
- [x] `[A]` Local records: `AppHub\.secrets\{instance-id.txt, elastic-ip.json, db-passwords.json, medo-prod-key.pem}`; deploy hints `AWS_REGION`/`EC2_HOST`/`EC2_USER` in `D:\medo\.env`.
- [x] `[A]` **Docker 29.10.1 + Compose v5.8.0** on EC2 via SSH + `05-install-docker.sh`; `docker ps` verified without sudo (docker group).
- [x] `[A]` Tooling: infra scripts `shared/scripts/infra/aws/`; SSM writes via aws-mcp `run_script`; Docker via SSH.

Pending: none for this task.

---

## Task 3 — Cloudflare R2 + DNS — **RESOLVED-BY-AGENT**

Goal: photo storage + domain DNS. Human steps: Namecheap NS switch + R2 free-plan enable (both done by user 27-11-26). Agent did everything else via Cloudflare MCP `execute` (JS sandbox → `cloudflare.request()`) + aws-mcp `run_script` for SSM.

Checklist:
- [x] `[U]` `simmaps.com` zone **active** on Cloudflare NS `evelyn/simon.ns.cloudflare.com` (user switched Namecheap NS; zone id `fbb94b5ef3b7684878c9c6d90a3bc9e4`, account `877f19f2931d079565c34ee359178113`).
- [x] `[U]` R2 free plan enabled on account.
- [x] `[A]` Bucket `medo-photos` created (APAC, Standard) via `POST /accounts/{id}/r2/buckets`.
- [x] `[A]` Custom domain `photos.simmaps.com` attached (minTLS 1.2) → auto CNAME→`public.r2.dev` proxied; SSL+ownership **active**; `https://photos.simmaps.com/` → 404 = live (empty bucket).
- [x] `[A]` API token `medo-prod-r2` via `POST /accounts/{id}/tokens` — Object Read&Write scoped to `medo-photos` only (perm groups `6a018a9f…` read + `2efd5506…` write). S3 creds derived per docs: AccessKeyId = token `id` `425779a47c…`, Secret = SHA-256(token `value`) computed inside MCP sandbox — raw token never exposed. Orphan token `a46ba4d9…` deleted.
- [x] `[A]` DNS records (zone `simmaps.com`):
  - `api` A → `52.63.127.50` DNS-only (Caddy terminates TLS) — resolves.
  - `app` CNAME → `cname.vercel-dns.com` DNS-only (pre-created for Task 5; Vercel requires DNS-only).
  - `photos` CNAME → `public.r2.dev` (auto-created by R2 custom domain — do not edit).
  - `notify` — Resend records added Task 4 (verified 28-11-26).
- [x] `[A]` SSM `/medo/prod/medicine/` 5 SecureStrings: `R2_ENDPOINT=https://877f19f2931d079565c34ee359178113.r2.cloudflarestorage.com`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME=medo-photos`, `R2_PUBLIC_BASE_URL=https://photos.simmaps.com`.
- [x] `[A]` Same values → `AppHub\medo-medicine\.env` lines 9–13 (gitignored) + `AppHub\.secrets\cloudflare.json` (full account/zone/R2/DNS/MCP record).
- [x] `[A]` Verified: `nslookup` api→52.63.127.50, NS→Cloudflare; `curl https://photos.simmaps.com/` → 404 live; `api.simmaps.com/health` → 000 expected (no deploy yet, ticket 31).

Notes: Cloudflare MCP OAuth needed re-auth with ALL permissions (`devin mcp logout/login cloudflare`, devin.exe full path not on PATH); `execute` intermittently fails "Failed to connect" — retry; registrar NS change is always human-only. Config: `.devin/mcp_config.local.json` + `.kiro/settings/mcp.json`; usage rules in `AGENTS.md` §Cloudflare access.

Pending: none — `notify` DNS records added + verified Task 4 (28-11-26).

---

## Task 4 — Resend sender + API key — **RESOLVED-BY-AGENT 28-11-26**

Goal: verified email sender `notify.simmaps.com` + API key in SSM.

Executed by agent via Resend REST API (`api.resend.com`, Bearer key from `D:\medo\.env`) + Cloudflare MCP `execute` + AWS CLI (`--profile medo`, re-authed via `aws login` browser flow). Domain created by agent (`POST /domains`, region `ap-northeast-1` — closest to PK users) since user had only created the account + API key.

Checklist:
- [x] `[U]` Resend account created + API key `re_...` pasted into `D:\medo\.env` `RESEND_API_KEY` (verified live — `GET /domains` 200).
- [x] `[A]` Domain `notify.simmaps.com` created via `POST /domains` — id `14394438-431b-4437-81c3-05d1003d056b`, region `ap-northeast-1`.
- [x] `[A]` All 4 DNS records added in Cloudflare zone `simmaps.com` via MCP `execute` and resolving (verified via `nslookup @1.1.1.1`):
  - TXT `resend._domainkey.notify` (DKIM `p=MIGf...`)
  - MX `send.notify` → `feedback-smtp.ap-northeast-1.amazonses.com` pri 10
  - TXT `send.notify` `v=spf1 include:amazonses.com ~all`
  - CNAME `rsend.notify` → `send.forge.rmta.net` (DNS-only)
- [x] `[A]` `POST /domains/{id}/verify` → **status `verified`, all 4 records verified** (28-11-26).
- [x] `[A]` API key stored: SSM `/medo/prod/notification/RESEND_API_KEY` SecureString (value-match verified vs `.env`) + `AppHub\.secrets\resend.json` + `AppHub\medo-notification\.env` `RESEND_API_KEY` (was `re_dev_placeholder`).
- [x] `[A]` `EMAIL_FROM` confirmed = `Medo <notifications@notify.simmaps.com>` (already correct in service `.env` + LLD §8.9).
- [x] `[A]` Resend MCP server configured earlier same session: local stdio `resend-mcp@2.29.0` via `mcp_env_bridge.py` in `.devin/mcp_config.local.json` + `.kiro/settings/mcp.json`; `initialize`+`tools/list` verified; `## Resend access` section in `AGENTS.md`.

Gotcha logged: AWS CLI needs `MSYS_NO_PATHCONV=1` for SSM names starting `/` under Git Bash (path mangling → ValidationException); aws-mcp MCP returned 0 tools after AWS session expiry — CLI fallback used after `aws login` re-auth.

---

## Task 5 — Vercel frontend — **RESOLVED-BY-AGENT 27-11-26**

Goal: live frontend at `app.simmaps.com`.

Executed by agent: Vercel MCP OAuth + `vercel` CLI 67.0.0 (device login `yaseenbuzdaarsky-6707`, hobby) + `vercel link` (created project `prj_VNnBaspirKEzeeyDLfKdfJVzSakr` + connected GitHub repo → push-to-deploy). Env vars + `GITHUB_PAT` secret set via CLI; `app.simmaps.com` added via `vercel domains add`; prod deploy Ready. Full record: `AppHub\.secrets\vercel.json`.

Prerequisite discovered: frontend `package.json` `file:../medo-shared` deps can't build on Vercel → switched to `@kiro-ai-bit/*@0.1.0` from GitHub Packages (Task 1 publish) + committed `.npmrc` with `${GITHUB_PAT}` + `GITHUB_PAT` Vercel secret. **Pushed 28-11-26** via PR #1 (repo ruleset requires PRs on `main`) → squash-merged `db0cb2e` → Vercel auto-deploy `dpl_AytbRDWDzjDKP7PPCWwTG2qXYjTr` state **READY** (prod, commit `db0cb2e`).

Checklist:
- [x] `[UA]` `medo-frontend` project created + GitHub repo connected (CLI `vercel link`).
- [x] `[A]` Env vars added: `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_APP_ENV` (prod+preview); `GITHUB_PAT` secret (prod+preview); `NEXT_PUBLIC_SENTRY_DSN` skipped (empty default).
- [x] `[A]` Production deployment succeeded — `medo-frontend-jzsoxjpkg-yaseenbuzdaarsky-6707.vercel.app` (state Ready).
- [x] `[UA]` `app.simmaps.com` added to project; Cloudflare CNAME `app`→`cname.vercel-dns.com` already valid (Vercel status: dns-change-recommended but working).
- [x] `[A]` `AppHub\.secrets\vercel.json` written.

Tell agent: `done 5` + final frontend URL.

---

## Cross-cutting — keys & local secrets — **DONE-AGENT** (local only)

- `[A]` Generated 26-11-26 (ES256/JWK + VAPID): bundle `AppHub\.secrets\medo-dev-keys.json` (local only) + `medo-prod-keys.json` (prod → SSM source; contains private keys — never commit).
- `[A]` Per-service gitignored `.env` written for `medo-identity`, `medo-care`, `medo-medicine`, `medo-schedule-dose`, `medo-notification`; `.env.example` in all 9 repos.
- `[A]` Prod equivalents in SSM only; private keys never committed.
- Note: `AppHub\medo-gamification` diverged via ticket-22 WIP (`origin/main...HEAD = 2 1` after fetch) — reconcile under ticket 22, do not force-push.
- Git identity rule (all commits): `Sir Asim <kiro-ai-bit@users.noreply.github.com>` via per-commit `git -c`, no bot trailers.

## After all 5 tasks

Tell agent: `provisioning human steps done` → agent verifies `npm view @kiro-ai-bit/contracts version` + DNS/HTTP checks (`api.simmaps.com`, `photos.simmaps.com`, `app.simmaps.com`, `notify.simmaps.com`) → ticket 30 resolved only if every box truly done → frontier moves to ticket `31-infra-compose-deploy`.

## Quick reference — where everything lives

| What | Where |
|---|---|
| Runbook/steps+progress | this file |
| Per-point status detail | this file (merged record) |
| SSM params (33 prod secrets) | `/medo/prod/*` ap-southeast-2, names in Task 2 |
| Local secrets vault | `D:\medo\AppHub\.secrets\` (+ `README.md` inventory — all files present incl. `resend.json`, `vercel.json`) |
| Deploy hints | `D:\medo\.env` (`AWS_REGION`/`EC2_HOST`/`EC2_USER`, `GITHUB_PAT`) |
| npm auth | `C:\Users\admin\.npmrc` |
| Infra automation | `shared/scripts/infra/aws/` (`AWS-EC2-SETUP-GUIDE.md`) |
| MCP configs | `.devin/mcp_config.local.json` + `.kiro/settings/mcp.json` (`aws-mcp`, `cloudflare`, `context7`, `vercel`, `resend`) |
| Agent usage rules | `AGENTS.md` §Context7 docs / §AWS access / §Cloudflare access |
