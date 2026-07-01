# CaseFlow Dev Console™ MVP

CaseFlow Dev Console™ は、CaseFlow Studio の GitHub リポジトリをチャット形式で調査し、dry-run で修正案を確認し、承認時だけ専用ブランチと Draft Pull Request を作成する管理者用の開発コンソールです。

English: CaseFlow Dev Console™ is an admin-only development console for chatting with the CaseFlow Studio GitHub repository, reviewing dry-run proposals, and creating a dedicated branch plus Draft Pull Request only after explicit approval.

## Files

- `caseflow_dev_console.html`  
  管理者用のブラウザUIです。  
  English: Browser UI for the admin console.

- `api/dev-agent.js`  
  Vercel Serverless Functionです。GitHub APIとAIモデルAPIをサーバー側で呼び出します。  
  English: Vercel Serverless Function that calls GitHub and the model provider from the server side.

## Required environment variables

Set these in Vercel Project Settings → Environment Variables.

```txt
CASEFLOW_DEV_CONSOLE_KEY=your-admin-password
GITHUB_TOKEN=github-fine-grained-token
CASEFLOW_DEV_REPO=eternidad475/luks-professional
CASEFLOW_DEV_BASE_BRANCH=claude/image-morphing-video-3kujgb
```

AI provider must be one of the following.

```txt
ANTHROPIC_API_KEY=...
ANTHROPIC_MODEL=...
```

or

```txt
OPENAI_API_KEY=...
OPENAI_MODEL=...
```

Optional:

```txt
CASEFLOW_DEV_DRY_RUN_ONLY=1
CASEFLOW_DEV_MAX_CONTEXT_CHARS=70000
```

## GitHub token permissions

Use a fine-grained token. Limit it to the target repository.

Recommended permissions:

- Contents: Read and write
- Pull requests: Read and write
- Metadata: Read-only

日本語:
GitHub token は、対象リポジトリだけに限定した fine-grained token を推奨します。必要な権限は Contents の読み書き、Pull requests の読み書き、Metadata の読み取りです。

## Safety model

The console is intentionally conservative.

- It does not push directly to the base branch.
- Apply mode creates or reuses a working branch.
- Pull Requests are created as Draft PRs.
- Secrets are never returned to the browser by the health endpoint.
- If `CASEFLOW_DEV_DRY_RUN_ONLY=1`, apply mode is disabled server-side.
- Billing, Stripe, auth, or patient-data code should not be edited unless explicitly requested and reviewed.

日本語:
安全性を優先し、base branch への直接pushは行いません。Applyモードでも専用ブランチに変更し、Draft PRを作成します。`CASEFLOW_DEV_DRY_RUN_ONLY=1` を設定すると、サーバー側で適用処理を無効化できます。

## Recommended first use

1. Open `/caseflow_dev_console.html`.
2. Enter the admin key.
3. Press **Health**.
4. Keep mode as **Dry-run only**.
5. Ask the agent to inspect a small, specific issue.
6. Review the proposed actions in the raw JSON.
7. Switch to **Apply + Draft PR** only after the actions are clearly correct.

日本語:
最初は必ず Dry-run only で使ってください。AIが返す `actions` の内容を確認し、対象ファイルと内容が正しい時だけ Apply + Draft PR に切り替えてください。

## Practical limitation of this MVP

This is not a full Claude Code replacement yet.

It can:

- search GitHub code,
- read files,
- call an AI model,
- propose file actions,
- create/update full files,
- create a Draft PR.

It does not yet:

- run `npm test` or `npm run build`,
- execute shell commands,
- inspect Vercel Preview visually,
- perform multi-step tool loops with automatic patch refinement.

日本語:
これはClaude Code完全互換ではなく、安全なMVPです。コード検索、ファイル読込、AI提案、ファイル作成/更新、Draft PR作成までを担当します。テスト実行、シェル実行、Previewの視覚検証、自動修正ループは次フェーズです。

## Next phase

A stronger version should add:

- Vercel Preview deployment inspection
- GitHub Actions log reading
- branch diff viewer
- patch-only updates instead of full-file replacement
- explicit approval per file
- audit log storage
- role-based access
- repo-specific CaseFlow Studio system prompt
- Visual Simulation Studio / Morphing Video Studio regression checklist

日本語:
次フェーズでは、Vercel Preview検証、GitHub Actionsログ読込、差分ビューア、ファイル単位の明示承認、監査ログ、CaseFlow Studio専用の回帰チェックリストを追加すると実用性が大きく上がります。
