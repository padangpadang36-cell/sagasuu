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
    get_maps_screenshot, merge_pdf_with_map_image,
    login_atbb, search_atbb, download_atbb_print_pdf,
    login_homemate, search_homemate, extract_homemate_properties, download_homemate_detail_pdf,
    login_droom, search_droom, download_droom_bulk_pdf,
    search_leopalace, download_leopalace_pdf,
    login_reabro, search_reabro, download_reabro_pdfs, get_reabro_address,
    clean_droom_address, append_labeled_maps_to_pdf,
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
                                  work_address, commute, shot_dir, case_dir, case_id, font_name, all_props)
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


def _rename_output(path: str, case_id: str, site_label: str) -> str:
    """出力PDFのファイル名を「{管理番号}_{サイト名}_元のファイル名」形式に統一する"""
    if not path:
        return path
    p = Path(path)
    new_name = f"{case_id}_{site_label}_{p.name}"
    new_path = p.with_name(new_name)
    try:
        p.rename(new_path)
        return str(new_path)
    except Exception:
        return path


async def _attach_commute_map(map_page, work_address, commute, prop, pdf_path,
                               case_dir, shot_dir, font_name, tag):
    """物件住所→勤務先住所のGoogleマップ通勤ルートを取得し、PDFに合成する。
    勤務先住所が未入力、または物件に住所が無い場合は何もせず元のPDFパスを返す。"""
    if not work_address or not pdf_path:
        return pdf_path
    addr = prop.get('address', '')
    if not addr:
        return pdf_path
    try:
        map_png = str(shot_dir / f"map_{tag}.png")
        ok = await get_maps_screenshot(map_page, addr, work_address, map_png,
                                       commute_method=commute)
        if not ok:
            return pdf_path
        merged_path = str(Path(pdf_path).with_name(Path(pdf_path).stem + "_地図付き.pdf"))
        merge_pdf_with_map_image(pdf_path, map_png, merged_path, font_name,
                                 commute_method=commute, workplace=work_address)
        return merged_path
    except Exception as e:
        print(f"  ⚠ 地図合成エラー: {e}")
        return pdf_path


async def _run_all_sites(ctx, pw, sites, area, rent_max, layout,
                          work_address, commute, shot_dir, case_dir, case_id, font_name, all_props):
        # 通勤ルート地図の取得専用ページ（サイトへのログイン不要）
        map_page = await ctx.new_page() if work_address else None
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
                            dp = _rename_output(dp, case_id, "ATBB")
                            dp = await _attach_commute_map(map_page, work_address, commute, props[idx], dp,
                                                           case_dir, shot_dir, font_name, f"atbb_{idx}")
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
                                    dp = _rename_output(dp, case_id, "東建")
                                    dp = await _attach_commute_map(map_page, work_address, commute, hp, dp,
                                                                   case_dir, shot_dir, font_name, f"homemate_{idx}")
                                    print(f"  東建 PDF{idx+1}: {Path(dp).name}")
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
                            bulk_pdf = _rename_output(bulk_pdf, case_id, "D-Room")
                            print(f"  D-Room 一括PDF: {Path(bulk_pdf).name}")

                            # 勤務先住所がある場合、各物件から勤務先までの通勤ルート
                            # 地図を取得し、一括PDFの末尾に物件ごとの地図ページとして追記する
                            if map_page and work_address:
                                map_entries = []
                                for midx, mp in enumerate(props[:5]):
                                    addr = clean_droom_address(mp.get('address', ''))
                                    if not addr:
                                        continue
                                    mp['address'] = addr
                                    map_png = str(shot_dir / f"map_droom_{midx}.png")
                                    ok_map = await get_maps_screenshot(map_page, addr, work_address, map_png,
                                                                       commute_method=commute)
                                    if ok_map:
                                        map_entries.append((mp.get('name', f'物件{midx+1}'), map_png))
                                if map_entries:
                                    merged_path = str(Path(bulk_pdf).with_name(
                                        Path(bulk_pdf).stem + "_地図付き.pdf"))
                                    bulk_pdf = append_labeled_maps_to_pdf(
                                        bulk_pdf, map_entries, merged_path, font_name,
                                        commute_method=commute, workplace=work_address)
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
                            f"{case_id}_レオパレス_{lp.get('name', f'物件{idx+1}')}", case_dir)
                        if dp:
                            dp = await _attach_commute_map(map_page, work_address, commute, lp, dp,
                                                           case_dir, shot_dir, font_name, f"leopalace_{idx}")
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
                            # 一覧テーブルには住所が無いため、物件詳細ページから取得する
                            addr = await get_reabro_address(page, ctx, rp['room_id'])
                            if addr:
                                rp['address'] = addr
                                print(f"  リアブロ住所取得: {addr}")
                            map_png = ""
                            if map_page and work_address and addr:
                                map_png = str(shot_dir / f"map_reabro_{idx}.png")
                                ok_map = await get_maps_screenshot(map_page, addr, work_address, map_png,
                                                                   commute_method=commute)
                                if not ok_map:
                                    map_png = ""
                            pdfs = await download_reabro_pdfs(
                                ctx, rp['room_id'],
                                f"{case_id}_リアブロ_{rp.get('name', f'物件{idx+1}')}",
                                case_dir, font_name, map_png,
                                commute_method=commute, workplace=work_address)
                            saved = [v for v in pdfs.values() if v]
                            if saved:
                                print(f"  リアブロ PDF{idx+1}: {len(saved)}件保存")
                    all_props.extend(props)
                await page.close()
            except Exception as e:
                print(f"  リアブロ エラー: {e}")

        if map_page:
            await map_page.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--params", required=True, help="JSON形式の検索パラメータ")
    args = parser.parse_args()

    params = json.loads(args.params)
    asyncio.run(run_manual_search(params))


if __name__ == "__main__":
    main()
