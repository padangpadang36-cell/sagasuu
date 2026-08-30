"""
手動検索スクリプト
app.py の「手動検索」タブから subprocess で呼ばれる。
--params に JSON 文字列を渡す。

JSON 例:
{
  "area": "茨城県つくば市",
  "rent_max": 80000,
  "layout": "1K・1DK",
  "work_address": "茨城県かすみがうら市上稲吉2046",
  "commute": "自転車",
  "name": "田中太郎",
  "case_id": "手動001",
  "sites": ["ATBB", "東建", "D-Room", "レオパレス", "リアブロ"]
}
"""

import sys
import io
import asyncio
import argparse
import json
import os
import re
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from dotenv import load_dotenv
from playwright.async_api import async_playwright

BASE_DIR   = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "出力PDF"
SHOT_DIR   = BASE_DIR / "システムファイル" / "デバッグ" / "screenshots"

load_dotenv(BASE_DIR / ".env")

# main.py と同じ関数群をインポート
sys.path.insert(0, str(Path(__file__).parent))
from main import (
    register_japanese_font,
    filter_properties,
    jst_now,
    login_atbb, search_atbb, download_atbb_print_pdf,
    login_homemate, search_homemate, extract_homemate_properties, download_homemate_detail_pdf,
    login_droom, search_droom, download_droom_bulk_pdf,
    search_leopalace, download_leopalace_pdf,
    login_reabro, search_reabro, download_reabro_pdfs,
)


async def run_manual_search(params: dict):
    area         = params.get("希望エリア", params.get("area", ""))
    rent_max     = int(params.get("家賃上限（円）", params.get("家賃上限", params.get("rent_max", 100000))))
    layout       = params.get("希望間取り", params.get("layout", ""))
    work_address = params.get("勤務地住所", params.get("work_address", ""))
    commute      = params.get("通勤方法", params.get("commute", ""))
    name         = params.get("氏名", params.get("name", "手動検索"))
    case_id      = params.get("管理番号", params.get("case_id", "")) or f"手動_{jst_now().strftime('%Y%m%d_%H%M%S')}"
    sites        = [s.strip() for s in params.get("sites", [])]

    case_id = re.sub(r'[\\/:*?"<>|]', "_", case_id).strip()
    case_dir = OUTPUT_DIR / case_id
    # 前回の出力PDFをクリアして古いファイルが混入しないようにする
    if case_dir.exists():
        import shutil
        shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True, exist_ok=True)
    shot_dir = SHOT_DIR / case_id
    shot_dir.mkdir(parents=True, exist_ok=True)

    font_name = register_japanese_font()
    all_props = []

    print(f"検索開始: {case_id}")
    print(f"  エリア: {area}  家賃上限: {rent_max:,}円  間取り: {layout}")
    print(f"  選択サイト: {', '.join(sites) if sites else '（なし）'}")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, slow_mo=400)
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="ja-JP",
        )
        try:
            await _run_all_sites(ctx, pw, sites, area, rent_max, layout,
                                  work_address, shot_dir, case_dir, font_name, all_props)
        finally:
            await browser.close()

    # 結果を JSON で標準出力に出力（app.py が読み取る）
    result = {
        "case_id":    case_id,
        "case_dir":   str(case_dir),
        "total":      len(all_props),
        "properties": all_props,
    }
    print("__RESULT_JSON__")
    print(json.dumps(result, ensure_ascii=False, default=str))
    print("__RESULT_JSON_END__")
    print(f"完了: 合計 {len(all_props)} 件")


async def _run_all_sites(ctx, pw, sites, area, rent_max, layout,
                          work_address, shot_dir, case_dir, font_name, all_props):
        # ── ATBB ─────────────────────────────────────────────
        if "atbb" in sites or "ATBB" in sites:
            try:
                page = await ctx.new_page()
                if await login_atbb(page, shot_dir):
                    props, page = await search_atbb(page, ctx, area, rent_max, layout, shot_dir)
                    props = filter_properties(props, rent_max)
                    print(f"  ATBB: {len(props)}件取得（フィルター後）")
                    for idx, p in enumerate(props):
                        p['source'] = 'atbb'
                        p['atbb_idx'] = idx
                    for idx in range(min(len(props), 3)):
                        dp = await download_atbb_print_pdf(page, ctx, pw, idx, props[idx], case_dir, font_name)
                        if dp:
                            print(f"  ATBB PDF{idx+1}: {Path(dp).name}")
                    all_props.extend(props)
                await page.close()
            except Exception as e:
                print(f"  ATBB エラー: {e}")

        # ── 東建ルームサーチ ────────────────────────────────
        if "homemate" in sites or "東建" in sites:
            try:
                page = await ctx.new_page()
                hm_shot = shot_dir / "homemate"
                hm_shot.mkdir(exist_ok=True)
                if await login_homemate(page, hm_shot):
                    ok = await search_homemate(page, area, hm_shot, work_address=work_address)
                    if ok:
                        props = await extract_homemate_properties(page, ctx, hm_shot)
                        props = filter_properties(props, rent_max)
                        print(f"  東建: {len(props)}件取得（フィルター後）")
                        for idx, hp in enumerate(props[:3]):
                            if hp.get('detail_href'):
                                dp = await download_homemate_detail_pdf(page, pw, hp['detail_href'], case_dir)
                                if dp:
                                    print(f"  東建 PDF{idx+1}: {dp}")
                        for p in props:
                            p['source'] = 'homemate'
                        all_props.extend(props)
                await page.close()
            except Exception as e:
                print(f"  東建 エラー: {e}")

        # ── D-Room（住所・家賃上限で検索 → Droomシート一括PDFを取得）──
        if "droom" in sites or "D-Room" in sites:
            try:
                page = await ctx.new_page()
                dr_shot = shot_dir / "droom"
                dr_shot.mkdir(exist_ok=True)
                if await login_droom(page, dr_shot):
                    props = await search_droom(page, area, rent_max, dr_shot)
                    props = filter_properties(props, rent_max)
                    print(f"  D-Room: {len(props)}件取得（フィルター後）")
                    for p in props:
                        p['source'] = 'droom'
                    if props:
                        bulk_pdf = await download_droom_bulk_pdf(page, case_dir)
                        if bulk_pdf:
                            print(f"  D-Room 一括PDF: {Path(bulk_pdf).name}")
                    all_props.extend(props)
                await page.close()
            except Exception as e:
                print(f"  D-Room エラー: {e}")

        # ── レオパレス21（都道府県→市区町村URLで検索 → 最大3件の詳細PDF）──
        if "leopalace" in sites or "レオパレス" in sites:
            try:
                page = await ctx.new_page()
                lp_shot = shot_dir / "leopalace"
                lp_shot.mkdir(exist_ok=True)
                props = await search_leopalace(page, area, rent_max, lp_shot, work_address=work_address)
                props = filter_properties(props, rent_max)
                print(f"  レオパレス: {len(props)}件取得（フィルター後）")
                for idx, p in enumerate(props):
                    p['source'] = 'leopalace'
                for idx, lp in enumerate(props[:3]):
                    if lp.get('detail_url'):
                        dp = await download_leopalace_pdf(
                            page, pw, lp['detail_url'],
                            f"レオパレス_{lp.get('name', f'物件{idx+1}')}", case_dir)
                        if dp:
                            print(f"  レオパレス PDF{idx+1}: {Path(dp).name}")
                all_props.extend(props)
                await page.close()
            except Exception as e:
                print(f"  レオパレス エラー: {e}")

        # ── リアブロ（所在地絞り込み→家賃上限設定 → 最大2件の地図なしPDF）──
        if "reabro" in sites or "リアブロ" in sites:
            try:
                page = await ctx.new_page()
                rb_shot = shot_dir / "reabro"
                rb_shot.mkdir(exist_ok=True)
                if await login_reabro(page, rb_shot):
                    props = await search_reabro(page, area, rent_max, rb_shot, work_address=work_address)
                    props = filter_properties(props, rent_max)
                    print(f"  リアブロ: {len(props)}件取得（フィルター後）")
                    for p in props:
                        p['source'] = 'reabro'
                    for idx, rp in enumerate(props[:2]):
                        if rp.get('room_id'):
                            pdfs = await download_reabro_pdfs(
                                ctx, rp['room_id'],
                                f"リアブロ_{rp.get('name', f'物件{idx+1}')}",
                                case_dir, font_name)
                            saved = [v for v in pdfs.values() if v]
                            if saved:
                                print(f"  リアブロ PDF{idx+1}: {len(saved)}件保存")
                    all_props.extend(props)
                await page.close()
            except Exception as e:
                print(f"  リアブロ エラー: {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--params", required=True, help="JSON形式の検索パラメータ")
    args = parser.parse_args()

    params = json.loads(args.params)
    asyncio.run(run_manual_search(params))


if __name__ == "__main__":
    main()
