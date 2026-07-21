FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

# 日本語フォント
RUN apt-get update && apt-get install -y \
    fonts-ipafont-gothic \
    fonts-ipafont-mincho \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501

CMD ["python", "-m", "streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
