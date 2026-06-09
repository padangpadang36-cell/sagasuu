@echo off
REM ============================================================
REM   社宅物件提案書 自動生成システム（夜間・スケジューラ実行用）
REM
REM   このファイルはタスクスケジューラや自動実行に使用します。
REM   「実行していいですか」などの確認は一切表示されません。
REM
REM   ログはシステムファイル\logs\フォルダに日付付きで保存されます。
REM ============================================================
chcp 65001 > nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

REM ── ログファイルの設定 ──────────────────────────────────────
set LOGDIR=%~dp0システムファイル\logs
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
set LOGFILE=%LOGDIR%\実行ログ_%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%.txt
set LOGFILE=%LOGFILE: =0%

echo [%date% %time%] 自動実行開始 > "%LOGFILE%"

REM ── Python を探す ─────────────────────────────────────────
set PYTHON=

for %%v in (313 312 311 310 39) do (
    if exist "%LOCALAPPDATA%\Programs\Python\Python%%v\python.exe" (
        set PYTHON=%LOCALAPPDATA%\Programs\Python\Python%%v\python.exe
        goto :python_found
    )
)
for %%v in (313 312 311 310 39) do (
    if exist "C:\Python%%v\python.exe" (
        set PYTHON=C:\Python%%v\python.exe
        goto :python_found
    )
)
for %%v in (313 312 311 310 39) do (
    if exist "C:\Program Files\Python%%v\python.exe" (
        set PYTHON=C:\Program Files\Python%%v\python.exe
        goto :python_found
    )
)
for /f "tokens=*" %%p in ('where python 2^>nul') do (
    echo %%p | findstr /i "WindowsApps" > nul
    if errorlevel 1 (
        "%%p" --version > nul 2>&1
        if not errorlevel 1 (
            set PYTHON=%%p
            goto :python_found
        )
    )
)

echo [%date% %time%] [エラー] Python が見つかりません >> "%LOGFILE%"
exit /b 1

:python_found
echo [%date% %time%] Python: !PYTHON! >> "%LOGFILE%"

set PYTHONIOENCODING=utf-8

REM pipeline.py を実行してログに出力
"!PYTHON!" システムファイル\pipeline.py %* >> "%LOGFILE%" 2>&1

if errorlevel 1 (
    echo [%date% %time%] [エラー] 処理中に問題が発生しました >> "%LOGFILE%"
    exit /b 1
)

echo [%date% %time%] 正常完了 >> "%LOGFILE%"
exit /b 0
