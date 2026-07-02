# Phase 1 Emergency Beta Gate — 調査結果・設計・ロードマップ

> ステータス: 設計確定 / フロント実装済み（フラグOFF）/ **DB migration 3本適用済み（2026-07-02）**
> 適用済み: phase1_beta_gate / phase1_security_hardening / usage_events_admin_dashboard
> 開発者権限設定済み（eternidad475@gmail.com → role=developer, beta_access=true）
> ブートストラップ招待コード: DEV-BETA-0001（developer・invitee 1000・max_uses 1）
> 残る手動作業: ダッシュボードで Leaked Password Protection を有効化
> 最終更新: 2026-07-02

---

## 1. 現状調査サマリー

### 1.1 既に存在するもの（重要）

| 資産 | 場所 | 状態 |
|---|---|---|
| Supabase ログインゲート UI（Phase 3-A） | `caseflow_studio_v96.html` `#cfAuthGate`（~L4518） | **実装済み・`CF_AUTH_ENABLED=false` で無効化中** |
| トークンバッジ / 残高取得 / `cfConsumeToken()` | 同上（~L4668） | 実装済み・同フラグ内で無効化中 |
| トークン切れモーダル `#cfTokenEmpty` | 同上（~L4560） | 実装済み |
| 生成時のトークン消費ゲート | `generateViaAI`（L19784）/ `generateRefinedViaAI`（L24057） | 実装済み（`cfConsumeToken` が未定義なら素通し） |
| Supabase スキーマ | project `nuolihmfdjzofporhwkp`（唯一のプロジェクト＝実質Production） | `profiles` / `subscriptions` / `token_ledger` + `consume_token()` / `grant_tokens()` / `handle_new_user()`。migration 3件適用済み |
| 設計書 | `docs/subscription-auth-design.md` | Stripe構成・API設計あり（未実装） |
| デプロイ | `.github/workflows/deploy-vercel.yml` | `claude/image-morphing-video-3kujgb` ブランチ push → Vercel **Production** 直行 |

### 1.2 Supabase 現状（読み取り調査のみ・変更なし）

- ユーザー数: 1（開発者本人のみ）。実患者データなし。
- RLS: 全テーブル有効。policy は `auth.uid()` 直呼び（`(select auth.uid())` 未対応）。
- `profiles.update` policy に **WITH CHECK なし**（補強対象）。
- Security Advisor 警告:
  1. `consume_token()` が authenticated から実行可能な SECURITY DEFINER（→ 仕様どおりだが監視対象）
  2. **Leaked Password Protection 無効**（→ ダッシュボードで有効化。SQLでは不可）

### 1.3 ギャップ（Phase 1 で埋めるもの / 埋めないもの）

| 項目 | 状態 |
|---|---|
| 招待コード（invite_codes） | ❌ なし → **Phase 1 で新設** |
| role（developer/admin等） | ❌ profiles に列なし → **Phase 1 で追加** |
| feedback_items / admin_audit_logs | ❌ なし → **Phase 1 で新設** |
| token_ledger の台帳拡張（idempotency_key 等） | ❌ なし → **Phase 1 で追加（additive）** |
| Morphing GPU export のトークン消費 | ❌ 未消費（Sim系2箇所のみ消費） → **Phase 1.5** |
| Stripe 決済 API / webhook | ❌ 未実装 → **Phase 2（test mode）** |
| secure share URL / private storage / cases DB化 | ❌ → Phase 3+ |

### 1.4 v9.6 安定化指標（現状値）

- script block: 70 / parse error: **0**（コミットごとに `new Function` 検証を実施中）
- empty catch: **159**（漸減方針。新規コードでは禁止）
- `console.error`: 27（Library保存失敗・Export失敗は導入済み）
- `DOMContentLoaded` handler: **64**（Morphingサンプルpopupのタブ注入は無効化済み・再発防止コード導入済み）

---

## 2. Phase 1 実装方針

### 2.1 大原則: Production を壊さない「二重フラグ」

既存の `CF_AUTH_ENABLED=false` は温存し、新しい **Beta Gate v2** を独立した script block として追加する。

```
有効判定（cfGateEnabled）:
  1. URL ?beta_gate=on  → localStorage に保存して ON（Preview/Staging 検証用）
  2. URL ?beta_gate=off → 保存を消して OFF
  3. localStorage 'cf_beta_gate_v1'==='on' → ON
  4. それ以外 → CF_BETA_GATE_DEFAULT（現在 false）
```

- **Production（caseflow-studio.vercel.app）は挙動不変**。デフォルトOFF。
- Preview / Staging では `?beta_gate=on` を付けるだけで全機能を検証できる。
- 正式リリース時は `CF_BETA_GATE_DEFAULT` を `true` にする 1 行変更のみ。

### 2.2 can_use_app 判定

```
can_use_app =
  profile.role in ('developer','co_developer','admin')   … 課金免除
  OR active subscription（status in active/trialing かつ period_end > now）
  OR profile.beta_access = true（有効な招待コード承認済み）
```

- 判定はまずクライアント表示制御として実装。**最終的な強制力は RLS / RPC 側**（`accept_invite_code` / `consume_token` はサーバー側で検証）。
- 未招待ユーザーはログイン後も「招待コード入力画面」で止まる。

### 2.3 招待コードフロー

1. 管理者が `admin_create_invite_code()` RPC でコード発行（admin_audit_logs に記録）
2. 新規ユーザー: サインアップ → ログイン → 招待コード入力
3. `accept_invite_code(code)` RPC（SECURITY DEFINER）が原子的に:
   - 有効性検証（revoked_at / expires_at / used_count < max_uses / invited_email 一致 / 重複使用なし）
   - `profiles.beta_access=true`, `role`（コード指定があれば）設定
   - invitee へ `token_grant_invitee`（既定100）付与 → ledger `invitee_initial_beta_grant`
   - inviter へ `token_grant_inviter`（既定100）付与 → ledger `inviter_referral_beta_bonus`
   - `used_count` インクリメント、`invite_redemptions` に記録（同一ユーザー×同一コードに unique 制約 = 重複付与防止）
4. inviter ボーナスは「invitee の承認完了＝初回ログイン完了後」に付与される（仕様の推奨ルールを満たす）

### 2.4 フィードバック

- 送信フォーム: category / severity / message（page_path・user_agent は自動収集）
- INSERT のみ（RLS: `user_id = (select auth.uid())` の WITH CHECK）。SELECT 不可。
- 送信後: "Thank you. Your feedback has been sent. / ありがとうございます。フィードバックを送信しました。"
- 管理者（is_admin()）のみ SELECT / UPDATE（status, admin_notes）→ 閲覧・更新は admin_audit_logs に記録
- `ai_summary` 列は将来の CaseFlow Intelligence™ / sanitized GitHub Issue 化のための予約列

---

## 3. DB Migration 案（**未適用・提案**）

ファイル: `supabase/migrations/20260701000001_phase1_beta_gate.sql`（新規オブジェクトのみ）
ファイル: `supabase/migrations/20260701000002_phase1_security_hardening.sql`（既存 policy の再作成を含む）

### 3.1 追加されるもの（migration 1 = 破壊的変更なし）

- `profiles.role text default 'dentist'` + CHECK 制約（9ロール）
- `profiles.beta_access boolean default false`
- `token_ledger` に nullable 列追加: `organization_id / workspace_id / case_id / generation_id / provider / model / status / idempotency_key(unique)`
- 新テーブル: `invite_codes` / `invite_redemptions` / `feedback_items` / `admin_audit_logs`
- 関数: `is_admin()` / `is_privileged()` / `accept_invite_code(text)` / `admin_create_invite_code(...)` / `admin_revoke_invite_code(uuid)` / `admin_update_feedback(...)` / `admin_grant_tokens(uuid,int,text)`
- 各テーブルの RLS policy（新規のみ）

### 3.2 migration 2（既存オブジェクトに触れる部分 — リスク明示）

| 変更 | リスク | 回避策 |
|---|---|---|
| 既存4 policy を drop→create で `(select auth.uid())` 化 + UPDATE に WITH CHECK 追加 | drop〜create 間の一瞬、該当テーブルへのアクセスが拒否される | 1トランザクション内で実行（Postgres DDL はトランザクショナル）。ユーザー1名の現状では実質無リスク |
| `handle_new_user()` の初回付与を 10 → **0** に変更（招待経由で100付与に一本化） | 招待コードなしの新規登録者はトークン0になる | 招待制ベータでは仕様どおり。既存ユーザーの残高は変更しない。ロールバック用に旧定義をコメントで併記 |
| Leaked Password Protection | SQL不可 | **ダッシュボード操作**: Authentication → Providers → Password → Leaked password protection ON |

### 3.3 適用手順（ユーザー承認後）

1. Supabase MCP `apply_migration` で 1 → 2 の順に適用（どちらも冪等に書いてある）
2. `get_advisors(security)` 再実行で警告確認
3. 開発者本人の profile に `role='developer'` を手動設定（1行 UPDATE）
4. `admin_create_invite_code()` で `DEV-BETA-XXXX`（role=developer, invitee 1000）等を発行

---

## 4. フェーズ分解ロードマップ

| フェーズ | 内容 | 状態 |
|---|---|---|
| **1a** | 調査・設計・migration 案・本ドキュメント | ✅ 完了 |
| **1b** | フロント: Beta Gate v2（ログイン必須 + 招待UI + can_use_app + トークンバッジ接続）— フラグOFFで搭載 | ✅ 本コミット |
| **1c** | フロント: フィードバック送信フォーム + 管理者 Feedback Inbox + 招待コード管理UI | ✅ 本コミット |
| **1d** | migration 適用（ユーザー承認後）→ Preview で `?beta_gate=on` 検証 → smoke test | ⏳ 承認待ち |
| **1e** | `CF_BETA_GATE_DEFAULT=true` に切替（本番招待制開始） | ⏳ 1d 完了後 |
| **1.5** | Morphing GPU export にもトークン消費を接続 / generation_refund 自動化 | 未着手 |
| **2** | Stripe test mode: checkout / webhook / subscriptions 同期（serverless 関数） | 未着手 |
| **3** | cases DB化 / private storage / secure share URL | 未着手 |
| **4** | Next.js 分割移行 / CaseFlow Intelligence™ | 構想 |

## 5. Production Smoke Test チェックリスト（1e 後に実施）

- [ ] 本番URLが開ける（https://caseflow-studio.vercel.app/caseflow_studio_v96.html）
- [ ] ログイン画面が表示される
- [ ] 「Currently available to invited dental professionals only.」文言表示
- [ ] developer / admin がログインできる（課金なしで通過）
- [ ] 無効な招待コードが拒否される / 有効なコードで通過できる
- [ ] トークン残高バッジが表示される
- [ ] ダミーデータで1回だけテスト生成（トークン -1 が ledger に記録）
- [ ] フィードバック送信 → 完了文言表示
- [ ] 管理者が Feedback Inbox で受信確認・status 変更できる
- [ ] Library / Export / Morphing / Photo Manager の主要導線が壊れていない
- [ ] iPhone Safari / iPad / Mac Chrome で上記確認

## 6. 既存機能への影響リスクと回避策

| リスク | 回避策 |
|---|---|
| ゲートUIが既存 overlay（sampleVideoOverlay 等）と z-index 競合 | 既存 gate と同じ 2147483646 帯を使用。gate 表示中は本体操作不可が仕様 |
| 新 script block の parse error が全体を壊す | コミット前に全 block `new Function` 検証（今回 0 エラー確認済み） |
| 旧 Phase 3-A gate と二重表示 | 旧 gate は `CF_AUTH_ENABLED=false` のまま温存。v2 は同じ DOM を再利用せず独立 |
| Supabase 障害時にアプリが開けない | gate 有効時のみの挙動。CDN/クライアント初期化失敗時はエラーメッセージ表示（白画面にしない） |
| localStorage 不可（iOS private mode） | try/catch + sessionStorage フォールバック。gate 判定はメモリ内フォールバック |

## 7. 秘密情報の取り扱い（変更なしの確認）

- フロントに存在するのは **anon key のみ**（公開可・RLS前提）— 仕様どおり
- service_role key / Stripe secret / Modal Token は今回も一切コードに含めない（GitHub Secrets / Modal secrets のみ）
- `grant_tokens()` は revoke 済みで service_role 専用のまま。新設 `admin_grant_tokens()` は is_admin() チェック付き
