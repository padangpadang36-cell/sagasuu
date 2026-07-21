FROM python:3.11-slim

# システムライブラリ + 日本語フォント（TTF形式）
RUN apt-get update && apt-get install -y \
    wget curl gnupg ca-certificates \
    fonts-noto-cjk \
    fonts-ipafont-gothic \
    fonts-ipafont-mincho \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright のブラウザ（Chromium）をインストール
RUN playwright install chromium
RUN playwright install-deps chromium

COPY . .

EXPOSE 8501

CMD ["python", "-m", "streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
