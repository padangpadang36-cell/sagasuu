# -*- coding: utf-8 -*-
"""リアプロ: room_system_menu から room_id を取得してfactsheetダウンロードをテスト"""
import sys, io, asyncio, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import os
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv(Path(__file__).parent.parent / ".env")
REABRO_BASE_URL = "https://www.realnetpro.com"
REABRO_ID       = os.getenv("REABRO_ID", "")
REABRO_PASS     = os.getenv("REABRO_PASS", "")

OUT_DIR = Path(__file__).parent / "デバッグ" / "reabro9"
OUT_DIR.mkdir(parents=True, exist_ok=True)

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, channel="chrome", slow_mo=300)
        ctx = await browser.new_context(viewport={"width":1280,"height":900}, locale="ja-JP",
                                        accept_downloads=True)
        page = await ctx.new_page()

        # Login
        await page.goto(REABRO_BASE_URL + "/index.php", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)
        await page.locator('input[name="id"]').fill(REABRO_ID)
        await page.locator('input[name="pass"]').fill(REABRO_PASS)
        await page.locator('button:has-text("ログイン")').first.click()
        await asyncio.sleep(3)

        # Monitor AJAX
        ajax_log = []
        def on_req(r):
            if not any(x in r.url for x in ['google','facebook','yahoo','gstatic','doubleclick']):
                ajax_log.append(('REQ', r.method, r.url))
        def on_res(r):
            if not any(x in r.url for x in ['google','facebook','yahoo','gstatic','doubleclick']):
                ajax_log.append(('RES', r.status, r.url))
        page.on('request', on_req)
        page.on('response', on_res)

        # Building list default
        await page.goto(REABRO_BASE_URL + "/main.php?method=estate&display=building",
                        wait_until="networkidle", timeout=30000)
        await asyncio.sleep(5)

        # Extract rooms from default page
        rooms = await page.evaluate("""
            () => {
                const results = [];
                document.querySelectorAll('.room_system_menu[title]').forEach(el => {
                    const t = el.getAttribute('title');
                    if (t && t.includes(',')) {
                        const parts = t.split(',');
                        results.push({
                            room_id: parts[0],
                            building_name: parts[1] || '',
                            room_name: parts[2] || ''
                        });
                    }
                });
                return results.slice(0, 20);
            }
        """)

        print(f"Default page rooms: {len(rooms)}")
        for r in rooms[:5]:
            print(f"  room_id={r['room_id']} building={r['building_name']} room={r['room_name']}")

        await page.screenshot(path=str(OUT_DIR / "01_default.png"))

        # Now try keyword search
        ajax_log.clear()
        kw = page.locator('input[name="keyword"]').first
        await kw.click(click_count=3)
        await kw.fill("大阪市北区")
        await asyncio.sleep(1)

        # Try pressing Enter or clicking search button
        kw_val = await kw.input_value()
        print(f"Keyword value: {kw_val}")

        # Find and click search button
        clicked = False
        for txt in ["検 索", "検索", "絞り込み"]:
            try:
                btn = page.get_by_text(txt, exact=True).first
                if await btn.is_visible(timeout=1000):
                    await btn.click()
                    print(f"Clicked search button: [{txt}]")
                    clicked = True
                    break
            except:
                pass

        if not clicked:
            await kw.press("Enter")
            print("Pressed Enter")

        # Wait for results to update
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except:
            pass
        await asyncio.sleep(5)
        await page.screenshot(path=str(OUT_DIR / "02_after_search.png"))

        # Check for Osaka rooms
        rooms2 = await page.evaluate("""
            () => {
                const results = [];
                document.querySelectorAll('.room_system_menu[title]').forEach(el => {
                    const t = el.getAttribute('title');
                    if (t && t.includes(',')) {
                        const parts = t.split(',');
                        results.push({room_id: parts[0], building_name: parts[1] || ''});
                    }
                });
                return results.slice(0, 20);
            }
        """)
        print(f"After search rooms: {len(rooms2)}")
        for r in rooms2[:5]:
            print(f"  {r}")

        # AJAX log after search
        print("\nAJAX log after search:")
        for entry in ajax_log[-30:]:
            print(f"  {entry[0]} {entry[1] if len(entry)>1 else ''} {entry[-1][:100]}")

        # Use whichever rooms are available
        test_rooms = rooms2 if rooms2 else rooms
        if not test_rooms:
            print("No rooms found!")
            await browser.close()
            return

        room_id = test_rooms[0]['room_id']
        print(f"\n=== Testing factsheet download with room_id={room_id} ===")

        # Method 1: page.goto + expect_download
        fs_url_moto  = f"{REABRO_BASE_URL}/common/factsheet.php?id={room_id}&org=2"
        fs_url_kyaku = f"{REABRO_BASE_URL}/common/factsheet.php?id={room_id}"
        print(f"元付けURL: {fs_url_moto}")
        print(f"客付けURL: {fs_url_kyaku}")

        for label, url, suffix in [("元付け", fs_url_moto, "org2"), ("客付け", fs_url_kyaku, "org0")]:
            fs_page = await ctx.new_page()
            dl_ok = False
            try:
                async with fs_page.expect_download(timeout=15000) as dl_info:
                    await fs_page.goto(url, timeout=15000)
                dl = await dl_info.value
                fname = dl.suggested_filename or f"reabro_{room_id}_{suffix}.pdf"
                await dl.save_as(str(OUT_DIR / fname))
                print(f"[{label}] Downloaded: {fname}")
                dl_ok = True
            except Exception as e:
                print(f"[{label}] Download failed: {type(e).__name__}: {e}")
                await fs_page.screenshot(path=str(OUT_DIR / f"03_{suffix}_page.png"))
                print(f"  URL after: {fs_page.url}")
                content = await fs_page.content()
                # Check if it's a PDF rendered in browser
                print(f"  Page title: {await fs_page.title()}")

            if not dl_ok:
                # Method 2: urllib with cookies
                print(f"  Trying urllib for {label}...")
                cookies = await ctx.cookies(urls=[REABRO_BASE_URL])
                cookie_str = "; ".join(f'{c["name"]}={c["value"]}' for c in cookies)
                req = urllib.request.Request(url, headers={
                    "Cookie": cookie_str,
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Referer": REABRO_BASE_URL + "/main.php"
                })
                try:
                    with urllib.request.urlopen(req, timeout=20) as resp:
                        ct = resp.headers.get("Content-Type", "")
                        data = resp.read()
                        save_path = str(OUT_DIR / f"urllib_{room_id}_{suffix}.bin")
                        with open(save_path, 'wb') as f:
                            f.write(data)
                        print(f"  urllib: ct={ct} size={len(data)} bytes")
                        print(f"  First bytes: {data[:20]}")
                except Exception as e2:
                    print(f"  urllib failed: {e2}")

            await fs_page.close()

        print("\n=== 完了 ===")
        await browser.close()

asyncio.run(main())
