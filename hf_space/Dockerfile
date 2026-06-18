# Smile Morph Studio — Hugging Face Spaces (Docker, 無料CPU)
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=7860

# 日本語ラベル焼き込み用フォント（IPAGothic）。imageio-ffmpeg は ffmpeg を同梱するため apt 不要。
RUN apt-get update && apt-get install -y --no-install-recommends \
        fonts-ipafont-gothic fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# HF Spaces はコンテナを uid 1000 で実行するため、専用ユーザーを作成して権限を合わせる
RUN useradd -m -u 1000 user
WORKDIR /app

COPY --chown=user requirements.txt .
RUN pip install -r requirements.txt

COPY --chown=user . .
RUN mkdir -p outputs && chown -R user:user /app

USER user
EXPOSE 7860

# gunicorn で Flask アプリ(app.py の app)を 7860 で起動。動画生成に時間がかかるため timeout を長めに。
CMD ["gunicorn", "-b", "0.0.0.0:7860", "-w", "1", "--threads", "4", "-t", "300", "app:app"]
