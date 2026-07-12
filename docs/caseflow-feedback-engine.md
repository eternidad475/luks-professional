# CaseFlow Feedback Engine™ / Clinical Curation Loop — Phase 1 (draft)

Branch: `caseflow/feedback-engine-phase1` (Preview only — **not** production).
Base commit: `34217e9` on the production line.

> *Every review becomes structured clinical intelligence. / すべてのレビューを、構造化された臨床知へ。*

## Blindspot pass (verified in code)

- **Production/preview separation.** Production deploys from `claude/image-morphing-video-3kujgb` (`deploy-vercel.yml --prod`). Branch **previews** deploy from `caseflow/**` / `chatgpt/**` (`deploy-preview.yml`). This feature is on `caseflow/feedback-engine-phase1` → Preview only.
- **`feedback_items` is a support/bug inbox** (`category/severity/message/status`, user-insert + admin-read RLS, admin modal). Per spec, **not overloaded** — a new table is introduced.
- **Admin authz** is server-side: `public.is_admin()` (`role in developer/admin`, SECURITY DEFINER, fixed `search_path`) from migration `…0001`. Reused as-is; no `user_metadata` trust.
- **Audit/analytics** already exist: `admin_audit_logs` (DEFINER insert) and `usage_events` (`cfLogEvent`).
- **No PHI to LLMs.** Only the screening image goes to the val.town proxy; no landmark arrays or patient images are stored in feedback.
- **Submit convention.** Existing feedback uses client-side supabase-js inserts; Stripe uses serverless functions with `SUPABASE_SERVICE_ROLE_KEY` + `admin.auth.getUser(jwt)`. This feature follows the **serverless** pattern per spec.
- **A lightweight result-screen card already shipped** to production (`cfFbe`, Good/Bad + casual chips, localStorage only). This phase **evolves that same surface** into the clinical version — no third feedback UI.

## What Phase 1 delivers here

### 1A — Database (`supabase/migrations/20260718000020_caseflow_feedback_reviews.sql`)
- New table `public.caseflow_feedback_reviews` (additive; existing tables untouched).
  Structured judgement + non-PHI generation metadata; **no raw images, no landmark arrays.**
- Indexes: user, created_at, output_id, module, rating, workspace, GIN(reason_tags).
- RLS: user insert/select/update **own** rows; admin read-all via `is_admin()`; **no delete** policy.
- `updated_at` touch trigger.
- Admin RPCs (SECURITY DEFINER, `is_admin()` gate, fixed `search_path`, `authenticated`-only execute):
  - `admin_feedback_overview()` → aggregate counts / rates / top-bad / module breakdown / opt-in count.
  - `admin_feedback_reviews(...)` → filtered review stream (rating/module/artifact/tag/date, limit/offset); returns truncated `output_id`, **no raw prompt**.

### 1B — Submit endpoint (`api/feedback/submit.js`)
- `POST /api/feedback/submit`, `Authorization: Bearer <supabase token>`; `user_id` derived from the **verified token only** (never the body).
- Validates: `output_id` required; `rating`/`artifact_type`/`studio_module` enums; `reason_tags` allowlist (§7/§8); comment/metadata size caps; oversized metadata dropped (never fails the request).
- Never touches tokens/billing. Normalized, user-safe errors (`feedback_not_enabled` when the table isn't present yet).

### 1B — Result-screen clinical card (`caseflow_studio_v96.html`, `cf-p1-feedback*`)
- Progressive disclosure: **Good/Bad → reveal** relevant clinical reason tags (bilingual, morph-only tags hidden for image module) + optional comment + **aggregate-learning consent (default OFF)** → **explicit Submit** (never auto-submits on Good/Bad tap).
- Posts to `/api/feedback/submit`; on any failure falls back to `result.settings.feedback` + `usage_events` so the clinician is never blocked.
- Inherits the dynamic palette (`--c1/--c2`), stays above the bottom nav (`bottom: calc(86px + safe-area)`), ≥44px targets, reduced-motion fallback, × dismiss, 30s auto-hide.
- Stamps a stable `output_id` on the result record for lineage.

## Deviations
- **API vs client insert:** followed the spec's serverless endpoint (server-side validation) rather than the app's usual client-side RLS insert.
- **Admin dashboard (1C)** — Overview + Review Stream UI — is **not yet wired** in this commit; the RPCs it will call are already shipped in the migration. Next increment.

## Remaining before production (per spec)
- Apply the migration to the production Supabase project (**awaiting explicit approval** — it is the only irreversible step; additive, isolated).
- 1C admin Feedback Engine panel (Overview + Review Stream) using the two RPCs.
- Full regression matrix (§18, 30 checks), Preview screenshot gate (§20), readiness report.
- **Do not merge to production** until approved.

## Rollback
- Frontend/API: revert the branch (no prod impact — Preview only).
- DB (if applied): `drop function admin_feedback_reviews...; drop function admin_feedback_overview(); drop table public.caseflow_feedback_reviews;` — additive objects only; no existing data touched.
