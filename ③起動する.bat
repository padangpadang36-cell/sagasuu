@echo off
chcp 65001 > nul
cd /d "%~dp0"

REM ── Streamlit をインストール確認 ─────────────────────────
python -c "import streamlit" > nul 2>&1
if errorlevel 1 (
    echo Streamlit をインストールしています。少々お待ちください...
    python -m pip install streamlit
    echo.
)

REM ── 新しいウィンドウで Web UI を起動（エラーがあっても閉じない）
start "社宅システム Web UI" cmd /k "%~dp0システムファイル\start_webui.bat"

REM ── 3秒待ってからブラウザを開く
ping -n 4 127.0.0.1 > nul
start http://localhost:8501
