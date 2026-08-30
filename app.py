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
from datetime import datetime, timezone, timedelta
from pathlib import Path

import streamlit as st

# ── タイムゾーン（本番環境はUTCのため常に日本時間に変換して表示）───
JST = timezone(timedelta(hours=9))


def jst_strftime(unix_time: float, fmt: str = "%Y/%m/%d %H:%M") -> str:
    return datetime.fromtimestamp(unix_time, JST).strftime(fmt)

# ── パス設定 ────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
INPUT_DIR  = BASE_DIR / "入力データ"
KANSEI_DIR = INPUT_DIR / "完成版"
PASTE_FILE = BASE_DIR / "メール貼り付け.txt"
OUTPUT_DIR = BASE_DIR / "出力PDF"
PIPELINE   = BASE_DIR / "システムファイル" / "pipeline.py"

# ── 都道府県リスト ───────────────────────────────────────────
PREF_LIST = [
    "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県",
    "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県",
    "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県", "岐阜県",
    "静岡県", "愛知県", "三重県", "滋賀県", "京都府", "大阪府", "兵庫県",
    "奈良県", "和歌山県", "鳥取県", "島根県", "岡山県", "広島県", "山口県",
    "徳島県", "香川県", "愛媛県", "高知県", "福岡県", "佐賀県", "長崎県",
    "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県",
]

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
    .mail-card {
        background: #f1f8e9;
        border-left: 4px solid #66bb6a;
        padding: 6px 10px;
        border-radius: 4px;
        margin-bottom: 4px;
        font-size: 0.88rem;
    }
</style>
""", unsafe_allow_html=True)

# ── セッション状態の初期化 ──────────────────────────────────
if "accumulated_emails" not in st.session_state:
    st.session_state.accumulated_emails = []   # List[str] 追加済みメール本文
if "paste_key" not in st.session_state:
    st.session_state.paste_key = 0             # テキストエリアをクリアするためのキー
if "uploaded_file_data" not in st.session_state:
    st.session_state.uploaded_file_data = None  # アップロードされたExcelファイルのデータ
if "uploaded_file_name" not in st.session_state:
    st.session_state.uploaded_file_name = None

# ── ヘルパー: メール本文からプレビュー情報を抽出 ─────────────
def _parse_mail_preview(text: str) -> dict:
    anken_m   = re.search(r'案件ID\s*[：:]\s*(\S+)', text)
    sid_m     = re.search(r'進捗ID\s*[：:]\s*(\S+)', text)
    company_m = re.search(r'企業名\s*[：:]\s*(.+)', text)
    addr_all  = re.findall(r'所在地\s*[：:]\s*(.*)', text)
    work_addr = addr_all[-1].strip() if addr_all else ''
    commute_m = re.search(r'通勤方法\s*[：:]\s*(.+)', text)
    rent_m    = re.search(r'依頼上限賃料\s*[：:]\s*(.+)', text)
    return dict(
        anken   = anken_m.group(1) if anken_m else '',
        sid     = sid_m.group(1) if sid_m else '',
        company = company_m.group(1).strip() if company_m else '',
        work_addr = work_addr,
        commute = commute_m.group(1).strip() if commute_m else '',
        rent    = rent_m.group(1).strip() if rent_m else '',
    )

def _mail_card_label(text: str, index: int) -> str:
    p = _parse_mail_preview(text)
    parts = []
    if p['sid']:
        parts.append(f"進捗ID: {p['sid']}")
    if p['company']:
        parts.append(p['company'][:25])
    return "　/　".join(parts) if parts else f"メール {index + 1}"

# ══════════════════════════════════════════════════════════
#  ヘッダー
# ══════════════════════════════════════════════════════════
st.markdown('<p class="main-title">🏠 社宅物件提案書 自動生成システム</p>', unsafe_allow_html=True)
st.divider()

tab_mail, tab_manual = st.tabs(["📧 メール起点で検索", "🔍 手動で検索"])

# ══════════════════════════════════════════════════════════
#  手動検索タブ
# ══════════════════════════════════════════════════════════
with tab_manual:
    st.caption("エリアや条件を手動で入力して物件を検索します")

    MANUAL_SCRIPT = BASE_DIR / "システムファイル" / "manual_search.py"

    col_m1, col_m2 = st.columns(2, gap="large")

    with col_m1:
        st.markdown('<p class="section-label">検索条件</p>', unsafe_allow_html=True)

        area_pref_col, area_free_col = st.columns([1, 2])
        with area_pref_col:
            manual_area_pref = st.selectbox("都道府県*", ["選択してください"] + PREF_LIST, key="manual_area_pref")
        with area_free_col:
            manual_area_free = st.text_input("エリア（市区町村・自由入力）*", placeholder="例: 奥州市、盛岡市",
                                             key="manual_area_free")

        manual_rent = st.number_input("家賃上限（円）*", min_value=0, max_value=500000,
                                      value=80000, step=5000, key="manual_rent")

        work_pref_col, work_free_col = st.columns([1, 2])
        with work_pref_col:
            manual_work_pref = st.selectbox("勤務先 都道府県（任意）", ["選択してください"] + PREF_LIST,
                                            key="manual_work_pref")
        with work_free_col:
            manual_work_addr_free = st.text_input("勤務先住所（任意・自由入力）", placeholder="例: 奥州市上田字先達沢12-1",
                                                   key="manual_work_addr_free")

        manual_layout = st.text_input("希望間取り（任意）", placeholder="例: 1K、1LDK", key="manual_layout")
        manual_commute = st.text_input("通勤方法（任意）", placeholder="例: 車、電車", key="manual_commute")

        manual_area = (manual_area_pref if manual_area_pref != "選択してください" else "") + manual_area_free.strip()
        manual_work_addr = (manual_work_pref if manual_work_pref != "選択してください" else "") + manual_work_addr_free.strip()

    with col_m2:
        st.markdown('<p class="section-label">検索サイト選択</p>', unsafe_allow_html=True)
        site_atbb    = st.checkbox("ATBB（アットホーム業者向け）", value=True, key="site_atbb")
        st.caption("⚠️ 連続検索するとBOT対策により一時的に利用できなくなる場合があります")
        site_hm      = st.checkbox("東建ルームサーチ", value=True, key="site_hm")
        site_droom   = st.checkbox("D-Room（大和リビング）", value=True, key="site_droom")
        site_lp      = st.checkbox("レオパレス21", value=True, key="site_lp")
        site_reabro  = st.checkbox("リアブロ（リアネットプロ）", value=True, key="site_reabro")

        st.markdown("---")
        st.markdown('<p class="section-label">出力用（任意）</p>', unsafe_allow_html=True)
        manual_name   = st.text_input("氏名", placeholder="例: 山田 太郎", key="manual_name")
        manual_anken  = st.text_input("案件ID", placeholder="例: 159869", key="manual_anken")

    can_manual = (manual_area_pref != "選択してください") and bool(manual_area_free.strip()) and manual_rent > 0
    if not can_manual:
        st.warning("⚠️ 都道府県・エリア（市区町村）・家賃上限は必須です")

    manual_btn = st.button("🔍 検索する", type="primary", disabled=not can_manual,
                           use_container_width=True, key="manual_btn")

    if manual_btn and can_manual:
        sites = []
        if site_atbb:   sites.append("atbb")
        if site_hm:     sites.append("homemate")
        if site_droom:  sites.append("droom")
        if site_lp:     sites.append("leopalace")
        if site_reabro: sites.append("reabro")

        if not sites:
            st.warning("⚠️ 検索サイトを1つ以上選択してください")
        else:
            import json as _json
            params = {
                "希望エリア":      manual_area.strip(),
                "家賃上限（円）":  manual_rent,
                "勤務地住所":      manual_work_addr.strip(),
                "希望間取り":      manual_layout.strip(),
                "通勤方法":        manual_commute.strip(),
                "氏名":            manual_name.strip(),
                "管理番号":        manual_anken.strip() or "手動検索",
                "sites":           sites,
            }

            cmd = [
                sys.executable, "-u", str(MANUAL_SCRIPT),
                "--params", _json.dumps(params, ensure_ascii=False),
            ]
            env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}

            st.divider()
            st.subheader("📋 検索ログ")
            log_ph = st.empty()
            log_lines_m: list[str] = []

            import time as _time
            start_m = _time.time()
            proc_m = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                cwd=str(BASE_DIR / "システムファイル"), env=env,
            )
            for line in iter(proc_m.stdout.readline, ""):
                log_lines_m.append(line.rstrip())
                log_ph.code("\n".join(log_lines_m[-60:]), language=None)
            proc_m.wait()
            elapsed_m = _time.time() - start_m

            st.divider()
            if proc_m.returncode == 0:
                st.success(f"✅ 検索完了（所要時間: {int(elapsed_m // 60)}分{int(elapsed_m % 60)}秒）")

                # __RESULT_JSON__ ブロックから物件一覧を取得して画面表示
                full_log = "\n".join(log_lines_m)
                m = re.search(r"__RESULT_JSON__\n(.*?)\n__RESULT_JSON_END__", full_log, re.S)
                properties = []
                if m:
                    try:
                        result_data = _json.loads(m.group(1))
                        properties = result_data.get("properties", [])
                    except Exception as e:
                        st.warning(f"結果データの解析に失敗しました: {e}")

                if properties:
                    st.subheader(f"🏠 検索結果（{len(properties)}件）")
                    table_rows = [{
                        "サイト": p.get("source", ""),
                        "物件名": p.get("name", ""),
                        "家賃": p.get("rent", ""),
                        "間取り": p.get("layout", ""),
                        "面積": p.get("area", ""),
                        "住所": p.get("address", ""),
                    } for p in properties]
                    st.dataframe(table_rows, use_container_width=True)
                else:
                    st.info("該当する物件が見つかりませんでした。")

                # 生成されたPDF一覧とZIPダウンロード
                case_id_safe = re.sub(r'[\\/:*?"<>|]', "_",
                                      manual_anken.strip() or "手動検索")
                result_dir = OUTPUT_DIR / case_id_safe
                if result_dir.exists():
                    pdfs = sorted(result_dir.glob("*.pdf"))
                    if pdfs:
                        st.subheader("📁 生成されたファイル")
                        for pdf in pdfs:
                            st.markdown(f"&nbsp;&nbsp;📄 `{pdf.name}`")
                        import zipfile, io as _io
                        zip_buf = _io.BytesIO()
                        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                            for pdf in pdfs:
                                zf.write(pdf, pdf.name)
                        zip_buf.seek(0)
                        st.download_button(
                            label=f"⬇️ ZIPでダウンロード（{len(pdfs)}件）",
                            data=zip_buf,
                            file_name=f"{case_id_safe}.zip",
                            mime="application/zip",
                            key="manual_zip",
                        )
                    elif properties:
                        st.caption("※ 選択したサイトの一部はPDF出力に対応していません（対応: ATBB・東建）。上記の検索結果一覧をご確認ください。")
            else:
                st.error("❌ 検索中にエラーが発生しました。ログを確認してください。")

with tab_mail:
    st.caption("メール本文と Excel を用意して「実行する」を押すだけで物件検索〜PDF出力まで自動で行います")

    col_mail, col_excel = st.columns([3, 2], gap="large")

    with col_mail:
        st.markdown('<p class="section-label">① ヒアリングメールの本文を貼り付ける</p>',
                    unsafe_allow_html=True)

        email_text = st.text_area(
            label="email_input",
            label_visibility="collapsed",
            height=200,
            placeholder=(
                "ここに1件分のメール本文をそのまま貼り付けてください。\n\n"
                "例:\n"
                "進捗ID: 74377\n"
                "企業名: ○○株式会社\n"
                "所在地: 茨城県 かすみがうら市上稲吉2046番地\n"
                "就業開始日: 2026年7月1日\n"
                "通勤方法: 自転車\n"
                "..."
            ),
            key=f"email_text_{st.session_state.paste_key}",
        )

        if email_text.strip():
            p = _parse_mail_preview(email_text)
            lines = []
            if p['anken']:     lines.append(f"案件ID　: {p['anken']}")
            if p['sid']:       lines.append(f"進捗ID　: {p['sid']}")
            if p['company']:   lines.append(f"企業名　: {p['company']}")
            if p['work_addr']: lines.append(f"就業先　: {p['work_addr']}")
            if p['commute']:   lines.append(f"通勤方法: {p['commute']}")
            if p['rent']:      lines.append(f"上限賃料: {p['rent']}")

            with st.expander("✅ 読み取り内容（追加前確認）", expanded=True):
                st.code('\n'.join(lines) if lines else "（進捗IDが見つかりません）")

            btn_add, btn_clr = st.columns([3, 1])
            with btn_add:
                if st.button("➕  この1件を追加する", type="primary", use_container_width=True):
                    st.session_state.accumulated_emails.append(email_text.strip())
                    st.session_state.paste_key += 1
                    st.rerun()
            with btn_clr:
                if st.button("✕ クリア", use_container_width=True):
                    st.session_state.paste_key += 1
                    st.rerun()

        mails = st.session_state.accumulated_emails
        if mails:
            st.markdown(f"**追加済み: {len(mails)}件**")
            for i, mail in enumerate(mails):
                card_col, del_col = st.columns([10, 1])
                with card_col:
                    st.markdown(
                        f'<div class="mail-card">✅ {_mail_card_label(mail, i)}</div>',
                        unsafe_allow_html=True,
                    )
                with del_col:
                    if st.button("✕", key=f"del_mail_{i}", help="このメールを削除"):
                        st.session_state.accumulated_emails.pop(i)
                        st.rerun()

            if st.button("🗑️ 追加済みをすべてクリア", key="clear_all_mails"):
                st.session_state.accumulated_emails = []
                st.rerun()

        elif not email_text.strip():
            st.caption("メール本文を貼り付けて「➕ この1件を追加する」を押してください。")

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
            st.session_state.uploaded_file_data = uploaded_file.getvalue()
            st.session_state.uploaded_file_name = uploaded_file.name
            st.success(f"📄 {uploaded_file.name}")
        elif st.session_state.uploaded_file_data:
            st.success(f"📄 {st.session_state.uploaded_file_name}")

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

    st.divider()
    has_mail  = bool(st.session_state.accumulated_emails)
    has_excel = bool(uploaded_file) or bool(st.session_state.uploaded_file_data) or bool(existing_excels)
    can_run   = has_mail and has_excel

    if not has_mail:
        st.warning("⚠️  メール本文を1件以上追加してください")
    if not has_excel:
        st.warning("⚠️  Excel ファイルをアップロードするか、入力データフォルダに入れてください")

    run_btn = st.button(
        f"🚀  実行する（{len(st.session_state.accumulated_emails)}件）" if has_mail else "🚀  実行する",
        type="primary",
        disabled=not can_run,
        use_container_width=True,
    )

    if run_btn and can_run:
        combined_mail = "\n========\n".join(st.session_state.accumulated_emails)
        PASTE_FILE.write_text(combined_mail, encoding="utf-8")

        file_data = uploaded_file.getvalue() if uploaded_file else st.session_state.uploaded_file_data
        file_name = uploaded_file.name if uploaded_file else st.session_state.uploaded_file_name
        if file_data:
            INPUT_DIR.mkdir(exist_ok=True)
            save_path = INPUT_DIR / file_name
            save_path.write_bytes(file_data)

        cmd = [sys.executable, "-u", str(PIPELINE)]
        if target_id.strip():
            cmd += ["--id"] + target_id.strip().split()
        if dry_run:
            cmd.append("--dry-run")

        st.divider()
        st.subheader("📋 実行ログ")
        log_placeholder = st.empty()
        log_lines: list[str] = []

        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
        start_time = time.time()
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            cwd=str(BASE_DIR), env=env,
        )

        for line in iter(process.stdout.readline, ""):
            log_lines.append(line.rstrip())
            log_placeholder.code("\n".join(log_lines[-60:]), language=None)

        process.wait()
        elapsed = time.time() - start_time

        st.divider()
        if process.returncode == 0:
            st.success(f"✅ 処理完了（所要時間: {int(elapsed // 60)}分{int(elapsed % 60)}秒）")
            st.session_state.accumulated_emails = []
            PASTE_FILE.write_text(
                "# 処理が完了したため内容をクリアしました。\n"
                "# 次回実行時はここにメール本文を貼り付けてください。\n",
                encoding="utf-8",
            )

            if OUTPUT_DIR.exists():
                case_dirs = sorted(
                    [d for d in OUTPUT_DIR.iterdir() if d.is_dir()],
                    key=lambda d: d.stat().st_mtime, reverse=True,
                )
                recent_dirs = case_dirs[:10]
                if recent_dirs:
                    st.subheader("📁 生成されたファイル")
                    for case_dir in recent_dirs:
                        pdfs = sorted(case_dir.glob("*.pdf"))
                        if pdfs:
                            with st.expander(f"📂 {case_dir.name}　（{len(pdfs)}件）", expanded=True):
                                for pdf in pdfs:
                                    st.markdown(f"&nbsp;&nbsp;📄 `{pdf.name}`")
                                import zipfile, io as _io
                                zip_buf = _io.BytesIO()
                                with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                                    for pdf in pdfs:
                                        zf.write(pdf, pdf.name)
                                zip_buf.seek(0)
                                st.download_button(
                                    label=f"⬇️ ZIPでダウンロード（{len(pdfs)}件）",
                                    data=zip_buf,
                                    file_name=f"{case_dir.name}.zip",
                                    mime="application/zip",
                                    key=f"zip_{case_dir.name}",
                                )
        else:
            st.error("❌ 処理中にエラーが発生しました。上のログを確認してください。")
            st.info("💡 ログの最後のエラーメッセージを担当者に連絡してください。")

        log_dir = BASE_DIR / "システムファイル" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        ts = jst_strftime(time.time(), "%Y%m%d_%H%M%S")
        (log_dir / f"実行ログ_{ts}.txt").write_text("\n".join(log_lines), encoding="utf-8")

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
    pass  # Webアプリではフォルダを開く機能は非対応

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
            mtime = jst_strftime(case_dir.stat().st_mtime)
            label = f"📂 {case_dir.name}　（PDF {len(pdfs)}件 ／ {mtime}）"

            with st.expander(label, expanded=False):

                if pdfs:
                    for pdf in pdfs:
                        size_kb = pdf.stat().st_size // 1024
                        st.markdown(f"&nbsp;&nbsp;📄 `{pdf.name}` &nbsp; {size_kb} KB")
                    import zipfile, io as _io
                    zip_buf = _io.BytesIO()
                    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                        for pdf in pdfs:
                            zf.write(pdf, pdf.name)
                    zip_buf.seek(0)
                    st.download_button(
                        label=f"⬇️ ZIPでダウンロード（{len(pdfs)}件）",
                        data=zip_buf,
                        file_name=f"{case_dir.name}.zip",
                        mime="application/zip",
                        key=f"zip2_{case_dir.name}",
                    )
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
    pass  # Webアプリではフォルダを開く機能は非対応

if KANSEI_DIR.exists():
    kansei_files = sorted(
        KANSEI_DIR.glob("*.xlsx"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    kansei_files = [f for f in kansei_files if not f.name.startswith("~$")]
    if kansei_files:
        for f in kansei_files[:10]:
            mtime = jst_strftime(f.stat().st_mtime)
            size_kb = f.stat().st_size // 1024
            st.markdown(f"📗 `{f.name}` &nbsp; {size_kb} KB &nbsp; {mtime}")
    else:
        st.info("完成版スプレッドシートがまだありません。")
else:
    st.info("完成版フォルダがまだ存在しません。実行後に表示されます。")
