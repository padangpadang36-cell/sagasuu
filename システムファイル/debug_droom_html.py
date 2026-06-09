# -*- coding: utf-8 -*-
"""D-Room 検索結果HTMLを保存して構造を調査"""
import sys, io, asyncio
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import os
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv(Path(__file__).parent.parent / ".env")
DROOM_LOGIN_URL    = "https://anavi.daiwaliving.co.jp/dp/login"
DROOM_ROOMLIST_URL = "https://anavi.daiwaliving.co.jp/dp/navi/room/RoomList/menu"
DROOM_TENPO = os.getenv("DROOM_TENPO", "")
DROOM_TANTO = os.getenv("DROOM_TANTO", "")
DROOM_PASS  = os.getenv("DROOM_PASS", "")

OUT_DIR = Path(__file__).parent / "デバッグ" / "droom_html"
OUT_DIR.mkdir(parents=True, exist_ok=True)

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, channel="chrome", slow_mo=200)
        ctx = await browser.new_context(viewport={"width":1280,"height":900}, locale="ja-JP")
        page = await ctx.new_page()

        # Login
        await page.goto(DROOM_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)
        await page.locator('#txtEnterpriseId').fill(DROOM_TENPO)
        await page.locator('#txtUserId').fill(DROOM_TANTO)
        await page.locator('#txtPassword').fill(DROOM_PASS)
        await page.locator('#btnLoginButton').click()
        await asyncio.sleep(3)
        if "CheckLogin" in page.url:
            try:
                await page.locator('#forcepassword').fill(DROOM_PASS)
            except Exception:
                pass
            await page.locator('#forceloginok').click()
            await asyncio.sleep(3)
        # お知らせページ
        try:
            btn = page.get_by_text("メニューに進む").first
            if await btn.is_visible(timeout=3000):
                await btn.click()
                await asyncio.sleep(2)
        except Exception:
            pass
        print(f"Login URL: {page.url}")

        # Search
        await page.goto(DROOM_ROOMLIST_URL, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)
        await page.locator('input[name="address"]').fill("大阪市北区")
        await page.locator('input[name="rentTo"]').fill("8")
        await page.evaluate("() => { const f = document.querySelector('form'); if (f) f.submit(); }")
        await asyncio.sleep(5)

        # Save HTML
        html = await page.content()
        with open(str(OUT_DIR / "search_result.html"), "w", encoding="utf-8") as f:
            f.write(html)
        print("HTML saved")

        # Get first checkbox row structure
        row_info = await page.evaluate("""
            () => {
                const results = [];
                for (const cb of document.querySelectorAll('input[type="checkbox"]')) {
                    if (!cb.value || !cb.value.match(/^\\d{7,12}-\\d{3}/)) continue;
                    const row = cb.closest('tr') || cb.closest('li') || cb.parentElement;
                    if (!row) continue;
                    const cells = Array.from(row.querySelectorAll('td, th'))
                        .map(td => ({
                            cls: td.className.substring(0,50),
                            text: td.innerText.trim().substring(0,80)
                        }));
                    results.push({
                        value: cb.value,
                        parentTag: row.tagName,
                        parentCls: row.className.substring(0,60),
                        cells: cells.slice(0, 15)
                    });
                    if (results.length >= 2) break;
                }
                return results;
            }
        """)
        print(f"\nCheckbox rows: {len(row_info)}")
        for r in row_info:
            print(f"\nValue: {r['value']} | Parent: {r['parentTag']}.{r['parentCls']}")
            for i, c in enumerate(r['cells']):
                print(f"  Cell {i} [{c['cls']}]: {c['text'][:60]}")

        # Also get surrounding structure of first checkbox
        surrounding = await page.evaluate("""
            () => {
                const cb = document.querySelector('input[type="checkbox"][value]');
                if (!cb) return 'no checkbox found';
                const row = cb.closest('tr') || cb.parentElement;
                return row ? row.outerHTML.substring(0, 3000) : 'no row';
            }
        """)
        print(f"\nFirst checkbox row HTML (first 3000 chars):")
        print(surrounding[:2000])

        await browser.close()

asyncio.run(main())
