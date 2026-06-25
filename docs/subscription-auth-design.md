# CASEFLOW STUDIO™ — ユーザー認証 & サブスクリプション 設計書

> 本書は、現在「単一HTMLファイル（フロントエンドのみ）」で動作している CASEFLOW STUDIO に、
> **ユーザーログイン**と **Stripe によるサブスクリプション課金**を追加するための設計ドキュメントです。
> 公開後に運用設定（プラン登録など）を行う前提で、構成・フロー・データモデル・手順・費用・法務観点までを整理します。
>
> ステータス：**設計（実装前）** ／ 推奨スタック：**Supabase（認証・DB）＋ Stripe（課金）＋ Vercel（ホスティング/サーバーレス）**

---

## 1. 目的とゴール

- **ログイン**：歯科医院・歯科医師がアカウントでログインして利用できる。
- **サブスクリプション**：有料プラン契約者だけがアプリ機能（AI生成など）を利用できる。
- **公開後の運用**：プランの追加・価格変更・解約対応を、コード変更なしに Stripe ダッシュボードから行える。
- **安全性**：Stripe シークレットキーや課金ロジックをフロントに置かず、改ざん・不正利用を防ぐ。

### 非ゴール（今回のスコープ外）
- 院内マルチユーザー権限（管理者/スタッフ）まで作り込む（将来拡張として記載のみ）。
- 患者データのクラウド永続保存（現状どおり端末ローカル localStorage 運用を維持）。

---

## 2. なぜバックエンドが必要か（重要）

現状の単一HTMLは安全に課金を扱えません。Stripe サブスクには最低限、以下のサーバー側処理が必須です。

| 処理 | 理由 | 置き場所 |
|---|---|---|
| Checkout セッション作成 | Stripe **秘密鍵**を使う。フロントに置くと漏洩＝不正利用 | サーバーレス関数 |
| Webhook 受信 | 課金成功・更新・解約・失敗を**正となるデータ**として受け取る | サーバーレス関数 |
| 権限（エンタイトルメント）判定 | 「契約中か？」をクライアント任せにすると改ざん可能 | サーバー/DB |

→ アプリ本体（生成ロジック・UI）はそのまま流用し、**薄いバックエンドを足して“ゲート”を被せる**構成にします。

---

## 3. 全体アーキテクチャ

```
┌──────────────────────────────┐
│  ブラウザ（CASEFLOW STUDIO フロント）        │
│  - ログインUI（Supabase JS）                 │
│  - ログイン後、JWT を保持                    │
│  - 「契約状態」を取得してアプリをゲート       │
└───────────┬───────────────┘
            │ HTTPS（JWT付き）
            ▼
┌──────────────────────────────┐
│  サーバーレス関数（Vercel / Supabase Edge）   │
│  1) POST /api/checkout  → Stripe Checkout作成 │
│  2) POST /api/portal    → 顧客ポータル発行     │
│  3) POST /api/webhook   → Stripeイベント受信   │
│  4) GET  /api/me        → 契約状態を返す       │
└──────┬───────────────┬──────┘
       │ 秘密鍵          │ 署名検証
       ▼                 ▼
┌──────────────┐   ┌────────────────┐
│   Stripe       │   │  Supabase（Postgres）  │
│ - 商品/価格     │   │ - auth.users           │
│ - Checkout      │   │ - profiles             │
│ - Billing/解約  │   │ - subscriptions        │
│ - Webhook送信   │──▶│ （Webhookで同期）       │
└──────────────┘   └────────────────┘
```

- **認証**：Supabase Auth（メール＋パスワード / Google OAuth）。
- **課金**：Stripe Checkout（申込）＋ Customer Portal（解約・カード変更）＋ Webhook（状態同期）。
- **ホスティング**：静的フロント＋`/api/*` サーバーレス関数を一体で Vercel にデプロイ（Supabase Edge Functions でも可）。

---

## 4. データモデル（Supabase / Postgres）

```sql
-- Supabase Auth が自動作成する auth.users に紐づくプロフィール
create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  clinic_name text,
  stripe_customer_id text unique,
  created_at timestamptz default now()
);

-- Stripe のサブスク状態を Webhook で同期（“正”は常に Stripe）
create table public.subscriptions (
  id text primary key,                 -- Stripe subscription id (sub_...)
  user_id uuid references auth.users(id) on delete cascade,
  status text not null,                -- active / trialing / past_due / canceled ...
  price_id text,                       -- 契約中の price
  current_period_end timestamptz,
  cancel_at_period_end boolean default false,
  updated_at timestamptz default now()
);

-- RLS（行レベルセキュリティ）：本人の行だけ参照可。書き込みはサーバー（service role）のみ。
alter table public.profiles      enable row level security;
alter table public.subscriptions enable row level security;
create policy "own profile"      on public.profiles      for select using (auth.uid() = id);
create policy "own subscription" on public.subscriptions for select using (auth.uid() = user_id);
```

> **エンタイトルメント判定**：`status in ('active','trialing')` かつ `current_period_end > now()` を「利用可」とする。

---

## 5. 認証フロー

1. フロントで Supabase JS を読み込み、ログイン/サインアップUIを表示。
2. メール＋パスワード or Google でログイン → Supabase が **JWT** を発行。
3. 以降のAPI呼び出しは `Authorization: Bearer <JWT>` を付与。
4. サーバー側は JWT を検証して `user_id` を確定（Supabase の `auth.getUser()`）。

---

## 6. サブスクリプション・フロー

### 6.1 申し込み（Checkout）
1. ログイン済みユーザーが「プランに登録」をクリック。
2. フロント → `POST /api/checkout`（JWT付き、希望 `price_id`）。
3. サーバー：Stripe 顧客を取得/作成（`stripe_customer_id` を profiles に保存）→ **Checkout セッション**を作成し URL を返す。
4. ユーザーは Stripe のホスト画面で決済 → 成功で `success_url` に戻る。

### 6.2 状態同期（Webhook：ここが“正”）
- Stripe → `POST /api/webhook` に以下を送信。**必ず署名検証**（`stripe.webhooks.constructEvent`）。
  - `checkout.session.completed`
  - `customer.subscription.created / updated / deleted`
  - `invoice.payment_failed`
- サーバーは受信内容で `subscriptions` テーブルを upsert。

### 6.3 利用ゲート
1. アプリ起動時にフロント → `GET /api/me`。
2. サーバーは DB の契約状態を返す（`{ active: true/false, plan, period_end }`）。
3. `active=false` の場合は生成機能をロックし「プラン登録」へ誘導。
   - ※ クライアント側のフラグは“表示制御”のみ。**実生成API側でも契約チェック**を行い、迂回を防ぐ。

### 6.4 解約・カード変更（Customer Portal）
- `POST /api/portal` → Stripe Customer Portal の URL を返す。ユーザーは自分で解約・カード変更・領収書取得が可能（運用負荷ゼロ）。

---

## 7. APIエンドポイント仕様（サーバーレス）

| メソッド/パス | 認証 | 役割 |
|---|---|---|
| `POST /api/checkout` | JWT必須 | Checkout セッションURLを返す |
| `POST /api/portal` | JWT必須 | Customer Portal URLを返す |
| `GET /api/me` | JWT必須 | 契約状態 `{active, plan, period_end}` を返す |
| `POST /api/webhook` | Stripe署名 | Stripeイベントを受けDB同期（公開・無認証だが署名検証必須） |

**必要な環境変数（サーバー側のみ・絶対にフロントへ出さない）**
```
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...      # サーバー専用
# フロント用（公開可）
NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY
STRIPE_PUBLISHABLE_KEY=pk_live_... # 公開可
```

---

## 8. プラン設計（たたき台 ／ 公開後に Stripe で登録）

| プラン | 価格（例・税別） | 内容 | Stripe |
|---|---|---|---|
| Free Trial | 0円（14日） | 全機能・回数制限あり | `trial_period_days` |
| Solo（月額） | 例 ¥9,800/月 | 1ユーザー・標準利用 | recurring/month |
| Solo（年額） | 例 ¥98,000/年 | 2ヶ月分お得 | recurring/year |
| Clinic | 例 ¥29,800/月 | 複数ユーザー（将来拡張） | recurring/month |

> 価格は**仮**です。原価（AI生成コスト）と提供価値から確定してください。
> 価格・プランは Stripe ダッシュボードで作成すれば、コード変更なしに `price_id` を差し替え可能。

---

## 9. セキュリティ要点

- Stripe **秘密鍵 / service role キーはサーバー専用**。フロントJS・リポジトリに含めない（環境変数管理）。
- Webhook は **署名検証必須**（偽イベントによる不正契約付与を防止）。
- 契約状態の**最終判定はサーバー＋DB**で行う。クライアントのフラグは信用しない。
- Supabase は **RLS 有効**。書き込みは service role（サーバー）のみ。
- HTTPS 必須、CORS は自ドメインに限定。

---

## 10. 公開後の運用設定手順（チェックリスト）

1. **Stripe アカウント開設** → 本人確認 → 入金口座登録。
2. ダッシュボードで **商品（Product）と価格（Price）** を作成（§8）。
3. **Customer Portal** を有効化（解約・領収書を自動化）。
4. **Webhook エンドポイント**を登録（`/api/webhook`）→ `whsec_...` を環境変数へ。
5. Supabase プロジェクト作成 → §4 のテーブル/RLS を適用 → 認証プロバイダ（メール/Google）設定。
6. Vercel に本リポジトリをデプロイ → 環境変数を設定。
7. **テストモード**で一連（登録→決済→Webhook→ゲート解除→解約）を検証。
8. 本番キーへ切替え → 少額の実決済で最終確認。

---

## 11. 開発マイルストーン（実装フェーズ・お任せ部分）

1. **M1 認証**：Supabase 導入、ログイン/サインアップUI、ログイン後ゲート（モック契約）。
2. **M2 課金**：`/api/checkout`・`/api/portal`・`/api/webhook`・`/api/me`、DB同期。
3. **M3 ゲート統合**：生成APIに契約チェックを組み込み、未契約はロック。
4. **M4 運用**：トライアル、解約導線、領収書、エラー/失敗時のリカバリ、QA。
5. **M5 公開**：本番キー、監視（Stripeダッシュボード/ログ）、ドキュメント整備。

---

## 12. 費用感（目安）

| 項目 | 初期 | ランニング |
|---|---|---|
| Supabase | 0円 | 無料枠 → 規模に応じ有料（$25/月〜） |
| Vercel | 0円 | 無料枠 → Pro（$20/月〜） |
| Stripe | 0円 | 決済額の手数料（国内カード概ね 3.6% 前後） |
| AI生成バックエンド | 既存 | 生成回数に比例（原価管理が要） |

> いずれも**初期費用ゼロ・無料枠から開始可能**。AI生成の従量コストが価格設計の肝。

---

## 13. 法務・コンプライアンス（要確認）

- **特定商取引法**に基づく表記（提供事業者・料金・解約条件など）を公開ページに掲載。
- **利用規約 / プライバシーポリシー / 返金・解約ポリシー**を整備。
- サブスクの**自動更新の明示**と解約手段の提供（Customer Portal で担保）。
- 医療広告ガイドライン：生成画像は引き続き「**参考イメージ・非診断**」を明示（アプリ/LP既存方針を踏襲）。
- 患者写真の取り扱い（同意・保存方針）。現状ローカル保存方針を規約に明記。

---

## 14. 将来拡張

- 院内マルチユーザー（管理者/スタッフ権限、座席課金）。
- 使用量メータリング（生成回数に応じた従量課金）。
- 請求書払い（Invoicing）対応の法人プラン。

---

### 付記
本設計は推奨スタック（Supabase＋Stripe＋Vercel）前提です。既存のAI生成バックエンド（val.run等）はそのまま併存可能で、その呼び出し前に「契約チェック」を挟む形で統合します。実装フェーズはご要望どおり当方にお任せいただく前提で進めます。
