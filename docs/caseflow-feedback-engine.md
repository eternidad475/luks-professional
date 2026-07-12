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

### 1C — Admin Feedback Engine panel (`caseflow_studio_v96.html`)
- Added inside the existing admin modal (no nav restructure): **Overview** stat tiles (total / Good% / Bad% / top-bad reason / recent-7d / aggregate opt-in) + **Review Stream** with rating/module filters, calling `admin_feedback_overview()` and `admin_feedback_reviews()`. Intentional empty state (`臨床フィードバックはまだ記録されていません。`). Truncated `output_id`, no raw prompt in the first-level UI.

## Migration status
- **APPLIED to the production Supabase project** (`nuolihmfdjzofporhwkp`) on approval — additive only (new table + 2 RPCs); existing tables/RLS/billing untouched. Security advisor: the 2 new RPCs show the same expected `authenticated_security_definer_function_executable` WARN as every existing `admin_*` RPC (each self-gated by `is_admin()` raising `not_authorized`) — consistent, no new/unique risk. New table has RLS enabled with policies.

## Deviations
- **API vs client insert:** followed the spec's serverless endpoint (server-side validation) rather than the app's usual client-side RLS insert.

### Morphing result surface
- The clinical card is also surfaced on morph **video export** (`setExportBlob` hook) with `studio_module:'morphing_video'`, `artifact_type:'video'` — morph-specific reason tags shown, no token/regeneration side effects.

## Validation (§18 matrix, headless)
- 39 E2E checks green, incl.: reason tags hidden until Good/Bad; no auto-submit; explicit Submit records rating+tag+consent; stable output_id; **submit payload carries no raw image / no client `user_id`**; consent defaults false; **feedback never consumes a token**; **never triggers regeneration**; morph module surfaces morph-only tags; no duplicate card in the DOM; admin empty state.
- 81 inline JS blocks `node --check`: 0 failures. `api/feedback/submit.js` `node --check`: OK.

## Remaining (post-merge, optional)
- §20 screenshot gate as a formal CI artifact; per-user personalization / refinement-suggestion phases (interface boundaries reserved, not built — per §17).

## Rollback
- Frontend/API: revert the branch (no prod impact — Preview only).
- DB (if applied): `drop function admin_feedback_reviews...; drop function admin_feedback_overview(); drop table public.caseflow_feedback_reviews;` — additive objects only; no existing data touched.
