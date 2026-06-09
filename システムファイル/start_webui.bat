@echo off
chcp 65001 > nul
cd /d "%~dp0\.."
set PYTHONIOENCODING=utf-8
echo ============================================================
echo   社宅物件提案書 自動生成システム - Web UI
echo   サーバー起動中... ブラウザで開いてください:
echo   http://localhost:8501
echo.
echo   このウィンドウを閉じるとサーバーが停止します。
echo ============================================================
echo.
python -m streamlit run app.py --server.port 8501 --server.headless true --browser.gatherUsageStats false
echo.
echo サーバーが停止しました。
pause
