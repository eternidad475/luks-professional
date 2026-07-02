# Phase 2 — Stripe 連携セットアップ手順（test mode / 料金確定版）

> 本番課金は未開始。すべて **Stripe test mode** 前提。
> Secret key / Webhook secret / service_role key は Vercel 環境変数のみ（フロント・リポジトリに置かない）。
> 旧 Sketch/Studio・年額プランは廃止（コード上は表示互換のみ残存）。

## 1. 確定プラン

| プラン | 価格 | tokens | 種別 | 処理 |
|---|---|---|---|---|
| Trial | 0円 | 10（初回のみ・約5回分） | — | `claim_trial_tokens()` RPC（Stripe不使用・支払い方法不要） |
| Personal | 1,500円/月 | 100/月（約50回分） | subscription | invoice.payment_succeeded で付与 |
| Clinic | 5,000円/月 | 500/月（約250回分） | subscription | 同上 |
| Add-on Mini | 500円 | +20 | one-time payment | checkout.session.completed で即時付与 |
| Add-on Standard | 2,000円 | +100 | one-time payment | 同上 |
| Add-on Plus | 5,000円 | +300 | one-time payment | 同上 |
| Developer | 無料 | 管理者付与 | — | 非公開（role免除＋admin_grant） |
| Enterprise | 個別契約 | — | — | UI非表示（問い合わせ） |

**トークン消費**: Visual Simulation 作成 = 2 tokens ／ Morphing Video 書き出し = 2 tokens ／ 再生成 = 2 tokens。
スライダー調整・比較・保存・Library/Gallery/Project閲覧・生成前プレビューは消費なし。
**失敗生成**: 原則消費なし — 消費後に失敗した場合は `refund_generation_tokens()` が自動返却（15分以内・二重返却防止付き）。

## 2. Stripe Dashboard で作成するもの（test mode）

| Product | Price | env 変数名 |
|---|---|---|
| CaseFlow Personal | 1,500 JPY recurring/month | `STRIPE_PRICE_PERSONAL_MONTHLY` |
| CaseFlow Clinic | 5,000 JPY recurring/month | `STRIPE_PRICE_CLINIC_MONTHLY` |
| CaseFlow Add-on Mini | 500 JPY one-time | `STRIPE_PRICE_ADDON_MINI` |
| CaseFlow Add-on Standard | 2,000 JPY one-time | `STRIPE_PRICE_ADDON_STANDARD` |
| CaseFlow Add-on Plus | 5,000 JPY one-time | `STRIPE_PRICE_ADDON_PLUS` |

- Customer Portal を有効化（Settings → Billing → Customer portal）
- Webhook endpoint: `https://<デプロイURL>/api/stripe/webhook`
  イベント: `checkout.session.completed` / `customer.subscription.created` / `customer.subscription.updated` / `customer.subscription.deleted` / `invoice.payment_succeeded` / `invoice.payment_failed`

## 3. Vercel 環境変数

| 変数 | 公開可否 |
|---|---|
| `STRIPE_SECRET_KEY`（sk_test） | **server only** |
| `STRIPE_WEBHOOK_SECRET` | **server only** |
| `SUPABASE_URL` | server |
| `SUPABASE_SERVICE_ROLE_KEY` | **server only・絶対にフロント禁止** |
| `NEXT_PUBLIC_APP_URL` | 公開可 |
| `STRIPE_PRICE_PERSONAL_MONTHLY` / `STRIPE_PRICE_CLINIC_MONTHLY` / `STRIPE_PRICE_ADDON_MINI` / `STRIPE_PRICE_ADDON_STANDARD` / `STRIPE_PRICE_ADDON_PLUS` | server only |

旧 env（`STRIPE_PRICE_SKETCH_*` / `STRIPE_PRICE_STUDIO_*`）は廃止。webhook は互換のため設定が残っていれば personal/clinic として解釈する。

## 4. Supabase migration

- **migration 5（適用済み）**: billing_customers / billing_subscriptions / billing_events / claim_trial_tokens / admin_list_billing / trial_tokens_granted
- **migration 6（新規・要適用）** `20260704000006_multi_token_consume_refund.sql`:
  - `consume_tokens(p_amount, p_reason)` — 原子的な複数トークン消費（ledger_id を返す）
  - `refund_generation_tokens(p_ledger_id)` — 失敗時返却（本人・消費行・generation系reason・15分以内・`refund:<id>` idempotency）
  - 旧 `consume_token()`（1消費）は互換のため残置。migration 6 未適用でもフロントは自動フォールバック（1トークン消費）で動作

## 5. token_ledger reason 一覧

`trial_grant` / `subscription_personal_monthly` / `subscription_clinic_monthly` / `token_addon_mini` / `token_addon_standard` / `token_addon_plus` / `admin_grant` / `invitee_initial_beta_grant`・`inviter_referral_beta_bonus`（invite bonus） / `generation`・`morphing_video`（消費） / `generation_refund`（返却）。
Stripe 由来の付与はすべて `idempotency_key='stripe:<event_id>'`、返却は `'refund:<ledger_id>'` で二重処理を防止。

## 6. テスト手順（Preview / test mode — 依頼書§12対応）

1. migration 6 適用 → Stripe products/prices 作成 → Vercel env 設定 → 再デプロイ
2. `?beta_gate=on` でログイン → Account →「プランを変更」
3. **Trial** → +10 tokens（ledger `trial_grant`）
4. **Visual Simulation 作成** → −2 tokens（ledger `generation`、パネルに「作成：2 tokens」表示）
5. **Morphing Video 書き出し** → −2 tokens（ledger `morphing_video`、保存ボタン下に表示）
6. 生成失敗（エンドポイント一時停止等）→ +2 tokens 返却（ledger `generation_refund`）
7. **Personal** checkout（4242…）→ webhook で +100（`subscription_personal_monthly`）
8. **Clinic** checkout → +500（`subscription_clinic_monthly`）
9. **Add-on Mini/Standard/Plus**（mode:payment）→ 即時 +20/+100/+300（`token_addon_*`）
10. billing_events に全 Stripe event、/admin Billing に plan・status・Add-on購入履歴が反映
11. Customer Portal → 解約予約 → `cancel_at_period_end` 反映、失敗カード `4000 0000 0000 0341` → `past_due`

## 7. 本番反映前に別途整備（ユーザー側タスク）

特商法表記 / 利用規約 / プライバシーポリシー / キャンセル・返金方針 / SMS provider / Leaked Password Protection。
本番課金開始まで `sk_live` は設定しない。Preview の `/api/*` に Deployment Protection がかかる場合は Protection Bypass for Automation を設定（Stripe webhook が 401 になるため）。
