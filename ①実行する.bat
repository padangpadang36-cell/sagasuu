@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion
cd /d "%~dp0"
title 社宅物件提案書 自動生成システム

REM ── 自動実行モードの判定 ─────────────────────────────────
REM   --auto を引数に渡すと pause なしで終了する（夜間・スケジューラ実行用）
set AUTO_MODE=0
for %%a in (%*) do (
    if "%%a"=="--auto" set AUTO_MODE=1
)

echo ============================================================
echo   社宅物件提案書 自動生成システム
if "%AUTO_MODE%"=="1" (
    echo   [自動実行モード: 確認なしで処理します]
)
echo ============================================================
echo.

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

REM Windows Store 以外の python.exe を探す
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

echo [エラー] Python が見つかりませんでした。
echo.
echo Python 3.9 以上をインストールしてください。
echo   https://www.python.org/downloads/
echo.
if "%AUTO_MODE%"=="0" pause
exit /b 1

:python_found
echo Python: !PYTHON!
echo.
echo ============================================================
echo   処理を開始します。
echo   ブラウザが自動で起動します。
echo   終了するまでそのままお待ちください。
echo ============================================================
echo.

set PYTHONIOENCODING=utf-8

REM --auto を除いた引数をそのまま pipeline.py へ渡す
set PIPELINE_ARGS=
for %%a in (%*) do (
    if not "%%a"=="--auto" set PIPELINE_ARGS=!PIPELINE_ARGS! %%a
)

"!PYTHON!" システムファイル\pipeline.py !PIPELINE_ARGS!

if errorlevel 1 (
    echo.
    echo ============================================================
    echo   [エラー] 処理中に問題が発生しました。
    echo   上記のエラーメッセージを担当者にお知らせください。
    echo   ログは システムファイル\logs\ フォルダに保存されます。
    echo ============================================================
    if "%AUTO_MODE%"=="0" pause
    exit /b 1
)

echo.
echo ============================================================
echo   完了しました！
echo   「出力PDF」フォルダに提案書が生成されています。
echo ============================================================
echo.
if "%AUTO_MODE%"=="0" pause
