# -*- coding: utf-8 -*-
"""ATBBインフォシート：実際のフローで開いてpdf出力URLを把握"""
import sys, io, asyncio
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import os
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv(Path(__file__).parent.parent / ".env")
ATBB_URL  = "https://atbb.athome.jp/"
ATBB_ID   = os.getenv("ATBB_ID", "")
ATBB_PASS = os.getenv("ATBB_PASS", "")

OUT_DIR = Path(__file__).parent / "デバッグ" / "atbb2"
OUT_DIR.mkdir(parents=True, exist_ok=True)

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, channel="chrome", slow_mo=300)
        ctx = await browser.new_context(viewport={"width":1280,"height":900}, locale="ja-JP",
                                        accept_downloads=True)
        page = await ctx.new_page()

        # ネットワーク監視
        net_log = []
        page.on("request",  lambda r: net_log.append(("REQ", r.method, r.url)))
        page.on("response", lambda r: net_log.append(("RES", r.status, r.headers.get("content-type",""), r.url)))

        # ─── ATBBログイン ───
        await page.goto(ATBB_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)
        await page.locator('input[name="loginId"]').fill(ATBB_ID)
        await page.locator('input[type="password"]').fill(ATBB_PASS)
        await page.locator('input[type="submit"]').click()
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        await asyncio.sleep(2)
        print(f"ログイン後URL: {page.url}")
        await page.screenshot(path=str(OUT_DIR / "01_login.png"))

        # ─── 物件検索ページへ ───
        # 流通物件検索 を開く
        try:
            menu = page.locator('a:has-text("物件・会社検索")').first
            await menu.click()
            await asyncio.sleep(1)
            async with ctx.expect_page(timeout=8000) as np_info:
                await page.get_by_text("流通物件検索").first.click()
            search_page = await np_info.value
            await search_page.wait_for_load_state("domcontentloaded", timeout=15000)
            await asyncio.sleep(2)
            print(f"流通物件検索URL: {search_page.url}")
            await search_page.screenshot(path=str(OUT_DIR / "02_search.png"))
        except Exception as e:
            print(f"流通物件検索エラー: {e}")
            search_page = page

        # ─── 物件を1件クリックしてインフォシートを開く ───
        print("\n=== 物件一覧のshosaiボタンを探す ===")
        await asyncio.sleep(3)

        # shosai_0 ボタンがあるか確認
        shosai_exists = await search_page.evaluate("() => !!document.getElementById('shosai_0')")
        print(f"shosai_0 exists: {shosai_exists}")

        if not shosai_exists:
            # 何か物件が表示されているか確認
            body_text = await search_page.evaluate("() => document.body.innerText.substring(0,500)")
            print(f"ページテキスト: {body_text}")
            await search_page.screenshot(path=str(OUT_DIR / "03_no_shosai.png"))
            # インフォシートボタンを探す
            info_btns = await search_page.evaluate("""
                () => Array.from(document.querySelectorAll('button, a'))
                    .filter(el => el.innerText.includes('インフォシート') || el.innerText.includes('詳細'))
                    .map(el => ({text: el.innerText.trim().substring(0,30), tag: el.tagName, id: el.id, cls: el.className.substring(0,40)}))
                    .slice(0, 10)
            """)
            print(f"インフォシート/詳細ボタン: {info_btns}")

        # shosai_0 があればクリック
        if shosai_exists:
            net_log.clear()
            print("\nshosai_0 をクリック...")
            try:
                async with ctx.expect_page(timeout=10000) as dp_info:
                    await search_page.evaluate("document.getElementById('shosai_0').click()")
                detail_page = await dp_info.value
                await detail_page.wait_for_load_state("domcontentloaded", timeout=20000)
            except Exception as e:
                print(f"新規タブなし: {e}")
                await search_page.wait_for_load_state("domcontentloaded", timeout=10000)
                detail_page = search_page

            await asyncio.sleep(3)
            print(f"詳細URL: {detail_page.url}")
            await detail_page.screenshot(path=str(OUT_DIR / "04_detail.png"))

            # インフォシートボタン
            info_btns = await detail_page.evaluate("""
                () => Array.from(document.querySelectorAll('button, a, input[type="button"]'))
                    .filter(el => {
                        const t = (el.innerText||el.value||'').trim();
                        return t.includes('インフォシート') || t.includes('PDF') || t.includes('印刷');
                    })
                    .map(el => ({
                        text: (el.innerText||el.value||'').trim().substring(0,40),
                        tag: el.tagName, id: el.id,
                        cls: el.className.substring(0,50),
                        href: el.href || ''
                    }))
                    .slice(0, 10)
            """)
            print(f"\nインフォシート/PDF/印刷ボタン: {len(info_btns)}件")
            for b in info_btns:
                print(f"  [{b['text']}] id={b['id']} cls={b['cls']}")

            # インフォシートボタンをクリック
            net_log.clear()
            for btn_selector in ['#infoSheetButtonTop_0', 'button:has-text("インフォシート")', 'a:has-text("インフォシート")']:
                try:
                    btn = detail_page.locator(btn_selector).first
                    if await btn.is_visible(timeout=2000):
                        print(f"\nインフォシートボタン({btn_selector})をクリック...")
                        try:
                            async with ctx.expect_page(timeout=10000) as info_info:
                                await btn.click()
                            info_page = await info_info.value
                            await info_page.wait_for_load_state("domcontentloaded", timeout=20000)
                            await asyncio.sleep(3)
                            print(f"インフォシートURL: {info_page.url}")
                            await info_page.screenshot(path=str(OUT_DIR / "05_infosheet.png"))

                            # ページの全要素を確認
                            all_els = await info_page.evaluate("""
                                () => Array.from(document.querySelectorAll('button, a, input[type="button"], [onclick]'))
                                    .filter(el => el.offsetParent !== null)
                                    .map(el => ({
                                        text: (el.innerText||el.value||'').trim().replace(/\\s+/g,' ').substring(0,50),
                                        tag: el.tagName, id: el.id,
                                        cls: el.className.substring(0,50),
                                        onclick: (el.getAttribute('onclick')||'').substring(0,80),
                                        href: el.href||''
                                    }))
                                    .filter(x => x.text)
                            """)
                            print(f"\nインフォシートページの要素 ({len(all_els)}件):")
                            for el in all_els[:20]:
                                print(f"  [{el['text']}] tag={el['tag']} id={el['id']}")
                                if el['onclick']:
                                    print(f"    onclick={el['onclick']}")
                                if el['href'] and el['href'] != 'javascript:void(0)':
                                    print(f"    href={el['href'][:80]}")

                            # ネットワークログ（PDF/print関連）
                            print("\nネットワーク:")
                            for entry in net_log:
                                url = str(entry[-1])
                                if any(k in url.lower() for k in ['pdf', 'print', 'infosheet', 'export', 'download']):
                                    print(f"  {entry[0]} {entry[1] if len(entry)>1 else ''} {url[:100]}")

                            # HTML保存
                            html = await info_page.content()
                            with open(str(OUT_DIR / "infosheet.html"), "w", encoding="utf-8") as f:
                                f.write(html)
                            print(f"\nHTML保存: {OUT_DIR}/infosheet.html")

                            # 「編集」「メニュー」ボタンを探す
                            print("\n=== 編集メニューを探す ===")
                            for label in ["編集メニュー", "編集", "メニュー", "設定"]:
                                try:
                                    el = info_page.get_by_text(label, exact=False).first
                                    if await el.is_visible(timeout=1000):
                                        print(f"  発見: '{label}'")
                                        await el.click()
                                        await asyncio.sleep(2)
                                        await info_page.screenshot(path=str(OUT_DIR / "06_after_edit_click.png"))

                                        # クリック後の要素
                                        after_els = await info_page.evaluate("""
                                            () => Array.from(document.querySelectorAll('a, button, li, label'))
                                                .filter(el => el.offsetParent !== null)
                                                .map(el => ({
                                                    text: (el.innerText||'').trim().replace(/\\s+/g,' ').substring(0,50),
                                                    tag: el.tagName, cls: el.className.substring(0,50)
                                                }))
                                                .filter(x => x.text)
                                        """)
                                        print("クリック後の要素:")
                                        for el2 in after_els:
                                            if any(k in el2['text'] for k in ['一般', '客付', '手数料', 'PDF', '出力', '印刷']):
                                                print(f"  ★ [{el2['text']}]")
                                            else:
                                                print(f"    [{el2['text']}]")
                                        break
                                except Exception:
                                    continue

                        except Exception as e2:
                            print(f"インフォシートタブエラー: {e2}")
                        break
                except Exception:
                    continue

        # ネットワーク全ログ
        print("\n=== ネットワーク全ログ(重要) ===")
        for entry in net_log:
            url = str(entry[-1])
            if any(k in url.lower() for k in ['pdf', 'print', 'infosheet', 'export', 'download', 'factsheet', 'sheet']):
                print(f"  {entry[0]} {entry[1] if len(entry)>1 else ''} {url[:100]}")

        print("\n=== 完了 ===")
        await browser.close()

asyncio.run(main())
