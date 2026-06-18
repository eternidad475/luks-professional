---
title: Smile Morph Studio
emoji: 🦷
colorFrom: purple
colorTo: pink
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# Smile Morph Studio — Web App (Hugging Face Spaces)

審美歯科症例ビジュアル制作アプリのプロトタイプ。術前・経過・術後の最大10枚の写真を
読み込み、自然なモーフィング風の **H.264 MP4 動画** を生成して、患者説明・症例提示・
SNS 投稿用のビジュアルを作成します。

> 本アプリは医療診断アプリではありません。治療結果を保証するものではなく、歯科医師に
> よる患者説明・症例提示・SNS 用ビジュアル制作の補助ツールです。AI 仮処理・生成画像には
> "Simulation / Reference Image" を表示します。**動作確認はテスト画像（「サンプルで試す」）で
> 行ってください（患者写真は使用しない前提）。**

## エンドポイント
- `GET /` → `/studio/` にリダイレクト
- `GET /studio/` → HTML UI（PWA。iPhone Safari からそのまま開けます）
- `POST /api/morph_video` → MP4 を生成し `{"ok":true,"video_url":"/outputs/xxxx.mp4"}` を返す
- `GET /outputs/<file>` → 生成された MP4（**一時保存**。1時間で自動削除）

## 構成
- **Flask + Pillow + imageio(ffmpeg)**。動画は `libx264 / yuv420p` で書き出すため
  iPhone Safari でそのまま再生できます。
- Hugging Face Spaces の **Docker SDK**（無料 CPU 環境）で起動します（`app_port: 7860`）。
- 生成動画は `outputs/` に一時保存（コンテナ再起動で消えます）。

## Hugging Face Spaces へのデプロイ
1. https://huggingface.co/new-space で **Docker** を選んで Space を作成。
2. このフォルダ (`hf_space/`) の中身を Space リポジトリ直下に置く（`README.md` の YAML が
   そのまま Space 設定になります）。
   ```
   app.py  Dockerfile  requirements.txt  README.md  studio/  outputs/
   ```
3. push すると自動でビルド・起動します。表示された Space の URL を iPhone Safari で開き、
   `/studio/` にアクセス。

## ローカル確認
```bash
pip install -r requirements.txt
python3 app.py            # http://localhost:8000/studio/
# または Docker:
docker build -t smile-morph . && docker run -p 7860:7860 smile-morph   # http://localhost:7860/studio/
```

## 使い方
1. `/studio/` を開き「サンプルで試す」または写真を追加（最大10枚、ラベル編集可）。
2. 必要なら位置合わせ（正中・スマイル等のガイド）。
3. プレビューでアスペクト比（9:16 / 4:5 / 1:1 / 16:9）・テンプレート・タイトルを選択。
4. 「本物のMP4を書き出し（サーバー）」→ 生成後に「写真に保存 / ファイルに保存 / SNSに共有」。
