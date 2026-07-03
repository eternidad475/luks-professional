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
