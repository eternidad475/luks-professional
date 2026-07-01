# CaseFlow Dev Console™ Guarded MVP

CaseFlow Dev Console™ は、CaseFlow Studio の GitHub リポジトリをチャット形式で調査し、dry-run で修正案を確認し、承認時だけ専用ブランチと Draft Pull Request を作成する管理者用の開発コンソールです。

English: CaseFlow Dev Console™ is an admin-only development console for chatting with the CaseFlow Studio GitHub repository, reviewing dry-run proposals, and creating a dedicated branch plus Draft Pull Request only after explicit approval.

## Added files

- `caseflow_dev_console.html`  
  管理者用のブラウザUIです。Health / Search / Read file / Compare / Chat / Apply + Draft PR を扱います。  
  English: Browser UI for Health, Search, Read file, Compare, Chat, and Apply + Draft PR.

- `api/dev-agent.js`  
  Vercel Serverless Functionです。GitHub APIとAIモデルAPIをサーバー側で呼び出します。  
  English: Vercel Serverless Function that calls GitHub and the model provider from the server side.

- `docs/caseflow-dev-console-setup.md`  
  セットアップ、安全設計、環境変数、制限事項をまとめた文書です。  
  English: Setup, safety model, environment variables, and limitations.

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

Recommended first-use lock:

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

Use a fine-grained token. Limit it to the target repository.

Recommended permissions:

- Contents: Read and write
- Pull requests: Read and write
- Metadata: Read-only

日本語:
GitHub token は、対象リポジトリだけに限定した fine-grained token を推奨します。必要な権限は Contents の読み書き、Pull requests の読み書き、Metadata の読み取りです。

## Current features

The guarded MVP supports:

- Health check
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

日本語:
現時点では、Health確認、GitHubコード検索、ファイル読込、ブランチ差分確認、AI相談、dry-run提案、作業ブランチへの適用、Draft PR作成、既存Draft PR再利用、秘密情報のマスク、許可リポジトリ制限、保護ブランチ制限、危険パス制限、最大操作数制限に対応しています。

## Safety model

The console is intentionally conservative.

- It does not push directly to the base branch.
- Apply mode creates or reuses a working branch.
- Pull Requests are created as Draft PRs.
- Existing Draft PRs are reused instead of duplicated.
- Secrets are redacted before being returned to the browser.
- Secrets are never returned by the health endpoint.
- If `CASEFLOW_DEV_DRY_RUN_ONLY=1`, apply mode is disabled server-side.
- If `CASEFLOW_DEV_ALLOW_SENSITIVE_EDITS` is not enabled, payment/auth/patient/token-like paths are blocked.
- If `CASEFLOW_DEV_ALLOW_SELF_EDIT` is not enabled, the Dev Console files themselves are blocked from self-modification.

日本語:
安全性を優先し、base branch への直接pushは行いません。Applyモードでも専用ブランチに変更し、Draft PRを作成します。既存のPRがある場合は再利用します。`CASEFLOW_DEV_DRY_RUN_ONLY=1` を設定するとサーバー側で適用処理を無効化できます。Stripe・課金・認証・患者情報・token系のファイルは、明示的に許可しない限りブロックします。

## Recommended first use

1. Merge this PR.
2. Set Vercel environment variables.
3. Start with `CASEFLOW_DEV_DRY_RUN_ONLY=1`.
4. Open `/caseflow_dev_console.html`.
5. Enter the admin key.
6. Press **Health**.
7. Keep mode as **Dry-run only**.
8. Ask the agent to inspect a small, specific issue.
9. Review the proposed actions in the raw JSON.
10. Switch to **Apply + Draft PR** only after the actions are clearly correct.

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
- compare branch diff,
- create/reuse a Draft PR.

It does not yet:

- run `npm test` or `npm run build`,
- execute shell commands,
- inspect Vercel Preview visually,
- perform multi-step tool loops with automatic patch refinement,
- apply small patch hunks instead of full-file replacement,
- manage per-file approval inside the UI.

日本語:
これはClaude Code完全互換ではなく、安全なMVPです。コード検索、ファイル読込、AI提案、ファイル作成/更新、差分確認、Draft PR作成/再利用までを担当します。テスト実行、シェル実行、Previewの視覚検証、自動修正ループ、patch単位の編集、ファイル単位の承認UIは次フェーズです。

## Next phase

A stronger version should add:

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

日本語:
次フェーズでは、Vercel Preview検証、GitHub Actionsログ読込、インライン差分ビューア、patch単位の更新、ファイル単位の明示承認、監査ログ、CaseFlow Studio専用の回帰チェックリスト、ブラウザ検証を追加すると実用性が大きく上がります。
