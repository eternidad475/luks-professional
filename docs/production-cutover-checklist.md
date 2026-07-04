# caseflow-studio.com 本番接続チェックリスト（2026-07-03 時点）

## 完了済み
- [x] Production = `b8b7aa9`（migration 11 まで反映）— `dpl_8UqsXXjoHgPbfqJZcVhznB9CApQm`
- [x] caseflow-studio.vercel.app が新ビルドを配信（Wallet新UI・10/5・self_invite 文言を実測確認）
- [x] Resend DNS 3件（DKIM / MX / SPF @ auth サブドメイン）公開済み・実測確認
- [x] DB migrations 7〜12 適用済み

### DB migration ログ
| repo file | 本番 schema_migrations version | name | 適用日 | 備考 |
|---|---|---|---|---|
| `20260710000012_lock_down_profiles_column_updates.sql` | `20260703105817` | `lock_down_profiles_column_updates` | 2026-07-10 | **セキュリティ修正**: profiles の列 UPDATE 権限を最小化。role/tokens_remaining/beta_access 等の自己書き換え（権限昇格・トークン水増し）を遮断。authenticated の UPDATE は display_name/clinic_name/professional_type/professional_confirmed のみ。本番で BLOCKED(42501) を実測確認済み。|
| `20260711000013_clamp_accept_invite_code_role_escalation.sql` | `20260703113150` | `clamp_accept_invite_code_role_escalation` | 2026-07-11 | **セキュリティ hardening**: 公開RPC accept_invite_code() が付与できる role を非特権職種（dentist/staff/viewer/billing_manager/patient_link_viewer）に限定。developer/admin/co_developer/owner はコード redeem 経由で付与不可（admin_set_user_role 経由のみ）。潜在的権限昇格経路を恒久封鎖。|
| `20260712000014_general_user_invite_creation.sql` | `20260703144308` | `general_user_invite_creation` | 2026-07-12 | **機能+権限**: 一般ユーザー用の招待発行 RPC `create_user_invite()`（role=dentist固定・invitee 10・inviter 0・有効未使用5件上限・invited_by=auth.uid）。invite_codes に own-read RLS 追加（自分の発行コードのみ閲覧）。一般ユーザーは developer/admin コードを発行不可（DB側で固定）。|
| `20260713000015_lock_down_workspaces_column_updates.sql` | `20260703145750` | `lock_down_workspaces_column_updates` | 2026-07-13 | **セキュリティ修正**: workspaces の type/plan/tokens_remaining/owner_user_id/deleted_at を authenticated から直接 UPDATE 不可に。owner の直接編集は name/clinic_phone/clinic_address のみ。clinic wallet 自己増加・type/plan 自己変更を遮断。本番で DENIED(42501) 実測確認。|
| `20260714000016_admin_revenue_summary.sql` | 2026-07-14 適用 | `admin_revenue_summary` | 2026-07-14 | **管理機能**: admin dashboard の REVENUE カード用 RPC。SECURITY DEFINER + `is_admin()` gate（role developer/admin）。今月の売上/Add-on/返金を `billing_events.payload`（webhook保存の実額）から、MRR を active `billing_subscriptions` から集計し jsonb を返す。execute は authenticated のみ（anon/public revoke）。本番で admin→集計 / 非admin→42501 / anon→権限なし を実測確認。Stripe secret 非関与（DB内集計のみ）。|

## Admin Revenue カード（Stripe 売上概要）— 2026-07-14 追加

**場所**: `/admin`（`caseflow_admin.html`）Overview 直下の `REVENUE` カード。管理者（role developer/admin）のみ。

**表示項目（すべて JPY・参考値/estimate）**: 今月売上 / 決済件数 / MRR / Add-on売上 / 返金 / Net estimate（Stripe手数料 ~3.6% 控除後の概算）/ 最終更新。状態: loading / empty（まだ売上データがありません）/ error（再読み込み可）。

**集計方法（DB集計・Stripe API非使用）**:
- RPC `admin_revenue_summary()`（SECURITY DEFINER, `is_admin()` gate）が全集計を DB 内で実行。フロントは Supabase `sb.rpc('admin_revenue_summary')` を呼ぶだけで、**Stripe secret key はフロントにもRPCにも一切登場しない**。
- 今月売上/Add-on/返金 = `billing_events.payload` に webhook が保存する実額（`kind` in subscription/addon/refund, `amount` = JPY）を当月分で合計。
- MRR = active/trialing の `billing_subscriptions` からプラン価格（Sketch=personal 1500 / Clinic Studio=clinic 5000）で算出。
- 決済件数 = 当月の subscription+addon イベント件数。Net estimate = (gross − refunds) × (1 − 0.036) を四捨五入。

**どの値が概算か**: Net estimate は Stripe手数料控除後の**概算**（会計確定額ではない）。MRR はプラン定価ベースの推定（実際の割引/日割りは未考慮）。すべて運営確認用の参考値であり、正式な会計・税務処理は Stripe ダッシュボード/会計資料で確認する旨をカード内に明記。

**admin-only 制御**: UI は gate/denied/dash で管理者のみ dash 表示。RPC 側でも `is_admin()` 不成立なら 42501 を raise（一般ユーザーが直接叩いても DENIED）。execute grant は authenticated のみ（anon 不可）。

**Free/Trial・表記ポリシー**: Free/Trial は売上に非計上（webhook が amount を記録するのは実決済イベントのみ）。Invite Beta/招待ベータ 表記なし。Developer は売上プラン扱いしない。Plans は Free/Sketch/Clinic Studio 整理を維持。

**将来必要な改善点（推奨）**:
1. **webhook のイベント購読に `charge.refunded` を追加**（Stripe Dashboard → Webhooks → endpoint）。未追加だと Refunds は常に ¥0。
2. 非JPY通貨を扱う場合、`amount` は最小単位（例: USDはセント）になるため RPC 側で通貨別に /100 等の正規化が必要（現状は JPY 前提）。
3. Add-on 価格は現在 Stripe 実額（`amount_total`）を webhook が保存する方式のため DB で正確。将来 add-on の price ID→金額を1箇所に集約すると保守性向上。
4. `billing_events.payload` は今回の webhook 改修以降のイベントのみ金額を持つ（過去イベントは最小payloadのため集計対象外）。過去分が必要なら Stripe から一括バックフィルするバッチを別途用意。
5. より厳密な会計値が必要になった段階で、admin 専用サーバー側（Edge Function / API route）から Stripe Reporting API を呼ぶ拡張に移行可能（secret はサーバー側のみ）。

> リポジトリの migration ファイル名は連番ベースの合成タイムスタンプ（`2026070X00000N`）で、
> 本番 `supabase_migrations.schema_migrations` の実適用タイムスタンプとは一致しない運用（name で対応）。
> migration 12 の実適用版は `20260703105817 lock_down_profiles_column_updates`。

## 1. Vercel ドメイン追加（Dashboard 操作 — MCP からは不可）
Vercel → caseflow-studio → Settings → **Domains** で追加:
1. `caseflow-studio.com`（Production）
2. `www.caseflow-studio.com` → 追加時に **Redirect to caseflow-studio.com (308)** を選択

## 2. お名前.com（dnsv.jp）に追加する DNS レコード
> **Vercel 画面に表示される値を必ず優先**（以下は標準値）

| TYPE | HOST | VALUE |
|---|---|---|
| A | （空 = apex） | `76.76.21.21` |
| CNAME | `www` | `cname.vercel-dns.com` |

**触ってはいけない既存レコード（メール用・削除/上書き禁止）:**
- TXT `resend._domainkey.auth`（DKIM）
- MX `send.auth` → feedback-smtp.ap-northeast-1.amazonses.com (10)
- TXT `send.auth`（SPF）

競合なし: Vercel 用は apex と `www`、Resend 用は `auth` サブドメイン配下で名前空間が分離している。
推奨追加: TXT `_dmarc.auth` = `v=DMARC1; p=none;`（DMARC未設定のため）

## 3. Supabase Auth URL 設定（Dashboard: Authentication → URL Configuration）
- Site URL: `https://caseflow-studio.com`
- Redirect URLs（**両方残す** — 移行期間中は旧URLを消さない）:
  - `https://caseflow-studio.com/*`
  - `https://caseflow-studio.vercel.app/*`
  - `http://localhost:3000/*`（開発で使用中なら維持）

## 4. Vercel 環境変数（値は書かない・名前のみ）
- [ ] **STRIPE_PRICE_PERSONAL_MONTHLY の値を修正**（現在: 変数名の文字列が値に入っている
      — Runtime Logs に "No such price: 'STRIPE_PRICE_PERSONAL_MONTHLY'" が記録されている。
      正しい値は Stripe の price ID `price_1Tof4WPShHRTbktqwBxEUBqR`）
- [ ] 他4つの STRIPE_PRICE_* も値が `price_...` 形式か確認
      （CLINIC_MONTHLY / ADDON_MINI / ADDON_STANDARD / ADDON_PLUS）
- [x] SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY（10:05の欠落ログ後に設定済み — 10:52以降のログで hasSupabaseUrl 等の欠落エラーは消えている）
- [ ] `NEXT_PUBLIC_APP_URL=https://caseflow-studio.com` を Production に設定
      （未設定だと checkout の success/cancel URL が受信 Host 依存になる。実害はないが固定推奨）
- 変更後は **Redeploy が必要**（env は build/runtime に焼き込まれるため）

## 5. Stripe Webhook 移行（旧を消さず追加 → 検証 → 整理）
1. Stripe Dashboard → Developers → Webhooks → **Add endpoint**:
   `https://caseflow-studio.com/api/stripe/webhook`（旧 vercel.app 側は残す）
2. イベント: 旧エンドポイントと同一（checkout.session.completed / invoice.paid 系 / customer.subscription.*）
3. 新エンドポイントの **Signing secret を Vercel の STRIPE_WEBHOOK_SECRET に反映**
   ⚠ 注意: webhook.js は単一の STRIPE_WEBHOOK_SECRET しか読まないため、新旧2エンドポイント併存中は
   **secret が一致する側しか検証を通らない**。手順: 新endpoint作成 → secret差替え&redeploy →
   テスト決済で新endpointの受信確認 → 旧endpointを無効化（削除は数日後）
4. 検証: テスト購入 → billing_events に stripe_event_id 記録 / token_ledger に grant / 残高反映

## 6. 接続後の確認（ドメイン反映後）
- [ ] `https://caseflow-studio.com` が 200 / `https://www.caseflow-studio.com` → 308 → apex
- [ ] 新規登録 → 日本語確認メール（no-reply@auth.caseflow-studio.com）→ リンクが caseflow-studio.com に戻る
- [ ] パスワード再設定 → 同上
- [ ] ログイン → Account Sheet の Wallet 表示（保有トークン主表示・数値切れなし）
- [ ] 招待コード承認（10/5 付与・profiles/workspace 反映）
