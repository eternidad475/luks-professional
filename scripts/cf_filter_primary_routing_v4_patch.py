from pathlib import Path
import subprocess

BASE = "origin/claude/image-morphing-video-3kujgb"
PAYLOAD = "origin/chatgpt/primary-routing-v4-payload"
HTML = "caseflow_studio_v96.html"
SMOKE = "docs/primary-routing-v4-smoke.js"
OUT = Path("/tmp/cf-primary-routing-v4-filtered.patch")

result = subprocess.run(
    ["git", "diff", "--no-ext-diff", "--unified=3", BASE, PAYLOAD, "--", HTML, SMOKE],
    check=True,
    text=True,
    capture_output=True,
)
lines = result.stdout.splitlines(keepends=True)

sections = []
current = []
for line in lines:
    if line.startswith("diff --git ") and current:
        sections.append(current)
        current = [line]
    else:
        current.append(line)
if current:
    sections.append(current)

wanted_tokens = (
    "CF_PRIMARY_ROUTING_ISOLATION_V4",
    "cfCheckPrimaryRun(runCtx)",
    "cfScheduleTempSimSave",
    "CF_PRIMARY_RESULT_DEADLINE_MS",
    "__cfPrimaryGenerationActive",
    "__cfPendingGallerySync",
    "requestAnimationFrame(()=>requestAnimationFrame(ensureResult))",
    "Finalizing clinical preview",
    "cf-primary-routing-isolation-v4",
)
forbidden_tokens = (
    "icon-180-v2",
    "icon-192-v2",
    "icon-512-v2",
    "favicon-32-v2",
    "CF_TEETH_SEX",
    "Non-binary / ノンバイナリー",
    "cfTtCtxHint",
    "maskable-512-v2",
)

output = []
kept_hunks = 0
for section in sections:
    if not section:
        continue
    header_line = section[0]
    if f" b/{SMOKE}" in header_line:
        output.extend(section)
        continue
    if f" b/{HTML}" not in header_line:
        continue

    first_hunk = next((i for i, line in enumerate(section) if line.startswith("@@ ")), None)
    if first_hunk is None:
        continue
    header = section[:first_hunk]
    hunks = []
    current_hunk = []
    for line in section[first_hunk:]:
        if line.startswith("@@ ") and current_hunk:
            hunks.append(current_hunk)
            current_hunk = [line]
        else:
            current_hunk.append(line)
    if current_hunk:
        hunks.append(current_hunk)

    selected = []
    for hunk in hunks:
        body = "".join(hunk)
        if any(token in body for token in wanted_tokens):
            selected.extend(hunk)
            kept_hunks += 1
    if selected:
        output.extend(header)
        output.extend(selected)

patch = "".join(output)
if kept_hunks < 7:
    raise SystemExit(f"expected at least 7 production hunks, kept {kept_hunks}")
for token in forbidden_tokens:
    if token in patch:
        raise SystemExit(f"filtered patch still contains forbidden regression token: {token}")
for token in ("CF_PRIMARY_ROUTING_ISOLATION_V4", "cfScheduleTempSimSave", "Finalizing clinical preview"):
    if token not in patch:
        raise SystemExit(f"filtered patch is missing required token: {token}")

OUT.write_text(patch, encoding="utf-8")
print(f"wrote {OUT} with {kept_hunks} selected HTML hunks")
