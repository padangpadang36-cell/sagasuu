# -*- coding: utf-8 -*-
"""東建ルームサーチ 検索→結果ページ構造調査"""
import sys, io, asyncio, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import os
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv(Path(__file__).parent.parent / ".env")
HM_URL  = "https://www.homemate.co.jp/hmroom/"
HM_ID   = os.getenv("HM_ID", "")
HM_PASS = os.getenv("HM_PASS", "")

OUT_DIR = Path(__file__).parent / "デバッグ" / "homemate"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 検索条件（テスト用）
TEST_PREF = "27"        # 大阪府
TEST_AREA = "大阪市北区"

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, channel="chrome", slow_mo=600)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 900}, locale="ja-JP")
        page = await ctx.new_page()

        # ── 1. ログイン ──
        await page.goto(HM_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)
        await page.locator('input[name="id"]').fill(HM_ID)
        await page.locator('input[name="pw"]').fill(HM_PASS)
        await page.locator('#btn_login a').click()
        await page.wait_for_load_state("domcontentloaded", timeout=15000)
        await asyncio.sleep(3)
        print(f"ログイン後URL: {page.url}")
        await page.screenshot(path=str(OUT_DIR / "10_top.png"))

        # ログイン成功確認
        if "top.asp" not in page.url:
            print(f"  ⚠ ログイン失敗 (URL: {page.url})")
            print("  別のブラウザセッションが開いている場合は先に閉じてください")
            input("\n[確認] Enterで終了...")
            await browser.close()
            return

        # ── 2. 都道府県選択 ──
        print(f"\n都道府県選択: {TEST_PREF}(大阪府)")
        await page.select_option('select[name="prf"]', TEST_PREF)
        # getCitySb() が走る → citysb が動的ロードされる
        await asyncio.sleep(3)
        await page.screenshot(path=str(OUT_DIR / "11_pref_selected.png"))

        # citysb の選択肢を確認
        citysb_options = await page.evaluate("""
            () => Array.from(document.querySelector('select[name="citysb"]').options)
                .map(o => ({v: o.value, t: o.text}))
        """)
        print(f"\ncitysb 選択肢 ({len(citysb_options)}件):")
        for o in citysb_options:
            print(f"  {o}")

        # ── 3. 市区を選択 (大阪市) ──
        # citysb から "大阪市" を探す
        target_city = None
        for o in citysb_options:
            if TEST_AREA[:3] in o['t']:  # "大阪市"
                target_city = o['v']
                print(f"\n市選択: {o['t']} (value={o['v']})")
                break

        if target_city:
            await page.select_option('select[name="citysb"]', target_city)
            # getCity() が走る → seljiscd が動的ロード
            await asyncio.sleep(3)
            await page.screenshot(path=str(OUT_DIR / "12_city_selected.png"))

            seljiscd_options = await page.evaluate("""
                () => Array.from(document.querySelector('select[name="seljiscd"]').options)
                    .map(o => ({v: o.value, t: o.text}))
            """)
            print(f"\nseljiscd 選択肢 ({len(seljiscd_options)}件):")
            for o in seljiscd_options:
                print(f"  {o}")

            # ── 4. 区を選択して追加 (大阪市北区) ──
            target_ward = None
            for o in seljiscd_options:
                if TEST_AREA in o['t'] or o['t'] in TEST_AREA:
                    target_ward = o['v']
                    print(f"\n区選択: {o['t']} (value={o['v']})")
                    break

            if not target_ward and seljiscd_options:
                # 最初の選択肢でテスト
                target_ward = seljiscd_options[0]['v']
                print(f"\n区選択(先頭): {seljiscd_options[0]['t']} (value={target_ward})")

            if target_ward:
                await page.select_option('select[name="seljiscd"]', target_ward)
                await asyncio.sleep(1)
                # addlist を手動で呼ぶ (onclick の代わり)
                await page.evaluate("""
                    () => {
                        const f = document.frmCond;
                        addlist(f.seljiscd, f.stjiscd, 'jiscd');
                    }
                """)
                await asyncio.sleep(1)

                # stjiscd の中身確認
                stock = await page.evaluate("""
                    () => Array.from(document.querySelector('select[name="stjiscd"]').options)
                        .map(o => ({v: o.value, t: o.text}))
                """)
                print(f"\nstjiscd (検索対象): {stock}")
                await page.screenshot(path=str(OUT_DIR / "13_ward_added.png"))

        # ── 5. 検索実行 ──
        print("\n検索実行...")
        # nextSubmit() を呼んで frmCond を送信
        result = await page.evaluate("""
            () => {
                const ok = nextSubmit();
                if (ok !== false) document.frmCond.submit();
                return ok;
            }
        """)
        print(f"nextSubmit result: {result}")

        try:
            await page.wait_for_load_state("domcontentloaded", timeout=20000)
        except Exception:
            pass
        await asyncio.sleep(4)
        await page.screenshot(path=str(OUT_DIR / "14_search_result.png"))
        print(f"\n検索結果URL: {page.url}")

        # ── 6. 検索結果の構造を調査 ──
        body_text = await page.evaluate("() => document.body.innerText.substring(0, 3000)")
        print(f"\n検索結果ページ内容:\n{body_text}")

        # 物件リスト要素を探す
        bukken_info = await page.evaluate("""
            () => {
                const info = {};
                // よく使われる物件リストのセレクタ候補
                const candidates = [
                    '.bukken', '.property', '.item', '.result-item',
                    'tr.bukken', 'div.bukken', 'li.bukken',
                    '[class*="bukken"]', '[class*="property"]', '[class*="item"]',
                    'table tr', '.list-item'
                ];
                for (const sel of candidates) {
                    const els = document.querySelectorAll(sel);
                    if (els.length > 0) {
                        info[sel] = {
                            count: els.length,
                            sample: els[0].textContent.trim().substring(0, 100)
                        };
                    }
                }
                // テーブル構造
                info.tables = Array.from(document.querySelectorAll('table')).map((t,i) => ({
                    index: i,
                    rows: t.rows.length,
                    sample: t.rows[0] ? t.rows[0].textContent.trim().substring(0, 80) : ''
                })).slice(0, 10);
                // リンク
                info.links = Array.from(document.querySelectorAll('a'))
                    .filter(a => a.href && !a.href.startsWith('javascript'))
                    .map(a => ({text: a.textContent.trim().substring(0,30), href: a.href}))
                    .slice(0, 20);
                return info;
            }
        """)

        result_json = OUT_DIR / "search_result_structure.json"
        result_json.write_text(json.dumps(bukken_info, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"\n結果構造JSON保存: {result_json}")
        print(json.dumps(bukken_info, ensure_ascii=False, indent=2)[:2000])

        html = await page.content()
        (OUT_DIR / "14_search_result.html").write_text(html, encoding='utf-8', errors='replace')
        print(f"\nHTML保存: {OUT_DIR / '14_search_result.html'}")

        input("\n[確認] ブラウザを確認したらEnterで終了...")
        await browser.close()

asyncio.run(main())
