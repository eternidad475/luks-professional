# Phase 2 — Stripe 連携セットアップ手順（test mode）

> 本番課金は未開始。すべて **Stripe test mode** 前提。
> Secret key / Webhook secret / service_role key は Vercel 環境変数のみ（フロント・リポジトリに置かない）。

## 1. Stripe Dashboard で作成するもの（test mode）

### Products / Prices

| Product | Price | 金額 | 種別 | env 変数名 |
|---|---|---|---|---|
| CaseFlow Sketch | Sketch Monthly | 1,500 JPY | recurring / month | `STRIPE_PRICE_SKETCH_MONTHLY` |
| CaseFlow Sketch | Sketch Annual | 15,300 JPY | recurring / year | `STRIPE_PRICE_SKETCH_ANNUAL` |
| CaseFlow Studio | Studio Monthly | 3,000 JPY | recurring / month | `STRIPE_PRICE_STUDIO_MONTHLY` |
| CaseFlow Studio | Studio Annual | 30,600 JPY | recurring / year | `STRIPE_PRICE_STUDIO_ANNUAL` |

- Developer プランは Stripe に作らない（role による課金免除で対応）
- Trial は Stripe を使わない（`claim_trial_tokens()` RPC・支払い方法不要）
- 年額 price を作らなければ、Pricing UI の年額ボタンは「準備中」トーストになる（env 未設定→ `price_not_configured`）

### Customer Portal
Settings → Billing → Customer portal を有効化（解約・カード変更・領収書）。

### Webhook
Developers → Webhooks → Add endpoint:

- **URL**: `https://<デプロイURL>/api/stripe/webhook`
  - Production: `https://caseflow-studio.vercel.app/api/stripe/webhook`
  - Preview 検証時は Preview URL でもよい（そのデプロイに対して署名secretを発行）
- **イベント**: `checkout.session.completed` / `customer.subscription.created` / `customer.subscription.updated` / `customer.subscription.deleted` / `invoice.payment_succeeded` / `invoice.payment_failed`
- 発行された `whsec_...` を `STRIPE_WEBHOOK_SECRET` に設定

## 2. Vercel 環境変数

| 変数 | 用途 | 公開可否 |
|---|---|---|
| `STRIPE_SECRET_KEY` | `sk_test_...` | **server only** |
| `STRIPE_WEBHOOK_SECRET` | `whsec_...` | **server only** |
| `SUPABASE_URL` | `https://nuolihmfdjzofporhwkp.supabase.co` | server（値自体は公開情報） |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service_role | **server only・絶対にフロント禁止** |
| `NEXT_PUBLIC_APP_URL` | 例 `https://caseflow-studio.vercel.app` | 公開可（successリダイレクト先） |
| `STRIPE_PRICE_SKETCH_MONTHLY` ほか価格ID 4種 | `price_...` | server only |
| `STRIPE_PUBLISHABLE_KEY` / `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` | 現状 Hosted Checkout のみのため未使用（Embedded 化時に使用） | 公開可 |

## 3. Supabase migration

`supabase/migrations/20260703000005_billing_stripe.sql` を適用:
- `profiles.trial_tokens_granted`
- `billing_customers` / `billing_subscriptions` / `billing_events`（RLS: own-read + admin-read、書き込みは service_role のみ）
- `claim_trial_tokens()`（10トークン・1回のみ）
- `admin_list_billing()`（/admin Billing セクション用）

## 4. トークン付与ルール（Webhook 実装済み）

| トリガー | 付与 | ledger reason |
|---|---|---|
| Trial（RPC） | +10（1回のみ） | `trial_grant` |
| invoice.payment_succeeded（月額） | Sketch +100 / Studio +500 | `subscription_monthly_grant` |
| invoice.payment_succeeded（年額） | Sketch +1200 / Studio +6000 一括 | `subscription_annual_grant` |
| 招待承認 | +100 / +100 | `invitee_initial_beta_grant` / `inviter_referral_beta_bonus` |
| 管理者手動 | 任意 | `admin_grant` |

- 冪等性: `billing_events.stripe_event_id` unique + `token_ledger.idempotency_key`（`stripe:<event_id>`）の二段構え
- **年額の注意**: 現状は一括付与。返金・途中解約時の残トークン扱いが複雑になるため、月次ドリップ（cron）への移行を Phase 2.1 で検討。それまで年額 price を作らず月額のみで運用するのも可
- 解約: 既存トークンは没収しない。invoice が止まることで次回付与が自然停止
- past_due: 利用制限はかけず警告表示のみ（canUseApp は past_due も通す）

## 5. 消費ルール（実装済み）

- Visual Simulation 生成: 1 token（`generateViaAI` / `generateRefinedViaAI` — 生成前消費）
- Morphing Video 生成: 1 token（`setExportBlob` ラップ — 書き出し成功時消費。残0でも完成動画は失わせず、トークン切れモーダル表示）
- ローカル編集・閲覧・保存・比較スライダー: 消費なし
- 将来: 高コスト処理（AI中割り等）は reason/金額を変えるだけで 2〜3 tokens に変更可能

## 6. テスト手順（Preview / test mode）

1. migration 5 適用 → Vercel に環境変数設定 → 再デプロイ
2. Preview URL + `?beta_gate=on` でログイン
3. 下部ナビ中央 **Account** → 「プランを変更」→ Pricing 表示
4. Trial「無料で試す」→ +10 tokens / ledger `trial_grant` を確認
5. Sketch 月額 →「このプランにする」→ Stripe Checkout（test）
6. テストカード `4242 4242 4242 4242` / 任意の未来日付 / 任意CVC で支払い
7. `?checkout=success` で復帰 → 数十秒後 Account メニューに `現在のプラン：Sketch`・tokens +100
8. Supabase で確認: `billing_customers` / `billing_subscriptions(status=active)` / `billing_events` / `token_ledger(subscription_monthly_grant)`
9. 「支払い管理」→ Customer Portal → 解約予約 → `cancel_at_period_end=true` が menu と /admin Billing に反映
10. 失敗カード `4000 0000 0000 0341` で更新失敗 → `past_due` 反映を確認
11. /admin → Billing セクションで一覧確認

## 7. 本番反映前の注意

- 本番課金開始まで `sk_live` は設定しない（test キーのまま）
- Webhook は **デプロイURLごとに** endpoint + secret が必要（Preview で検証した secret は Production と別）
- `CF_BETA_GATE_DEFAULT` はまだ false（Phase 1e スイッチと独立）
- 特商法表記・利用規約の課金条項を本番課金開始前に整備
- Vercel の Deployment Protection が Preview の `/api/*` を保護している場合、Stripe からの Webhook が 401 になる → Preview 検証時は Protection Bypass for Automation を設定するか、Production の Webhook のみ使う
