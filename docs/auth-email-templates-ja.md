# Supabase 認証メール日本語化（confirmation / recovery）

> 対象プロジェクト: `caseflow-studio`（nuolihmfdjzofporhwkp）
> これは **DB migration ではなく Auth 設定変更** です。Supabase Dashboard
> （または Management API の auth config PATCH）で適用します。

## 適用手順（Dashboard）

1. Supabase Dashboard → 対象プロジェクト → **Authentication → Email Templates**
2. 各テンプレートの Subject / Body を下記に置き換えて **Save**
3. 変更は即時反映（再デプロイ不要）。テスト用アドレスでサインアップ／
   パスワード再設定を実行して受信文面を確認する

## 1) Confirm signup（確認メール）

**Subject:**

```
CaseFlow Studio メールアドレス確認のお願い
```

**Body (HTML):**

```html
<h2>CaseFlow Studio メールアドレス確認</h2>
<p>CaseFlow Studio へのご登録ありがとうございます。</p>
<p>以下のボタンを押して、メールアドレスの確認を完了してください。</p>
<p><a href="{{ .ConfirmationURL }}">メールアドレスを確認する</a></p>
<p>このメールに心当たりがない場合は、破棄してください。</p>
<p>CaseFlow Studio</p>
```

## 2) Reset password（パスワード再設定）

**Subject:**

```
CaseFlow Studio パスワード再設定
```

**Body (HTML):**

```html
<h2>パスワード再設定</h2>
<p>CaseFlow Studio のパスワード再設定リクエストを受け付けました。</p>
<p>以下のボタンから新しいパスワードを設定してください。</p>
<p><a href="{{ .ConfirmationURL }}">パスワードを再設定する</a></p>
<p>この操作に心当たりがない場合は、このメールを破棄してください。</p>
<p>CaseFlow Studio</p>
```

## 3) あわせて日本語化を推奨（同画面にあるその他テンプレート）

| テンプレート | Subject 案 |
|---|---|
| Magic Link | CaseFlow Studio ログインリンク |
| Change Email Address | CaseFlow Studio メールアドレス変更の確認 |
| Invite user | CaseFlow Studio への招待 |

（本文は上記と同トーンで `{{ .ConfirmationURL }}` を必ず含めること）

## 4) 注意事項

- `{{ .ConfirmationURL }}` などのテンプレート変数は **削除・改変しない**
- Site URL / Redirect URLs（Authentication → URL Configuration）が本番URLに
  なっていることを確認（確認リンクの遷移先に影響）
- 現在アプリはパスワード再設定に `?beta_gate=on` 付き redirectTo を使用して
  いるため、Redirect allow list にも本番URLが含まれている必要がある

## 5) 将来: custom SMTP（送信元を CaseFlow Studio 名義へ）

現状は Supabase 既定の送信（`noreply@mail.app.supabase.io`）。一般ユーザー
の不安軽減には custom SMTP への切替が有効:

1. 送信ドメインを用意（例: `mail.caseflow.studio` / Narrative Cherish 名義）
2. SMTP プロバイダ（Resend / SendGrid / Amazon SES 等）でドメイン認証
   （SPF / DKIM / DMARC を設定 — 医療系ユーザー向けに到達率とドメイン信頼が重要）
3. Dashboard → **Project Settings → Auth → SMTP Settings** で
   Host / Port / User / Pass / Sender email / Sender name を設定
   - Sender name: `CaseFlow Studio`
   - Sender email: `noreply@<認証済みドメイン>`
4. 切替後、confirmation / recovery の受信・迷惑メール判定を再テスト

> 補足: Supabase 既定送信はレート制限が厳しい（時間あたり数通）ため、
> ベータ招待を本格展開する前に custom SMTP へ移行することを推奨。
