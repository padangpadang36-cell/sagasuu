# -*- coding: utf-8 -*-
"""
社宅.com 一気通貫パイプライン

【実行フロー】
1. ヒアリング回答スプレッドシートを読み込む
2. Gmail からヒアリングメールを取得し、進捗IDで勤務地を紐付ける
3. 企業規定書（config/company_rules.json）から家賃上限を紐付ける
4. 完成版スプレッドシートを保存する
5. 各ケースについて物件検索を実行し、PDFを進捗IDフォルダに保存する

【使い方】
  python pipeline.py

【オプション】
  --dry-run    : スプレッドシート更新まで行い、物件検索は実行しない
  --no-gmail   : Gmail 取得をスキップ（勤務地は既にシートに記載済みの場合）
  --id 001,002 : 指定した進捗IDのみ処理する
"""

import sys
import io
import asyncio
import argparse
import json
from pathlib import Path
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

BASE_DIR       = Path(__file__).parent
PROJECT_ROOT   = BASE_DIR.parent
CONFIG_DIR     = BASE_DIR / "config"
OUTPUT_DIR     = PROJECT_ROOT / "出力PDF"
INPUT_DIR      = PROJECT_ROOT / "入力データ"          # 入力 Excel の置き場
KANSEI_DIR     = INPUT_DIR / "完成版"                 # _完成版_ ファイルの保存先
DB_PATH        = INPUT_DIR / "案件データベース.xlsx"  # 処理済み案件の蓄積データベース
COMPANY_RULES_PATH = CONFIG_DIR / "company_rules.json"


# ══════════════════════════════════════════════════════════
#  企業規定書の読み込み
# ══════════════════════════════════════════════════════════

def load_company_rules() -> dict:
    """
    config/company_rules.json から家賃上限を読み込む。

    ファイル形式（例）:
    {
        "default": {
            "単身": 80000,
            "家族": 120000
        },
        "companies": {
            "株式会社ビーネックステクノロジーズ": {
                "単身": 85000,
                "家族": 130000
            }
        }
    }
    """
    if not COMPANY_RULES_PATH.exists():
        print(f"  ⚠ 企業規定書が見つかりません: {COMPANY_RULES_PATH}")
        print(f"     デフォルト家賃上限（単身:10万円/家族:15万円）を使用します")
        return {'単身': 100_000, '家族': 150_000}

    with open(COMPANY_RULES_PATH, encoding='utf-8') as f:
        data = json.load(f)

    # "default" キーの値を使用（将来的に会社名で切り替え可能）
    rules = data.get('default', {'単身': 100_000, '家族': 150_000})
    print(f"  企業規定書読み込み: 単身={rules.get('単身'):,}円 / 家族={rules.get('家族'):,}円")
    return rules


# ══════════════════════════════════════════════════════════
#  main.py の process_case を呼び出す
# ══════════════════════════════════════════════════════════

async def run_search_for_case(pw, case_params: dict, case_num: int, font_name: str, out_base_dir: Path):
    """
    1件のケースについて物件検索を実行し、PDFを進捗IDフォルダに保存する。
    main.py の process_case をラップしている。
    """
    # main.py をモジュールとしてインポート
    import main as main_module

    # 出力フォルダ名を「進捗ID_氏名」形式に設定
    anken_id = case_params.get('案件ID', '').strip()   # メール由来の案件ID
    shinkoku_id = case_params.get('管理番号', f'case_{case_num:03d}')  # 進捗ID（Excelとの紐付けキー）
    name = case_params.get('氏名', '')
    import re

    # フォルダ・ファイル名: 案件ID_氏名（案件IDがなければ進捗IDで代替）
    id_part = anken_id if anken_id else shinkoku_id
    folder_name = re.sub(r'[\\/:*?"<>|]', '_', f"{id_part}_{name}") if name else str(id_part)

    # process_case は OUTPUT_DIR / 管理番号 でフォルダを作るため、
    # 管理番号をフォルダ名形式に一時差し替えて正しいフォルダ名にする
    case_params = dict(case_params)          # 元のdictを書き換えない
    case_params['管理番号'] = folder_name

    case_dir = out_base_dir / folder_name
    case_dir.mkdir(parents=True, exist_ok=True)

    # main.py の process_case が使う OUTPUT_DIR を一時的に書き換え
    original_output_dir = main_module.OUTPUT_DIR
    main_module.OUTPUT_DIR = out_base_dir

    print(f"\n{'='*60}")
    id_display = f"案件ID={anken_id}  進捗ID={shinkoku_id}" if anken_id else f"進捗ID={shinkoku_id}"
    print(f"ケース {case_num}: {id_display}  {name}")
    print(f"  エリア: {case_params.get('希望エリア', '（未設定）')}")
    print(f"  家賃上限: {case_params.get('家賃上限（円）', 0):,}円")
    print(f"  入居形態: {case_params.get('入居形態', '')} / {case_params.get('社宅種類', '')}")
    print(f"  出力先: {case_dir}")

    try:
        result_pdf = await main_module.process_case(pw, case_params, case_num, font_name)
        print(f"  → 完了: {result_pdf}")
        return result_pdf
    except Exception as e:
        print(f"  ⚠ 検索エラー: {e}")
        import traceback; traceback.print_exc()
        return ""
    finally:
        main_module.OUTPUT_DIR = original_output_dir


# ══════════════════════════════════════════════════════════
#  パイプライン本体
# ══════════════════════════════════════════════════════════

async def run_pipeline(
    xlsx_path: Path,
    use_gmail: bool = True,
    dry_run: bool = False,
    target_ids: list[str] = None,
    gmail_query: str = 'subject:社宅',
):
    """
    一気通貫パイプラインを実行する。

    Parameters
    ----------
    xlsx_path   : ヒアリング回答スプレッドシートのパス
    use_gmail   : Gmail からメールを取得するか
    dry_run     : True の場合、物件検索を実行しない
    target_ids  : 処理する進捗IDのリスト（None=全件）
    gmail_query : Gmail 検索クエリ
    """
    print(f"\n{'='*60}")
    print(f"社宅.com パイプライン開始")
    print(f"{'='*60}")
    print(f"入力ファイル: {xlsx_path.name}")
    print(f"Gmail取得: {'有効' if use_gmail else '無効'}")
    print(f"ドライラン: {'はい（検索スキップ）' if dry_run else 'いいえ（フル実行）'}")
    if target_ids:
        print(f"対象進捗ID: {', '.join(target_ids)}")

    # ─── Step 1: スプレッドシート読み込み ───
    print(f"\n[Step 1] ヒアリングスプレッドシート読み込み")
    from spreadsheet_manager import load_hearing_responses, merge_gmail_data, \
        merge_company_rules, generate_search_params, update_spreadsheet, \
        append_to_case_database

    rows, col_idx = load_hearing_responses(xlsx_path)

    # ─── Step 2: メール情報取得・紐付け ───
    # 優先順位: ① メール貼り付け.txt > ② Gmail API > ③ スキップ
    paste_file = PROJECT_ROOT / 'メール貼り付け.txt'
    paste_available = paste_file.exists() and paste_file.stat().st_size > 200

    if paste_available:
        print(f"\n[Step 2] メール貼り付けファイルから取得: {paste_file.name}")
        try:
            from gmail_reader import load_pasted_email_file, build_shinkoku_map
            from spreadsheet_manager import merge_gmail_data
            hearing_data = load_pasted_email_file(paste_file)
            shinkoku_map = build_shinkoku_map(hearing_data)
            rows = merge_gmail_data(rows, shinkoku_map)

            # ── クロスチェック: メールにあってExcelにない進捗ID を警告 ──
            email_ids = set(shinkoku_map.keys())
            excel_ids = {str(r.get('進捗ID', '')).strip() for r in rows if r.get('進捗ID')}
            missing_in_excel = email_ids - excel_ids
            if missing_in_excel:
                print(f"  ⚠ メールにあってExcelに見つからない進捗ID: {', '.join(sorted(missing_in_excel))}")
                print(f"     → Excelにその進捗IDの行がないため検索されません。Excelを確認してください。")
        except Exception as e:
            print(f"  ⚠ 貼り付けファイル読み込みエラー: {e}")
            import traceback; traceback.print_exc()
    elif use_gmail:
        print(f"\n[Step 2] Gmail からヒアリングメール取得")
        try:
            from gmail_reader import fetch_all_hearing_data, build_shinkoku_map
            hearing_data = fetch_all_hearing_data(query=gmail_query)
            shinkoku_map = build_shinkoku_map(hearing_data)
            rows = merge_gmail_data(rows, shinkoku_map)
        except FileNotFoundError as e:
            print(f"  ⚠ Gmail認証ファイルなし: {e}")
            print(f"  → Gmail統合をスキップします（勤務地はスプレッドシートの既存データを使用）")
        except Exception as e:
            print(f"  ⚠ Gmail取得エラー: {e}")
            print(f"  → Gmail統合をスキップします")
    else:
        print(f"\n[Step 2] メール取得スキップ（--no-gmail 指定）")

    # ─── Step 3: 企業規定書・家賃上限紐付け ───
    print(f"\n[Step 3] 企業規定書・家賃上限紐付け")
    company_rules = load_company_rules()
    rows = merge_company_rules(rows, company_rules)

    # ─── Step 4: 検索パラメータ生成 ───
    print(f"\n[Step 4] 検索パラメータ生成")
    all_params = generate_search_params(rows)

    # 対象IDフィルタリング
    if target_ids:
        all_params = [p for p in all_params if p.get('管理番号') in target_ids]
        print(f"  フィルタ後: {len(all_params)}件")

    # ─── Step 5: スプレッドシート保存（完成版） ───
    print(f"\n[Step 5] 完成版スプレッドシート保存")

    # 検索ステータスを初期化
    status_by_id = {r.get('進捗ID'): '検索待ち' for r in rows}
    for r in rows:
        r['検索ステータス'] = status_by_id.get(r.get('進捗ID'), '')

    completed_xlsx = update_spreadsheet(xlsx_path, rows, col_idx)

    if dry_run:
        print(f"\n[ドライラン完了] 物件検索はスキップされました")
        print(f"完成版スプレッドシート: {completed_xlsx}")
        return

    if not all_params:
        print(f"\n⚠ 検索対象ケースが0件です。")
        print(f"  → 進捗ID・勤務地が揃っているか確認してください")
        return

    # ─── Step 6: 物件検索実行 ───
    print(f"\n[Step 6] 物件検索実行 ({len(all_params)}件)")

    import main as main_module
    font_name = main_module.register_japanese_font()
    main_module.setup_dirs()

    from playwright.async_api import async_playwright

    results = []
    async with async_playwright() as pw:
        for i, params in enumerate(all_params, 1):
            pdf_path = await run_search_for_case(
                pw, params, i, font_name, OUTPUT_DIR)
            results.append({
                '案件ID':  params.get('案件ID', ''),
                '進捗ID':  params.get('管理番号'),
                '氏名':    params.get('氏名'),
                'PDF':     pdf_path,
            })

            # ステータスを更新してスプレッドシートに反映（進捗IDで紐付け）
            shinkoku_id = params.get('管理番号')
            search_status = '完了' if pdf_path else 'エラー'
            for r in rows:
                if r.get('進捗ID') == shinkoku_id:
                    r['検索ステータス'] = search_status
                    break

            # ─── 案件データベースに追記（処理済み案件の蓄積）───
            db_params = dict(params)
            db_params['検索ステータス'] = search_status
            try:
                append_to_case_database(db_params, DB_PATH)
            except Exception as db_err:
                print(f"  ⚠ 案件DB書き込みエラー: {db_err}")

    # ─── Step 7: 最終スプレッドシート保存（ステータス更新） ───
    print(f"\n[Step 7] ステータス更新後スプレッドシート保存")
    final_xlsx = update_spreadsheet(xlsx_path, rows, col_idx)

    # ─── Step 8: 入力 Excel を「完成版/」フォルダへ移動（入力データ/ を常にクリーンに保つ）───
    # --dry-run でない、かつ入力ファイルが「入力データ/」直下にある場合のみ移動
    if xlsx_path.parent == INPUT_DIR and xlsx_path.exists():
        import shutil as _shutil
        archived = KANSEI_DIR / xlsx_path.name
        _shutil.move(str(xlsx_path), str(archived))
        print(f"\n[Step 8] 処理済み入力ファイルを移動: 入力データ/完成版/{xlsx_path.name}")
    else:
        print(f"\n[Step 8] 入力ファイル移動スキップ（パスが入力データ/外のため）")

    # ─── 完了サマリー ───
    success = sum(1 for r in results if r['PDF'])
    failed  = len(results) - success
    print(f"\n{'='*60}")
    print(f"パイプライン完了")
    print(f"  成功: {success}件 / 失敗: {failed}件 / 合計: {len(results)}件")
    print(f"  出力フォルダ: {OUTPUT_DIR}")
    print(f"  完成版スプレッドシート: 入力データ/完成版/{final_xlsx.name}")
    print(f"{'='*60}")

    for r in results:
        status = '✓' if r['PDF'] else '✗'
        anken = r.get('案件ID', '')
        id_str = f"案件ID={anken}  進捗ID={r['進捗ID']}" if anken else f"進捗ID={r['進捗ID']}"
        print(f"  {status} {id_str}  {r['氏名']}")


# ══════════════════════════════════════════════════════════
#  CLI エントリポイント
# ══════════════════════════════════════════════════════════

def parse_args():
    parser = argparse.ArgumentParser(
        description='社宅.com 一気通貫パイプライン',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使い方:
  python pipeline.py                          # 全件フル実行
  python pipeline.py --dry-run                # 検索なし（スプレッドシート更新のみ）
  python pipeline.py --no-gmail               # Gmail スキップ
  python pipeline.py --id 001 002 003         # 特定の進捗IDのみ
  python pipeline.py --query "label:社宅ヒアリング"  # Gmailクエリ指定
  python pipeline.py --xlsx "C:/path/to/回答.xlsx"  # ファイルパス指定
        """
    )
    parser.add_argument(
        '--xlsx', type=str, default=None,
        help='ヒアリング回答スプレッドシートのパス（省略時は自動検索）'
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='スプレッドシート更新まで実行、物件検索はスキップ'
    )
    parser.add_argument(
        '--no-gmail', action='store_true',
        help='Gmail 取得をスキップ'
    )
    parser.add_argument(
        '--id', nargs='+', metavar='進捗ID',
        help='処理する進捗ID（スペース区切りで複数指定可）'
    )
    parser.add_argument(
        '--query', type=str, default='subject:社宅',
        help='Gmail 検索クエリ（デフォルト: "subject:社宅"）'
    )
    return parser.parse_args()


def find_default_xlsx() -> Path:
    """
    ヒアリングフォームのスプレッドシートを自動検索する。

    検索場所（優先順位順）:
      1. 入力データ/ フォルダ  ← ★ 通常はここに置く
      2. プロジェクトルート直下（フォールバック）
      3. システムファイル/ フォルダ（フォールバック）

    除外ルール:
      - ~$ で始まるファイル（Excel の一時ロックファイル）
      - テンプレート で始まるファイル
      - _完成版_ を含むファイル（pipeline.py が生成した出力ファイル）

    複数ファイルがある場合は最終更新日時が新しいものを優先する。
    """
    search_dirs = [
        INPUT_DIR,       # 入力データ/ を最優先
        PROJECT_ROOT,    # 根っこはフォールバック
        BASE_DIR,        # システムファイル/ はさらにフォールバック
    ]
    for d in search_dirs:
        if not d.exists():
            continue
        candidates = sorted(d.glob('*.xlsx'), key=lambda x: x.stat().st_mtime, reverse=True)
        for f in candidates:
            name = f.name
            if name.startswith('~$'):
                continue
            if name.startswith('テンプレート'):
                continue
            if '_完成版_' in name:
                continue
            return f
    return None


if __name__ == '__main__':
    args = parse_args()

    # 必要フォルダを作成
    INPUT_DIR.mkdir(exist_ok=True)
    KANSEI_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)
    CONFIG_DIR.mkdir(exist_ok=True)

    # スプレッドシートパスを決定
    if args.xlsx:
        xlsx_path = Path(args.xlsx)
    else:
        xlsx_path = find_default_xlsx()
        if xlsx_path is None:
            print("[エラー] スプレッドシートが見つかりません。")
            print("  --xlsx オプションでパスを指定してください。")
            sys.exit(1)
        print(f"スプレッドシート自動検出: {xlsx_path.name}")

    if not xlsx_path.exists():
        print(f"[エラー] ファイルが見つかりません: {xlsx_path}")
        sys.exit(1)

    # config フォルダを作成
    CONFIG_DIR.mkdir(exist_ok=True)

    # 実行
    asyncio.run(run_pipeline(
        xlsx_path  = xlsx_path,
        use_gmail  = not args.no_gmail,
        dry_run    = args.dry_run,
        target_ids = args.id,
        gmail_query = args.query,
    ))
