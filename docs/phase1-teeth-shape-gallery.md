# Phase 1 — Upper Anterior Teeth Shape Gallery / 上顎前歯形態ギャラリー

Implementation notes, blindspot pass, and validation record.
Branch: `chatgpt/phase1-invite-teeth-type` (Draft PR #6). Base: `claude/image-morphing-video-3kujgb`.

---

## 0. Blindspot pass

### Known Knowns (verified in code, with evidence)

| # | Fact | Evidence |
|---|------|----------|
| 1 | The five axes live in `state.simV96` (`shade, alignment, toothShape, scallop, smileFrame, bioBlend, master`), defaults in `DEF` (all 50, master 40). | `caseflow_studio_v96.html` ~18538 |
| 2 | `state.simV96` is **rebuilt** from `DEF + deriveFromSelections()` on every first generation launched from the simulator screen — foreign keys on it are wiped. | ~20813 in `generateSimulation` |
| 3 | Prompt building is centralized in `buildClinicalPrompt()` with exactly two disjoint paths: an intraoral early-return path (`ip` array) and a standard path (`parts` array). | ~18977–19292 |
| 4 | The backend payload (`buildSimulationPayload`) sends `params: state.simV96`, plus discrete flags (`intent_mode`, `minimal_change`, `correction_scope`) read from separate `state.*` keys — an established precedent for state that must survive the simV96 rebuild. | ~20032–20122 |
| 5 | Every result record snapshots `settings: JSON.parse(JSON.stringify(state.simV96))`; `selectSimResult` restores `state.simV96` from that snapshot; library saves (local + Supabase) carry `r.settings` through untouched. | 20661, 20858, 20486, 20431, 28967 |
| 6 | Session persistence (`cfPersist`) saves `simV96`, `simV82`, `simCustomPrompt` to `sessionStorage` (`cf_session_meta_v96`, 4 h TTL) and images to IndexedDB. `simIntentMode` etc. are **not** persisted. | 22466–22700 |
| 7 | The simulator page (treatment concept + chief complaint cards) is rebuilt by `rebuildSimulationStudioV95()` into `#simFinishPanel` via `innerHTML`, re-run on nav/DOM ready — any static DOM injected inside it is destroyed. | 18309–18409 |
| 8 | Sheet/dialog conventions: fixed full-viewport overlay + `.open` class, `role="dialog" aria-modal="true"`, backdrop button, `.cfSheetHandle/.cfSheetHead/.cfSheetClose` (see `cfPaletteOverlay`). No existing focus-trap utility. | 1220–1290, 5092–5130, 5703 |
| 9 | The swipe-back gesture handler treats any visible `[role="dialog"]` as an overlay and does **not** navigate screens while one is open. No `history.pushState` anywhere; browser Back leaves the SPA (unchanged behavior). | 20912–20940 |
| 10 | `html,body` and `.app` are `overflow:hidden`; screens scroll internally — a fixed overlay + `overscroll-behavior:contain` is sufficient scroll isolation. | 28, 134 |
| 11 | Dynamic Gradient System: `--c1/--c2/--blend`, `cfBgEdge`, palette JS already uses `color-mix(in srgb, …)`; luminance-derived text tokens exist. | 23–25, 5703+ |
| 12 | i18n is Japanese-fixed (`cfLang()` returns `'ja'`; the switch UI was removed); app convention is bilingual inline labels ("Shade / 色調"). | 26485 |
| 13 | Invite redemption rejects expired codes (`reason:'expired'`) in the latest `accept_invite_code` (migration 13 preserved the check); studio shows dedicated expired copy; the studio invite list already renders 残り時間/期限切れ. | migrations 01/09/13; studio 26432, 16867 |
| 14 | PR #6's trigger normalizes `expires_at` on **every** insert (`BEFORE INSERT`), covering both creation RPCs (`create_invite_code`, `create_user_invite`) and any future path; client input cannot extend it. | migration 20260710000100 |
| 15 | PR #5 is based on a stale base SHA (`74c91b4`); several of its "added" files already exist on the current base. It rewrites `caseflow_studio_v96.html` (+1931/−87) mostly in landing/hero/token areas. | PR #5 metadata + file list |
| 16 | `generateSimulation` recenters `alignment` to 50 after ortho generations and regenerates iteratively from the previous result — regeneration re-reads all state at prompt-build time, so any state-based prompt fragment automatically covers regeneration and post-slider regeneration. | 20860+ |
| 17 | Existing "Tooth Shape" **slider** is a bidirectional ovoid↔square intensity axis. The new gallery is a categorical form-family choice; the two are related but not competing (slider = intensity/direction, gallery = target family). | 19125+, 18538 |
| 18 | No test suite or smoke script exists on this branch; `.github/workflows` only deploys (Modal / Vercel). Validation is manual + syntax-level. | repo tree |

### Known Unknowns (resolved conservatively, or documented)

1. **Are migrations 13–18 already applied to production?** Their presence on the production branch strongly suggests yes. PR #6's migration (`20260710000100`) sorts *before* them, which Supabase CLI treats as an out-of-order migration on an up-to-date database. → Resolved conservatively: renamed to `20260717000019_…` (content byte-identical); see §6.
2. **Is backfilling legacy no-expiry active codes to `created_at + 7 days` the intended policy?** → **Resolved by the owner (2026-07-10, commit `dc75eb4`): Decision B** — legacy active codes receive a fresh seven-day grace period from migration-apply time (`now() + 7 days`), so outstanding invitations are not invalidated immediately.
3. **Does the admin UI need to distinguish expired vs redeemed?** It collapsed both into 使用不可. → Resolved additively: the badge now distinguishes 期限切れ / 使用済み / 無効化済み / 有効.
4. **Supabase environment access.** The Supabase MCP connection is not authorized in this session, so the migration could not be applied to a preview database from here. Validation of the SQL is static (syntax + logic review). Flagged in the PR checklist.
5. **The uploaded screen recording** (`ScreenRecording_07082026…​.mov`) could not be played in this environment; flow understanding is based on code reading and the provided static mockup screenshot.

### Unknown Knowns (things the codebase already decided that constrain us)

- `settings` snapshots are merged **into** `simV96` on gallery-variation switch (20486). Anything stamped into `settings` must be extracted, not merged, or it pollutes the axis state — handled in `selectSimResult`.
- The v9.5 wrapper *also* wraps `generateSimulation` and `go` (multiple layered wrappers). New behavior must be layered the same way (wrap, never replace), or a later layer silently discards it.
- `.app` is a max-480px phone-shaped shell even on desktop; "desktop wide" layouts are the same column. The gallery therefore needs no separate desktop layout, only keyboard support.
- The service workers cache the shell only; adding UI to the monolith increases the precache size but never caches case images (nothing in this change touches SW paths).

### Unknown Unknown candidates (watched during implementation)

- Another wrapper of `renderSimulator`/`go` loading *after* the new module could re-render the panel without the teeth-type field → mitigated by injecting the field from **inside** `rebuildSimulationStudioV95`'s template (it is the final authority on that panel).
- iOS Safari scroll-snap + `backdrop-filter` compositing jank → mitigated: single backdrop-filter layer, transforms/opacity only, no nested blurs on cards.
- PR #5 landing later could conflict textually in `caseflow_studio_v96.html` → all new code is one contiguous block appended before `</body>` plus 8 surgical one-to-three-line edits at unique anchors; conflict surface is minimal and enumerated in the PR body.

---

## 1. Implementation plan (ordered by decisions most likely to change)

1. **State ownership** — one canonical `state.simTeethType` (id + source + selected_at + optional_context {sex, age}). *Not* inside `simV96` (rebuilt on first generation, Known-Known #2). Follows the `simIntentMode` precedent but is additionally session-persisted and snapshotted.
2. **Entry point** — a compact "Teeth Type / 歯のタイプ" field rendered by `rebuildSimulationStudioV95()` between the chief-complaint grid and the note, i.e. after treatment-plan selection and before the generate button. Default "Auto / 自動"; always skippable; shows the current selection as its summary.
3. **Popup architecture** — a static overlay appended once at body level (panel innerHTML rebuilds cannot destroy it), `role="dialog" aria-modal="true"`, vertical scroll-snap carousel, opened/closed by class toggle like `cfPaletteOverlay`. Focus trap + Escape + backdrop close + reduced-motion fade implemented locally (no framework, no library).
4. **Specimens** — original inline SVG: two schematic upper central incisors per card, parameterized path pairs per form; deliberately diagrammatic (no photorealism, no third-party artwork).
5. **Prompt insertion point** — a single global `cfTeethTypePromptFragment(isIntraoral)`; `buildClinicalPrompt()` calls it once per path (its two paths are disjoint early-return branches). No other function builds teeth-type prompt text.
6. **Metadata** — `payload.teeth_type = {id, source, optional_sex, optional_age, prompt_version}` in `buildSimulationPayload`; `settings.teethType` stamped in `pushSimResult` (single place) → flows to local library, Supabase library, and the session snapshot with zero schema changes (JSON metadata already exists end-to-end). No DB migration.
7. **Navigation behavior** — dialog participates in the existing `[role="dialog"]` overlay detection (swipe-back safe); no history manipulation (app has none); underlying screen scroll position untouched (fixed overlay, internal scrolling only); focus restored to the opener on close.
8. **Accessibility** — labeled dialog, focus trap, Escape, arrow-key navigation between cards, Enter/Space select, 44px+ targets, selected state = border + check glyph + text (never color alone), `prefers-reduced-motion` collapses all transitions to fades.
9. **Visual system** — glass material from `--c1/--c2` via `color-mix`, existing radii/typography/shadow language, palette-linked internal glow on the source field, refraction line on selection; no new permanent palette, no replacement of the Dynamic Gradient System.
10. **Validation** — matrix in §7 below; performed checks recorded there truthfully (what was and was not run).
11. **Mechanical edits** — enumerated in §5; everything else lives in one appended `<style>` + `<script>` block (`cf-p1-teeth-type`).

### Priority order encoded in the prompt fragment

1. Explicit clinician instruction (`simCustomPrompt`) → 2. selected tooth form → 3. visible clinical findings → 4. optional age context → 5. optional sex context → 6. harmony/naturalness → 7. generic ideal proportions as soft reference only.

Sex/age are contextual hints only; the fragment states they must never override the explicit form choice or clinical findings, and no "masculine/feminine" mapping is used.

---

## 2. Decisions made

- `state.simTeethType` chosen over `state.simV96.teethType` (rebuild wipe, Known-Known #2) and over a new module-scoped variable (must be reachable by `cfPersist` and by the prompt builder). One canonical object; no competing variables.
- The gallery **stores the id only** plus optional context; labels/descriptions/prompt modifiers live in one frozen `CF_TEETH_TYPES` map so state can never carry stale copy.
- Sex options: Unspecified / Female / Male / Other・回答しない. Age: broad clinical ranges (未指定, 〜19, 20代 … 70代〜) rather than a free numeric — clinically sufficient for morphology context and less sensitive.
- Age/sex live in sessionStorage session meta only (same envelope that already carries case photos in IndexedDB) and in generation metadata; **never** localStorage.
- Regeneration semantics: switching to an older result variation restores that variation's teeth type (its `settings` are the record of what produced it) — consistent with how the five axes already behave.
- New-case reset: `clearPhotos` (the app's "start over" primitive, already hooked by `cfPersist`) resets the selection to Auto via the same wrapper pattern.
- PR #6 migration content retained **verbatim**; only the filename timestamp moved after the last existing migration (see §6).

## 3. Deviations

- CLAUDE.md's 200-line-per-commit law is exceeded by the gallery commit; the task explicitly prescribes this feature and commit structure, which is treated as the required ask. Logged here per the DONE rules.
- `supabase/migrations/` and `caseflow_admin.html` are touched only within the explicit §12 instruction of the task (validate/conservatively fix invite expiry).
- The result screen in the provided mockup shows a Teeth Type chip on the *result* page; this phase implements the selection field on the simulator page only (the specified entry point: after plan selection, before generation). The chip on the result page is a natural Phase-1.x follow-up.

## 4. Edge cases found

- First generation rebuilds `simV96` (wipe) — handled by separate state key.
- `selectSimResult` merges snapshots into `simV96` — teethType extracted and removed from the merge target.
- Ortho regeneration chains from the *previous result image*; the teeth-type fragment stays present in every pass (state-read at build time).
- The intraoral dark-contraster path forbids morphology repositioning; the fragment respects the incisal-trim rule by constraining itself to crown-outline character within existing edges (and is skipped entirely when it would contradict the absolute rule? No — it is emitted with an explicit subordination clause; the absolute rules in the path already override).
- Popup open during palette change: all colors are `var(--c1/--c2)`-derived, so live palette changes restyle the open dialog automatically.

## 5. Files and functions changed (mechanical edit list)

`caseflow_studio_v96.html`
1. `buildClinicalPrompt` — intraoral path: 1 fragment call before the intent block.
2. `buildClinicalPrompt` — standard path: 1 fragment call before the intent block.
3. `buildSimulationPayload` — add `payload.teeth_type` before return.
4. `pushSimResult` — stamp `r.settings.teethType`.
5. `selectSimResult` — extract/restore `state.simTeethType` from snapshot.
6. `rebuildSimulationStudioV95` — 1 line in the template: teeth-type field slot.
7. `cfPersist.saveAll` / `restoreAll` — persist/restore `simTeethType`.
8. Appended block `cf-p1-teeth-type-style` + `cf-p1-teeth-type` before `</body>`: all new CSS/JS/SVG.

`caseflow_admin.html` — invite badge distinguishes 有効/期限切れ/使用済み/無効化済み; custom expiry input disabled with a fixed-7-days note.

`supabase/migrations/` — `20260710000100_…` renamed to `20260717000019_…` (content identical).

## 6. Invite expiry validation (task §12)

| Check | Result |
|---|---|
| New codes expire 7 days after creation | ✅ BEFORE INSERT trigger sets `expires_at := now() + '7 days'` unconditionally |
| Applies to every creation path | ✅ trigger level (covers `create_invite_code`, `create_user_invite`, any direct insert) |
| Enforced server/database-side | ✅ trigger; function `security invoker`, exec revoked from public/anon/authenticated |
| Client cannot extend lifetime | ✅ trigger overwrites any supplied value (including the admin UI's optional date — now surfaced honestly in that UI) |
| Redemption rejects expired codes | ✅ `accept_invite_code` (mig. 01, preserved by 09 and 13): `expires_at <= now()` → `reason:'expired'` |
| Admin UI distinguishes active/expired/redeemed/revoked | ✅ after this branch's small additive change (was: expired+redeemed collapsed into 使用不可) |
| Error copy tells the user the code expired | ✅ studio: 「この招待コードは有効期限切れです。管理者に再発行をご依頼ください。」 |
| Redeemed/revoked history preserved | ✅ backfill `UPDATE` filters `revoked_at is null and used_count < max_uses`; no deletes |
| No duplicate trigger / conflicting migration | ✅ `drop trigger if exists` + unique function name; no other trigger on the table |
| Migration order | ✅ fixed conservatively: file renamed after `…000018` so it applies after all existing migrations on an up-to-date database |
| Legacy-code backfill policy | ✅ decided by the owner (commit `dc75eb4`): grace period `now() + 7 days` for active legacy codes (Decision B) |

## 7. Validation performed

Recorded truthfully; this environment is headless (no iOS device, no browser session with the deployed backend).

**Static / automated (run here):**
- All 80 inline `<script>` blocks of the modified `caseflow_studio_v96.html` (and `caseflow_admin.html`) extracted and parsed with `node --check`: 0 failures.
- Grep-audits: exactly one `teeth_type` payload writer, one settings stamper, one prompt-fragment builder; no `localStorage` writes from the new module; no service-worker changes.

**Headless functional smoke test (run here, real app in Chromium via Playwright — `docs/phase1-teeth-gallery-smoke.js`): 33 checks, 0 failures.** Covered: field renders on the simulator panel with Auto default; Auto + no context emits an *empty* prompt fragment (existing production prompts byte-identical); dialog semantics (`role=dialog`, `aria-modal`, labelled), six radios, focus moves in and returns to the opener; select→Apply commits the canonical state and updates the field summary; facial *and* intraoral `buildClinicalPrompt` paths carry the fragment with the subordination clauses; `buildSimulationPayload.teeth_type` additive with existing fields intact; Escape/backdrop cancel restore the prior selection; Auto reset clears context; `selectSimResult` restores a variation's tooth form without leaking a `teethType` key into `simV96`; `clearPhotos` resets to Auto; nothing teeth-related in `localStorage`; `cfPersist` session meta round-trips the selection; reduced-motion open/close; live palette swap restyles the open dialog; landscape sheet fits the viewport; 12 rapid open/close cycles cause zero DOM growth (this test caught and fixed a reopen-within-300 ms close-timer race and a landscape overflow).

Screenshots captured from the headless runs: gallery open (Auto centered), card selected, optional context, applied field state with toast, alternate green/gold palette, landscape.

**Manual matrix (requires a reviewer with a device — unchecked items are NOT claimed):**
- [ ] iPhone portrait / landscape, iPad portrait / landscape, desktop narrow / wide
- [ ] installed PWA + Safari browser mode + Chrome desktop
- [ ] Functional paths 1–22 of the task's validation matrix (open case → … → VoiceOver)
- [ ] Regression list (auth, consent, home, library, invite, upload, sliders, generation, token debit/refund, save/share, Morphing entry/preview, billing, admin, PWA update)

## 7.5 Feedback round (2026-07-10)

Clinician feedback applied and deployed:

1. **Sex/age moved out of the gallery** to the simulator panel as "Patient context / 患者情報（任意）" — after the treatment concept, **before the chief complaint cards** (two compact selects). Canonical storage unchanged (`simTeethType.optional_context`); the dialog's Auto-reset now resets the form only and no longer clears panel-owned context.
2. **Generated crowns did not reflect the selected form.** Root cause: the standing esthetic criteria instruct the model to "refine within the patient's own type (square/ovoid/triangular)" and rule (3) of the orthodontic knowledge base says to keep each tooth's individual form — both outranked the gentle fragment. The fragment is now an explicit **REQUESTED CHANGE … MANDATORY** block placed with the requested-changes assembly in both prompt paths, states that the clinician's selection **SUPERSEDES** any keep-own-form guidance, targets the central incisors first, and declares an unchanged outline an incorrect result. When only the form is selected (all axes neutral), the "No changes requested" sentence no longer fires.
3. **Specimens redrawn** in dental-lab presentation style (reference: Dentiqra card): glossy white crown pairs with sheen and faint vertical texture on dark clinical panels; the SVG gradient defs are injected at document level so the panel field icon renders before the dialog is ever opened (bug found in review screenshots).
4. **Auto = facial-type matched** (design language, not a diagnosis; reference: SKELETAL FACIAL PROFILE II): when a facial image is present and Auto is selected, MediaPipe face landmarks (already bundled for lip masks) classify 短頭型 brachy / 中顔型 mesio / 長顔型 dolicho from the facial index (`h(10→152)/w(234→454)`, jaw ratio `w(172→397)/w(234→454)`); mapping brachy→square (angular jaw) or rounded_square, mesio→ovoid, dolicho→tapered. The recommendation is computed before prompt build (bounded at 2.5 s so generation is never blocked), shown in the field ("Auto / 自動 ・推奨 …") and the Auto card, sent as `teeth_type.auto_recommended` + `facial_type`, and injected into the prompt as the starting direction. **Fallback:** if landmarks are unavailable, the prompt instructs the generator itself to read the facial type and apply the same mapping. ⚠️ The landmark thresholds (fi ≤1.26 / ≥1.42, ji ≥0.86) are initial values and should be calibrated against real clinical portraits.

Validation after this round: 40 headless checks, 0 failures (suite updated accordingly).

## 8. Open questions / known risks

- Legacy invite backfill policy (above) — needs product sign-off.
- PR #5 merge order: whichever of #5/#6 merges second must re-verify `caseflow_studio_v96.html`; overlap is small but the file is shared (see PR body §conflicts).
- The AI backend (`val.town` endpoint) silently ignores unknown payload fields today; `teeth_type` and the prompt fragment are designed so the prompt alone is sufficient — the structured field is additive for future backends.
- Repeated open/close memory behavior and low-end iPhone scroll smoothness must be validated on hardware.
