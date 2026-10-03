# Intraoral prosthetic spacing correction

Build: `2026-10-03-spacing.1`

## Defect and bounded repair

The intraoral prosthetic prompt returned before the restorative guidance and combined a spacing request with an absolute original-outline/width lock, a pixel-frozen incisal edge, and enamel-surface-only instructions. Older selections without `targetOrder` and spacing selected below first priority lacked a concrete closure goal.

The active selected cards now supply the complaint list independently of rank. Selected spacing permits bounded horizontal proximal-contour restoration at the existing tooth positions while keeping original vertical incisal limits, crown height, gingiva, tooth count and separate tooth boundaries. Automated screening no longer overrides that explicit target, and shade-only/preserve scopes retain their limits. Neutral sliders do not suppress an explicitly selected spacing request. Orthodontic movement is not requested for the prosthetic path.

The selected intraoral prosthetic path uses a true-alpha composite. It accepts model-produced enamel in conservative, vertically supported narrow dark corridors flanked by source enamel; it does not paint new teeth, force a warp, widen a missing-tooth span or fill a broad bite opening. Bio-Blend finishes the editable layer before the protected composite. Other generation paths keep their existing composition. AI/finalization failure preserves existing results instead of quietly substituting a cosmetic-only local output.

## Reproducible checks

- `node scripts/verify-spacing-simulation.mjs`: 37 synthetic prompt, scope, geometry and negative-fixture checks against production functions
- `node scripts/verify-access-recovery.mjs`: 23 existing authentication/recovery checks and inline-script syntax checks
- `node scripts/verify-spacing-canvas.mjs`: native Chromium Canvas/payload/finalization/token/refund regression; requires Playwright and a supported Chromium runtime. Optional `CF_PLAYWRIGHT_MODULE`, `CF_CHROMIUM` and `CF_CANVAS_SCREENSHOT` configure the test runtime

All fixtures are synthetic. No real patient images, accounts, paid generation calls, credentials, database writes or billing changes are required. Browser verification blocks external requests and uses a mocked image response.

## Limits and review

Color and corridor geometry are conservative heuristics, not anatomical segmentation or a clinical diagnostic test. Ambiguous gaps and cool/neutral enamel can remain unmodified. Real image-model quality is stochastic and must be reviewed by the clinician; automated tests do not establish clinical accuracy or guarantee complete closure on every photograph. Existing results are retained; a newly generated image is needed to use the repaired request pipeline.
