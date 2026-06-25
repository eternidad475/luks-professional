# Google ログイン設定手順（CASEFLOW STUDIO™）

Supabase の Google OAuth を有効化する手順です。所要 15〜20分・無料。

重要な値（コピーして使います）:

| 項目 | 値 |
|------|-----|
| Supabase コールバックURL | `https://nuolihmfdjzofporhwkp.supabase.co/auth/v1/callback` |
| アプリURL | `https://caseflow-studio.vercel.app` |

---

## STEP 1 — Google Cloud でプロジェクト作成

1. https://console.cloud.google.com/ を開く（Googleアカウントでログイン）
2. 画面上部のプロジェクト選択 → 「新しいプロジェクト」→ 名前を `caseflow-studio` などにして「作成」
3. 作成したプロジェクトが選択されていることを確認

## STEP 2 — OAuth 同意画面（consent screen）

1. 左メニュー → 「APIとサービス」→「OAuth 同意画面」
2. User Type は **外部（External）** を選択 →「作成」
3. 入力:
   - アプリ名: `CASEFLOW STUDIO`
   - ユーザーサポートメール: 自分のメール
   - デベロッパーの連絡先メール: 自分のメール
4. 「保存して次へ」。スコープ画面はそのまま「保存して次へ」（email / profile / openid は自動で付きます）
5. テストユーザー画面で、まず自分のメールを「テストユーザー」に追加 →「保存して次へ」
   - ※「公開（Publish）」にすると誰でもログイン可。最初はテストでもOK。

## STEP 3 — OAuth クライアントID を作成

1. 左メニュー →「APIとサービス」→「認証情報（Credentials）」
2. 上部「＋認証情報を作成」→「OAuth クライアント ID」
3. アプリケーションの種類: **ウェブアプリケーション**
4. 名前: `caseflow-web` など
5. **承認済みの JavaScript 生成元** に追加:
   - `https://caseflow-studio.vercel.app`
   - `https://nuolihmfdjzofporhwkp.supabase.co`
6. **承認済みのリダイレクト URI** に追加:
   - `https://nuolihmfdjzofporhwkp.supabase.co/auth/v1/callback`
7. 「作成」→ 表示される **クライアントID** と **クライアントシークレット** を控える

## STEP 4 — Supabase に貼る

1. https://supabase.com/dashboard → プロジェクト caseflow-studio
2. 左メニュー → Authentication → **Providers** → **Google**
3. 「Enable Sign in with Google」をON
4. **Client ID** と **Client Secret** を貼り付け → **Save**

## STEP 5 — URL設定（OAuth/メール認証の戻り先）

1. Authentication → **URL Configuration**
2. **Site URL**: `https://caseflow-studio.vercel.app`
3. **Redirect URLs** に追加: `https://caseflow-studio.vercel.app/**`
4. Save

## STEP 6 — 動作確認

1. `https://caseflow-studio.vercel.app` を開く
2. ログイン画面の「Googleで続ける」→ Google の同意画面 → アプリに戻る
3. 右上に 🪙 10 が表示されれば成功（新規ユーザーに無料トークン10付与）

---

### うまくいかない時

- 「redirect_uri_mismatch」→ STEP 3-6 のリダイレクトURI（`.../auth/v1/callback`）のスペル/末尾を確認
- 戻ってこない／白画面 → STEP 5 の Site URL・Redirect URLs を確認
- 「このアプリは確認されていません」→ テストユーザーに自分を追加（STEP 2-5）、または同意画面を「公開」に
