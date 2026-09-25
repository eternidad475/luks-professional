# CaseFlow Dev Console™ Guarded MVP

CaseFlow Dev Console™ は、CaseFlow Studio の GitHub リポジトリをチャット形式で調査し、dry-run で修正案を確認し、承認時だけ専用ブランチと Draft Pull Request を作成する管理者用の開発コンソールです。

English: CaseFlow Dev Console™ is an admin-only development console for chatting with the CaseFlow Studio GitHub repository, reviewing dry-run proposals, and creating a dedicated branch plus Draft Pull Request only after explicit approval.

## Added files

- `caseflow_dev_console.html`: 管理者用UI。Health / Search / Read file / Compare / Chat / Apply + Draft PR に対応します。
- `api/dev-agent.js`: Vercel Serverless Function。GitHub API と AI provider をサーバー側で呼び出します。
- `docs/caseflow-dev-console-setup.md`: セットアップ、安全設計、環境変数、制限事項のメモです。

## Required environment variables

```txt
CASEFLOW_DEV_CONSOLE_KEY=your-admin-password
GITHUB_TOKEN=github-fine-grained-token
CASEFLOW_DEV_REPO=eternidad475/luks-professional
CASEFLOW_DEV_BASE_BRANCH=claude/image-morphing-video-3kujgb
```

## Gemini 2.5 Flash setup

If CaseFlow Studio already has a Gemini / Google API key in Vercel, Dev Console can reuse it.

Preferred:

```txt
CASEFLOW_DEV_PROVIDER=gemini
GEMINI_API_KEY=existing-gemini-key
GEMINI_MODEL=gemini-2.5-flash
```

Also supported:

```txt
GOOGLE_API_KEY=existing-google-key
GOOGLE_GENERATIVE_AI_API_KEY=existing-google-key
GOOGLE_MODEL=gemini-2.5-flash
```

日本語:
既存のGemini 2.5 Flash用キーがVercelにある場合、`GEMINI_API_KEY` または `GOOGLE_API_KEY` としてDev Consoleで流用できます。明示的にGeminiを使う場合は `CASEFLOW_DEV_PROVIDER=gemini` を設定してください。

## Other AI providers

Anthropic:

```txt
ANTHROPIC_API_KEY=...
ANTHROPIC_MODEL=...
```

OpenAI:

```txt
OPENAI_API_KEY=...
OPENAI_MODEL=...
```

Provider priority:

```txt
CASEFLOW_DEV_PROVIDER=gemini     # Gemini first
CASEFLOW_DEV_PROVIDER=anthropic  # Anthropic first
CASEFLOW_DEV_PROVIDER=openai     # OpenAI first
CASEFLOW_DEV_PROVIDER=auto       # Default: Gemini, then Anthropic, then OpenAI
```

## Recommended first-use lock

```txt
CASEFLOW_DEV_DRY_RUN_ONLY=1
```

Optional guard settings:

```txt
CASEFLOW_DEV_MAX_CONTEXT_CHARS=70000
CASEFLOW_DEV_MAX_ACTIONS=3
CASEFLOW_DEV_ALLOWED_REPOS=eternidad475/luks-professional
CASEFLOW_DEV_ALLOW_SENSITIVE_EDITS=0
CASEFLOW_DEV_ALLOW_SELF_EDIT=0
```

## GitHub token permissions

Use a fine-grained token limited to the target repository.

- Contents: Read and write
- Pull requests: Read and write
- Metadata: Read-only

日本語: GitHub token は対象リポジトリだけに限定した fine-grained token を推奨します。

## Current features

- Health check
- Gemini 2.5 Flash provider support
- Anthropic / OpenAI fallback support
- GitHub code search
- Read file
- Compare branch diff
- Chat with AI provider
- Dry-run action proposal
- Apply to a working branch
- Draft PR creation
- Draft PR reuse when the same branch already has an open PR
- Secret redaction in returned text
- Repository allowlist
- Protected branch guard
- Protected/sensitive path guard
- Maximum action count guard

## Safety model

- No direct push to the base branch.
- Apply mode creates or reuses a working branch.
- Pull Requests are Draft PRs.
- Existing Draft PRs are reused instead of duplicated.
- Secrets are redacted before being returned to the browser.
- `CASEFLOW_DEV_DRY_RUN_ONLY=1` disables apply mode server-side.
- Payment/auth/patient/token-like paths are blocked unless `CASEFLOW_DEV_ALLOW_SENSITIVE_EDITS=1`.
- Dev Console self-editing is blocked unless `CASEFLOW_DEV_ALLOW_SELF_EDIT=1`.

日本語: 安全性を優先し、base branchへの直接pushは行いません。まずはdry-runで使用してください。

## Recommended first use

1. Merge this PR.
2. Set Vercel environment variables.
3. Start with `CASEFLOW_DEV_DRY_RUN_ONLY=1`.
4. Open `/caseflow_dev_console.html`.
5. Enter the admin key.
6. Press **Health**.
7. Confirm `Gemini: gemini-2.5-flash` is shown if Gemini is configured.
8. Keep mode as **Dry-run only**.
9. Ask the agent to inspect a small, specific issue.
10. Review the proposed actions in the raw JSON.
11. Switch to **Apply + Draft PR** only after the actions are clearly correct.

## Current limitation

This is not a full Claude Code replacement yet. It does not run shell commands, npm tests, visual preview checks, automatic patch loops, patch-only hunk updates, or per-file approval UI.

## Final checkpoint in this PR

Compared with `claude/image-morphing-video-3kujgb`, this branch only adds Dev Console-related files:

```txt
api/dev-agent.js
caseflow_dev_console.html
docs/caseflow-dev-console-setup.md
```

It does not modify the existing CaseFlow Studio production HTML or media assets.

## Next phase

- Vercel Preview deployment inspection
- GitHub Actions log reading
- branch diff viewer with inline file previews
- patch-only updates instead of full-file replacement
- explicit approval per file
- audit log storage
- role-based access
- repo-specific CaseFlow Studio system prompt
- Visual Simulation Studio / Morphing Video Studio regression checklist
- optional browser verification for `/landing`, `/caseflow_studio_v96.html`, and `/caseflow_dev_console.html`
