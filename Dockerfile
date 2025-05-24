FROM python:3.11-slim-bookworm

# ffmpeg をインストール
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# 作業ディレクトリ（venvなどを置く場所）を /opt に設定
WORKDIR /opt

# requirements.txt をコピー
COPY requirements.txt .

# 仮想環境を /opt/venv に作成し、依存をインストール
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# 環境変数で Python 実行環境を指定（任意）
ENV PATH="/opt/venv/bin:$PATH"

# /app はマウント前提。存在しなくてもエラーにならないようにする
WORKDIR /app

# デフォルトで /app/main.py を実行
CMD ["python", "main.py"]
