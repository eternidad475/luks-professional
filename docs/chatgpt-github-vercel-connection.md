# ChatGPT / GitHub / Vercel 接続メモ

このファイルは、ChatGPT から GitHub リポジトリを編集し、Vercel の自動デプロイへつなげるための接続確認メモです。

## 確認済みの接続状態

- GitHub App installation: enabled for `eternidad475`
- 対象リポジトリ: `eternidad475/luks-professional`
- Vercel チーム: `eternidad475's projects`
- Vercel プロジェクト: `caseflow-studio`
- Vercel プロジェクトID: `prj_jhKAMiCTf8silAMweuAdsF6aScxx`
- 本番ドメイン: `caseflow-studio.vercel.app`

## 編集フロー

1. ChatGPT が GitHub 上の対象ファイルを取得します。
2. 必要な修正内容を確認します。
3. 既存ファイルを更新、または新規ファイルを追加します。
4. GitHub にコミットします。
5. Vercel の GitHub 連携により、自動的にデプロイが走ります。

## 注意事項

- APIキー、トークン、秘密鍵などのシークレット値は、このリポジトリへ直接書き込まないでください。
- 環境変数は Vercel または Supabase など、適切な管理画面で扱ってください。
- 臨床画像や患者情報を含むファイルは、公開リポジトリへ保存しないでください。
- 大きな変更は、必要に応じて専用ブランチまたはプルリクエストで確認してから本番へ反映してください。

## 現在のルーティング

`vercel.json` により、以下のように公開パスが設定されています。

- `/` → `caseflow_studio_v96.html`
- `/app` → `caseflow_studio_v96.html`
- `/landing` → `caseflow_landing.html`
- `/privacy` → `privacy.html`
- `/terms` → `terms.html`
- `/legal` → `legal.html`
