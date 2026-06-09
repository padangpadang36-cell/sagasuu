# -*- coding: utf-8 -*-
"""
サンプルメールデータで物件検索をテスト実行するスクリプト。
Gmailやスプレッドシートを使わずに1件だけ検索して動作確認する。

使い方:
  python test_run.py
"""

import sys
import io
import asyncio
import json
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

BASE_DIR     = Path(__file__).parent
PROJECT_ROOT = BASE_DIR.parent
OUTPUT_DIR   = PROJECT_ROOT / "出力PDF"
CONFIG_DIR   = BASE_DIR / "config"


async def main():
    # ── Step1: サンプルメールをパース ──────────────────────
    from gmail_reader import parse_email_text, SAMPLE_EMAIL
    from spreadsheet_manager import _extract_city_from_address, _classify_area

    print("=" * 60)
    print("テスト実行: サンプルメールで物件検索")
    print("=" * 60)

    email_data = parse_email_text(SAMPLE_EMAIL)
    print(f"  進捗ID    : {email_data['shinkoku_id']}")
    print(f"  入居者名  : {email_data['resident_name']}")
    print(f"  企業名    : {email_data['company_name']}")
    print(f"  就業先住所: {email_data['work_address']}")
    print(f"  最寄駅    : {email_data['nearest_station'] or '（なし）'}")
    print(f"  通勤方法  : {email_data['commute_method']}")
    print(f"  社宅条件  : {email_data['housing_condition']}")
    print(f"  入居希望日: {email_data['move_in_date']}")

    # ── Step2: 家賃上限を規程書から算出 ────────────────────
    rules_path = CONFIG_DIR / "company_rules.json"
    with open(rules_path, encoding='utf-8') as f:
        rules = json.load(f)

    area_cls    = rules['area_classification']
    rent_limits = rules['rent_limits']
    area        = _classify_area(email_data['work_address'], area_cls)

    occ_raw = email_data.get('occupancy_type') or '単身'
    if '4人' in occ_raw:
        occ_key = '家族（4人以上）'
    elif '3人' in occ_raw or '家族' in occ_raw:
        occ_key = '家族（3人）'
    elif '2人' in occ_raw or '夫婦' in occ_raw:
        occ_key = '2人入居'
    else:
        occ_key = '単身'

    if email_data.get('rent_limit'):
        rent_max = email_data['rent_limit']
        print(f"\n  家賃上限: {rent_max:,}円（メール記載値）")
    else:
        rent_max = rent_limits.get(occ_key, {}).get(area, 70_000)
        print(f"\n  エリア区分: {area} / 入居形態: {occ_key}")
        print(f"  家賃上限: {rent_max:,}円（規程書より）")

    # ── Step3: 検索エリア ───────────────────────────────────
    station = email_data.get('nearest_station') or ''
    if station:
        search_area = station
    else:
        search_area = _extract_city_from_address(email_data['work_address'])
    print(f"  検索エリア: {search_area}")

    # ── Step4: 検索パラメータ組み立て ─────────────────────
    sid  = email_data['shinkoku_id']      # '74377'
    name = email_data['resident_name']    # '入居者名'

    case_params = {
        '管理番号':     sid,
        '氏名':         name,
        '希望エリア':   search_area,
        '家賃上限（円）': rent_max,
        '希望間取り':   '',          # 入居形態不明のため空
        '通勤時間（分）': 30,
        '入居形態':     occ_raw,
        '社宅種類':     email_data.get('housing_condition', ''),
        '入居希望日':   email_data.get('move_in_date', ''),
        '通勤方法':     email_data.get('commute_method', ''),
        '性別':         '',
        '国籍':         '',
        '勤務地住所':   email_data['work_address'],
        '最寄り駅':     email_data.get('nearest_station', ''),
        '企業名':       email_data.get('company_name', ''),
        '就業開始日':   email_data.get('work_start_date', ''),
        'メールアドレス': '',
        '携帯電話番号': '',
        'その他要望':   email_data.get('remarks', ''),
    }

    print(f"\n{'=' * 60}")
    print(f"検索パラメータ確認")
    print(f"  管理番号  : {case_params['管理番号']}")
    print(f"  氏名      : {case_params['氏名']}")
    print(f"  希望エリア: {case_params['希望エリア']}")
    print(f"  家賃上限  : {case_params['家賃上限（円）']:,}円")
    print(f"  社宅種類  : {case_params['社宅種類']}")
    print(f"  入居希望日: {case_params['入居希望日']}")
    print(f"  通勤方法  : {case_params['通勤方法']}")
    print(f"  その他要望: {case_params['その他要望']}")

    # ── Step5: フォルダ名を「進捗ID_氏名」形式に設定 ────────
    import re
    folder_name = re.sub(r'[\\/:*?"<>|]', '_', f"{sid}_{name}")
    # process_case は OUTPUT_DIR / 管理番号 でフォルダを作るため
    # 管理番号を folder_name に差し替えることで正しいフォルダ名にする
    case_params['管理番号'] = folder_name

    case_dir = OUTPUT_DIR / folder_name
    case_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n  出力フォルダ: {case_dir}")

    # ── Step6: 物件検索実行 ────────────────────────────────
    print(f"\n{'=' * 60}")
    print("物件検索を開始します...")

    import main as main_module
    main_module.OUTPUT_DIR = OUTPUT_DIR   # 出力先を明示的にセット
    font_name = main_module.register_japanese_font()
    main_module.setup_dirs()

    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        result_pdf = await main_module.process_case(pw, case_params, 1, font_name)

    if result_pdf:
        print(f"\n✓ 完了: {result_pdf}")
    else:
        print(f"\n✗ 物件検索でエラーが発生しました")

    print(f"\n出力フォルダを確認してください:")
    print(f"  {case_dir}")


if __name__ == '__main__':
    asyncio.run(main())
