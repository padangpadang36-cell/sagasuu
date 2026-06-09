# -*- coding: utf-8 -*-
"""
社宅物件提案書 自動生成システム - Web インターフェース
Streamlit アプリ

起動方法:
    python -m streamlit run app.py
    または ③起動する.bat をダブルクリック
"""

import os
import re
import sys
import subprocess
import time
from pathlib import Path

import streamlit as st

# ── パス設定 ────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
INPUT_DIR  = BASE_DIR / "入力データ"
KANSEI_DIR = INPUT_DIR / "完成版"
PASTE_FILE = BASE_DIR / "メール貼り付け.txt"
OUTPUT_DIR = BASE_DIR / "出力PDF"
PIPELINE   = BASE_DIR / "システムファイル" / "pipeline.py"

# ── ページ設定 ───────────────────────────────────────────────
st.set_page_config(
    page_title="社宅物件提案書 自動生成",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS ─────────────────────────────────────────────────────
st.markdown("""
<style>
    .main-title { font-size: 1.6rem; font-weight: bold; color: #1a237e; margin-bottom: 0; }
    .section-label { font-size: 1.05rem; font-weight: bold; margin-bottom: 4px; }
    .preview-box { background: #e8f5e9; border-left: 4px solid #43a047;
                   padding: 8px 12px; border-radius: 4px; font-size: 0.9rem; }
    .stButton > button { font-size: 1.1rem; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════
#  ヘッダー
# ══════════════════════════════════════════════════════════
st.markdown('<p class="main-title">🏠 社宅物件提案書 自動生成システム</p>', unsafe_allow_html=True)
st.caption("メール本文と Excel を用意して「実行する」を押すだけで物件検索〜PDF出力まで自動で行います")
st.divider()

# ══════════════════════════════════════════════════════════
#  Step 1・2 を左右に並べる
# ══════════════════════════════════════════════════════════
col_mail, col_excel = st.columns([3, 2], gap="large")

# ─── 左: メール貼り付け ─────────────────────────────────
with col_mail:
    st.markdown('<p class="section-label">① ヒアリングメールの本文を貼り付ける</p>',
                unsafe_allow_html=True)
    email_text = st.text_area(
        label="email_input",
        label_visibility="collapsed",
        height=340,
        placeholder=(
            "ここにメール本文をそのまま貼り付けてください。\n\n"
            "例:\n"
            "進捗ID: 74377\n"
            "企業名: ○○株式会社\n"
            "所在地: 茨城県 かすみがうら市上稲吉2046番地\n"
            "就業開始日: 2026年7月1日\n"
            "通勤方法: 自転車\n"
            "...\n\n"
            "複数件ある場合は\n"
            "========\n"
            "で区切って貼り付けてください。"
        ),
        key="email_text",
    )

    # リアルタイムプレビュー
    if email_text.strip():
        anken_m  = re.search(r'案件ID\s*[：:]\s*(\S+)', email_text)
        sid_m    = re.search(r'進捗ID\s*[：:]\s*(\S+)', email_text)
        company_m = re.search(r'企業名\s*[：:]\s*(.+)', email_text)
        addr_all = re.findall(r'所在地\s*[：:]\s*(.*)', email_text)
        work_addr = addr_all[-1].strip() if addr_all else ''
        commute_m = re.search(r'通勤方法\s*[：:]\s*(.+)', email_text)
        rent_m   = re.search(r'依頼上限賃料\s*[：:]\s*(.+)', email_text)

        lines = []
        if anken_m:  lines.append(f"案件ID　: {anken_m.group(1)}")
        if sid_m:    lines.append(f"進捗ID　: {sid_m.group(1)}")
        if company_m: lines.append(f"企業名　: {company_m.group(1).strip()}")
        if work_addr: lines.append(f"就業先　: {work_addr}")
        if commute_m: lines.append(f"通勤方法: {commute_m.group(1).strip()}")
        if rent_m and rent_m.group(1).strip():
            lines.append(f"上限賃料: {rent_m.group(1).strip()}")

        # 複数件カウント
        mail_count = len(re.split(r'\n={8,}\n|\n-{8,}\n', email_text.strip()))
        label = f"✅ 読み取り内容（{mail_count}件）" if mail_count > 1 else "✅ 読み取り内容"
        with st.expander(label, expanded=True):
            st.code('\n'.join(lines) if lines else "（進捗IDが見つかりません）")

# ─── 右: Excel アップロード ─────────────────────────────
with col_excel:
    st.markdown('<p class="section-label">② ヒアリングフォームの Excel をアップロード</p>',
                unsafe_allow_html=True)

    uploaded_file = st.file_uploader(
        label="excel_upload",
        label_visibility="collapsed",
        type=["xlsx"],
        help="Googleフォームからダウンロードした回答.xlsx ファイルです",
        key="excel_upload",
    )

    if uploaded_file:
        st.success(f"📄 {uploaded_file.name}")

    # 入力データフォルダの既存ファイル
    existing_excels = []
    if INPUT_DIR.exists():
        existing_excels = [
            f for f in sorted(INPUT_DIR.glob("*.xlsx"), key=lambda x: x.stat().st_mtime, reverse=True)
            if not f.name.startswith('~$')
            and '_完成版_' not in f.name
            and not f.name.startswith('テンプレート')
        ]

    if existing_excels:
        st.info("📂 入力データフォルダにあるファイル:\n" +
                "\n".join(f"・{f.name}" for f in existing_excels))
    elif not uploaded_file:
        st.warning("入力データフォルダに Excel がありません。\nアップロードするか、先にフォルダに入れてください。")

    st.markdown("---")

    # オプション
    st.markdown('<p class="section-label">オプション</p>', unsafe_allow_html=True)
    target_id = st.text_input(
        "特定の進捗IDのみ処理する（空白 = 全件）",
        placeholder="例: 74377　複数の場合はスペース区切り: 74377 74378",
        key="target_id",
    )
    dry_run = st.checkbox(
        "ドライラン（スプレッドシート更新のみ・物件検索はしない）",
        key="dry_run",
    )

# ══════════════════════════════════════════════════════════
#  実行ボタン
# ══════════════════════════════════════════════════════════
st.divider()

has_mail  = bool(email_text.strip())
has_excel = bool(uploaded_file) or bool(existing_excels)
can_run   = has_mail and has_excel

if not has_mail:
    st.warning("⚠️  メール本文を貼り付けてください")
if not has_excel:
    st.warning("⚠️  Excel ファイルをアップロードするか、入力データフォルダに入れてください")

run_btn = st.button(
    "🚀  実行する",
    type="primary",
    disabled=not can_run,
    use_container_width=True,
)

# ══════════════════════════════════════════════════════════
#  実行処理
# ══════════════════════════════════════════════════════════
if run_btn and can_run:

    # ① メール本文を保存
    if has_mail:
        PASTE_FILE.write_text(email_text, encoding="utf-8")

    # ② Excel を保存
    if uploaded_file:
        INPUT_DIR.mkdir(exist_ok=True)
        save_path = INPUT_DIR / uploaded_file.name
        save_path.write_bytes(uploaded_file.getvalue())

    # ③ pipeline.py の引数を組み立てる
    cmd = [sys.executable, "-u", str(PIPELINE)]
    if target_id.strip():
        cmd += ["--id"] + target_id.strip().split()
    if dry_run:
        cmd.append("--dry-run")

    # ④ 実行してログをリアルタイム表示
    st.divider()
    st.subheader("📋 実行ログ")
    log_placeholder = st.empty()
    log_lines: list[str] = []

    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}

    start_time = time.time()
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(BASE_DIR),
        env=env,
    )

    for line in iter(process.stdout.readline, ""):
        log_lines.append(line.rstrip())
        # 直近 60 行を表示
        log_placeholder.code("\n".join(log_lines[-60:]), language=None)

    process.wait()
    elapsed = time.time() - start_time

    # ⑤ 結果表示
    st.divider()
    if process.returncode == 0:
        st.success(f"✅ 処理完了（所要時間: {int(elapsed // 60)}分{int(elapsed % 60)}秒）")

        # メール貼り付けファイルをクリア（次回実行のため）
        PASTE_FILE.write_text(
            "# 処理が完了したため内容をクリアしました。\n"
            "# 次回実行時はここにメール本文を貼り付けてください。\n",
            encoding="utf-8",
        )

        # 生成されたPDF一覧
        if OUTPUT_DIR.exists():
            case_dirs = sorted(
                [d for d in OUTPUT_DIR.iterdir() if d.is_dir()],
                key=lambda d: d.stat().st_mtime,
                reverse=True,
            )
            recent_dirs = case_dirs[:10]  # 直近10件

            if recent_dirs:
                st.subheader("📁 生成されたファイル")
                for case_dir in recent_dirs:
                    pdfs = sorted(case_dir.glob("*.pdf"))
                    if pdfs:
                        with st.expander(f"📂 {case_dir.name}　（{len(pdfs)}件）", expanded=True):
                            for pdf in pdfs:
                                st.markdown(f"&nbsp;&nbsp;📄 `{pdf.name}`")
    else:
        st.error("❌ 処理中にエラーが発生しました。上のログを確認してください。")
        st.info("💡 ログの最後のエラーメッセージを担当者に連絡してください。")

    # ⑥ 全ログをファイルにも保存
    log_dir = BASE_DIR / "システムファイル" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    (log_dir / f"実行ログ_{ts}.txt").write_text(
        "\n".join(log_lines), encoding="utf-8"
    )

# ══════════════════════════════════════════════════════════
#  出力ファイル確認
# ══════════════════════════════════════════════════════════
st.divider()
st.subheader("📁 出力ファイル確認")

col_refresh, col_open = st.columns([1, 4])
with col_refresh:
    if st.button("🔄 更新", key="refresh_files"):
        st.rerun()
with col_open:
    if st.button("📂 出力PDFフォルダを開く", key="open_output_dir"):
        if OUTPUT_DIR.exists():
            import subprocess as _sp
            _sp.Popen(["explorer", str(OUTPUT_DIR)])
        else:
            st.warning("出力PDFフォルダがまだありません。")

if OUTPUT_DIR.exists():
    case_dirs = sorted(
        [d for d in OUTPUT_DIR.iterdir() if d.is_dir()],
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )

    if case_dirs:
        # 検索ボックス
        search_q = st.text_input(
            "🔍 案件名・IDで絞り込み",
            placeholder="例: 74377 または 田中",
            label_visibility="visible",
            key="file_search",
        )

        filtered = [
            d for d in case_dirs
            if not search_q.strip() or search_q.strip().lower() in d.name.lower()
        ]

        st.caption(f"全 {len(case_dirs)} 件　表示中: {len(filtered)} 件")

        for case_dir in filtered:
            pdfs = sorted(case_dir.glob("*.pdf"))
            mtime = time.strftime("%Y/%m/%d %H:%M", time.localtime(case_dir.stat().st_mtime))
            label = f"📂 {case_dir.name}　（PDF {len(pdfs)}件 ／ {mtime}）"

            with st.expander(label, expanded=False):
                btn_col, info_col = st.columns([2, 5])
                with btn_col:
                    if st.button("エクスプローラーで開く", key=f"open_{case_dir.name}"):
                        import subprocess as _sp
                        _sp.Popen(["explorer", str(case_dir)])

                if pdfs:
                    for pdf in pdfs:
                        size_kb = pdf.stat().st_size // 1024
                        st.markdown(f"&nbsp;&nbsp;📄 `{pdf.name}` &nbsp; {size_kb} KB")
                else:
                    st.caption("（PDFファイルがありません）")
    else:
        st.info("まだ出力されたフォルダがありません。")
else:
    st.info("「出力PDF」フォルダがまだ存在しません。実行後に表示されます。")

# ── 完成版スプレッドシート確認 ──────────────────────────────
st.divider()
st.subheader("📊 完成版スプレッドシート")

col_xls_refresh, col_xls_open = st.columns([1, 4])
with col_xls_refresh:
    pass  # 上の更新ボタンで兼用
with col_xls_open:
    if st.button("📂 完成版フォルダを開く", key="open_kansei_dir"):
        if KANSEI_DIR.exists():
            import subprocess as _sp
            _sp.Popen(["explorer", str(KANSEI_DIR)])
        else:
            st.warning("完成版フォルダがまだありません。")

if KANSEI_DIR.exists():
    kansei_files = sorted(
        KANSEI_DIR.glob("*.xlsx"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    kansei_files = [f for f in kansei_files if not f.name.startswith("~$")]
    if kansei_files:
        for f in kansei_files[:10]:
            mtime = time.strftime("%Y/%m/%d %H:%M", time.localtime(f.stat().st_mtime))
            size_kb = f.stat().st_size // 1024
            st.markdown(f"📗 `{f.name}` &nbsp; {size_kb} KB &nbsp; {mtime}")
    else:
        st.info("完成版スプレッドシートがまだありません。")
else:
    st.info("完成版フォルダがまだ存在しません。実行後に表示されます。")
