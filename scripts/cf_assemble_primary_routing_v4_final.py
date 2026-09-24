from pathlib import Path

html_path=Path('caseflow_studio_v96.html')
html=html_path.read_text(encoding='utf-8')

bad="""            const j=await res.json();
      cfCheckPrimaryRun(runCtx);
            const arr=Array.isArray(j)?j:(j&&Array.isArray(j.findings)?j.findings:null);"""
good="""            const j=await res.json();
            const arr=Array.isArray(j)?j:(j&&Array.isArray(j.findings)?j.findings:null);"""
if bad not in html:
    raise SystemExit('undefined runCtx screening insertion not found')
html=html.replace(bad,good,1)

marker="""    const quickTask=cfFastPrimaryPreview(src,state.simV96||{}),aiOn=aiEnabled();"""
replacement="""    // Reuse only findings that are already available. Do not launch a new heavy
    // screening task on the first-result critical path; this preserves prompt quality
    // when upload-time screening completed, while keeping the 16 s routing contract.
    const cachedFindings=Array.isArray(src.problemList)?src.problemList:null;
    if(cachedFindings&&cachedFindings.length)src.problemList=cachedFindings;
    const quickTask=cfFastPrimaryPreview(src,state.simV96||{}),aiOn=aiEnabled();"""
if marker not in html:
    raise SystemExit('primary quickTask marker not found')
html=html.replace(marker,replacement,1)
html_path.write_text(html,encoding='utf-8')

workflow="""name: Test primary routing v4

on:
  push:
    branches:
      - chatgpt/primary-routing-v4-final
    paths:
      - caseflow_studio_v96.html
      - sw.js
      - docs/primary-routing-v4-smoke.js
      - .github/workflows/cf-test-primary-routing-v4.yml
  pull_request:
    branches:
      - claude/image-morphing-video-3kujgb
    paths:
      - caseflow_studio_v96.html
      - sw.js
      - docs/primary-routing-v4-smoke.js
      - .github/workflows/cf-test-primary-routing-v4.yml

jobs:
  smoke:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 1
      - uses: actions/setup-node@v4
        with:
          node-version: 20
      - run: npm install --no-save playwright@1.54.1
      - run: npx playwright install --with-deps chromium
      - name: Static routing guards
        run: python3 scripts/cf_validate_primary_routing_v4.py
      - name: Start local server
        run: python3 -m http.server 4173 >/tmp/cf-http.log 2>&1 &
      - name: Run stalled-AI smoke test
        run: node docs/primary-routing-v4-smoke.js
"""
Path('.github/workflows/cf-test-primary-routing-v4.yml').write_text(workflow,encoding='utf-8')

validator="""from pathlib import Path
s=Path('caseflow_studio_v96.html').read_text(encoding='utf-8')
assert 'Preparing morphing sequence' not in s
assert 'モーフィングシークエンスを準備中' not in s
assert 'const CF_PRIMARY_RESULT_DEADLINE_MS=16000' in s
assert 'cfCheckPrimaryRun(runCtx);\\n            const arr=Array.isArray(j)' not in s
assert 'requestAnimationFrame(()=>requestAnimationFrame(ensureResult))' in s
assert 'cfsw-v4-primary-routing' in Path('sw.js').read_text(encoding='utf-8')
print('primary routing v4 static guards passed')
"""
Path('scripts/cf_validate_primary_routing_v4.py').write_text(validator,encoding='utf-8')
