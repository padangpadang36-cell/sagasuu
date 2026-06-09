# -*- coding: utf-8 -*-
"""リアプロ: キーワード検索→建物一覧→空室→詳細→図面ボタンを完全把握"""
import sys, io, asyncio
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

OUT_DIR = Path(__file__).parent / "デバッグ" / "reabro4"
OUT_DIR.mkdir(parents=True, exist_ok=True)

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, channel="chrome", slow_mo=200)
        ctx = await browser.new_context(viewport={"width":1280,"height":900}, locale="ja-JP",
                                        accept_downloads=True)
        page = await ctx.new_page()

        # ログイン
        await page.goto(REABRO_BASE_URL + "/index.php", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)
        await page.locator('input[name="id"]').fill(REABRO_ID)
        await page.locator('input[name="pass"]').fill(REABRO_PASS)
        await page.locator('button:has-text("ログイン")').first.click()
        await asyncio.sleep(3)

        # ─── 建物リスト（フィルタなし）へ ───
        list_url = REABRO_BASE_URL + "/main.php?method=estate&display=building"
        await page.goto(list_url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)

        # キーワード検索フィールドに大阪市北区を入力して検索
        try:
            kw = page.locator('input[name="keyword"]').first
            if await kw.is_visible(timeout=2000):
                await kw.fill("大阪市北区")
                print("keyword='大阪市北区'入力")
                # Enterキー or 検索ボタン
                await kw.press("Enter")
                await asyncio.sleep(4)
                print(f"検索後URL: {page.url}")
        except Exception as e:
            print(f"keyword検索失敗: {e}")

        await page.screenshot(path=str(OUT_DIR / "01_search_result.png"))

        # HTMLを保存
        html = await page.content()
        with open(str(OUT_DIR / "search_result.html"), "w", encoding="utf-8") as f:
            f.write(html)
        print(f"HTML保存完了")

        # ページ内の全リンク（href付き）を取得
        print("\n=== ページ内リンク（最初50件）===")
        links = await page.evaluate("""
            () => Array.from(document.querySelectorAll('a[href]'))
                .map(a => ({
                    text: a.innerText.trim().replace(/\\s+/g,' ').substring(0,40),
                    href: a.href
                }))
                .filter(x => x.text || x.href)
                .slice(0, 60)
        """)
        for l in links:
            print(f"  [{l['text']}] {l['href']}")

        # 「空室」を含む全要素
        print("\n=== 空室関連の全要素 ===")
        kuushitsu_els = await page.evaluate("""
            () => {
                const results = [];
                for (const el of document.querySelectorAll('*')) {
                    const t = (el.innerText||'').trim();
                    if (t === '空室検索' || t === '空室一覧ダウンロード(PDF)') {
                        if (!results.find(r => r.text === t && r.id === el.id)) {
                            results.push({
                                tag: el.tagName,
                                text: t,
                                id: el.id||'',
                                cls: el.className.substring(0,60),
                                href: el.href||'',
                                onclick: (el.getAttribute('onclick')||'').substring(0,100),
                                'data-id': el.getAttribute('data-id')||''
                            });
                        }
                    }
                }
                return results.slice(0, 20);
            }
        """)
        for e in kuushitsu_els:
            print(f"  tag={e['tag']} id={e['id']} text='{e['text']}'")
            print(f"    cls={e['cls']}")
            print(f"    href={e['href']} onclick={e['onclick']} data-id={e['data-id']}")

        # ページテキスト先頭1000文字
        body_text = await page.evaluate("() => document.body.innerText.substring(0,1000)")
        print(f"\nページテキスト:\n{body_text}")

        # ─── 1つ目の建物ページへ直接移動（building_detail） ───
        print("\n=== building_detailリンクを探す ===")
        bld_links = await page.evaluate("""
            () => Array.from(document.querySelectorAll('a[href*="building_detail"], a[href*="building"]'))
                .slice(0, 5)
                .map(a => ({text: a.innerText.trim().substring(0,30), href: a.href}))
        """)
        for b in bld_links:
            print(f"  [{b['text']}] {b['href']}")

        # 1件目の建物ページを開く
        if bld_links:
            print(f"\n  建物詳細: {bld_links[0]['href']}")
            await page.goto(bld_links[0]['href'], wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(2)
            await page.screenshot(path=str(OUT_DIR / "02_building_detail.png"))

            # room_detailリンクを探す
            room_links = await page.evaluate("""
                () => Array.from(document.querySelectorAll('a[href*="room_detail"]'))
                    .slice(0, 5)
                    .map(a => ({text: a.innerText.trim().substring(0,30), href: a.href}))
            """)
            print(f"\n  room_detailリンク: {len(room_links)}件")
            for r in room_links:
                print(f"    [{r['text']}] {r['href']}")

            # room_detailの1件目を開く
            if room_links:
                await page.goto(room_links[0]['href'], wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(2)
                await page.screenshot(path=str(OUT_DIR / "03_room_detail.png"))
                print(f"\n  room_detail URL: {page.url}")

                # 全リンク＋ボタンを出力
                print("\n=== room_detail内の全要素 ===")
                all_btns = await page.evaluate("""
                    () => Array.from(document.querySelectorAll('a, button'))
                        .map(el => ({
                            text: el.innerText.trim().replace(/\\s+/g,' ').substring(0,50),
                            href: el.href||'',
                            onclick: (el.getAttribute('onclick')||'').substring(0,100),
                            cls: el.className.substring(0,60)
                        }))
                        .filter(x => x.text)
                """)
                for b in all_btns:
                    print(f"  [{b['text']}] href={b['href'][:70]} onclick={b['onclick']}")

                # HTMLも保存
                html2 = await page.content()
                with open(str(OUT_DIR / "room_detail.html"), "w", encoding="utf-8") as f:
                    f.write(html2)
                print(f"\nroom_detail HTML保存")

                # factsheet.phpリンクを探す
                fs_links = await page.evaluate("""
                    () => Array.from(document.querySelectorAll('a[href*="factsheet"], a[href*="pdf"]'))
                        .map(a => ({text: a.innerText.trim().substring(0,40), href: a.href}))
                """)
                print(f"\n=== factsheet/PDFリンク ===")
                for f in fs_links:
                    print(f"  [{f['text']}] {f['href']}")

                # org=2のリンクも探す
                org_links = await page.evaluate("""
                    () => Array.from(document.querySelectorAll('a[href*="org"]'))
                        .map(a => ({text: a.innerText.trim().substring(0,40), href: a.href}))
                """)
                if org_links:
                    print(f"\n=== org=2リンク ===")
                    for o in org_links:
                        print(f"  [{o['text']}] {o['href']}")

        # ─── メインページの「空室検索」ボタンを数値IDで辿る ───
        print("\n\n=== メインページに戻って空室検索ボタンを試す ===")
        await page.goto(REABRO_BASE_URL + "/main.php", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)

        # 数値IDのボタンを探す
        numeric_btns = await page.evaluate("""
            () => {
                const results = [];
                for (const el of document.querySelectorAll('[id]')) {
                    if (/^\\d{3,6}$/.test(el.id)) {
                        const t = el.innerText.trim().replace(/\\s+/g,' ').substring(0,30);
                        if (t) results.push({ id: el.id, tag: el.tagName, text: t,
                            onclick: (el.getAttribute('onclick')||'').substring(0,80)});
                    }
                }
                return results.slice(0, 10);
            }
        """)
        print(f"数値IDボタン: {len(numeric_btns)}件")
        for b in numeric_btns:
            print(f"  id={b['id']} [{b['text']}] onclick={b['onclick']}")

        if numeric_btns:
            bld_id = numeric_btns[0]['id']
            print(f"\n  id={bld_id}をクリック...")
            await page.locator(f'[id="{bld_id}"]').click()
            await asyncio.sleep(3)
            print(f"  クリック後URL: {page.url}")
            await page.screenshot(path=str(OUT_DIR / "04_after_kuushitsu.png"))

            # 現れたページのリンクを確認
            new_links = await page.evaluate("""
                () => Array.from(document.querySelectorAll('a[href*="room_detail"], a[href*="detail"]'))
                    .slice(0, 5)
                    .map(a => ({text: a.innerText.trim().substring(0,30), href: a.href}))
            """)
            print(f"  room_detailリンク: {len(new_links)}件")
            for r in new_links:
                print(f"    [{r['text']}] {r['href']}")

            if new_links:
                await page.goto(new_links[0]['href'], wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(2)
                await page.screenshot(path=str(OUT_DIR / "05_room_from_main.png"))
                print(f"\n  room URL: {page.url}")

                # 図面系ボタン確認
                all_links = await page.evaluate("""
                    () => Array.from(document.querySelectorAll('a, button'))
                        .map(el => ({
                            text: el.innerText.trim().replace(/\\s+/g,' ').substring(0,50),
                            href: el.href||'',
                            onclick: (el.getAttribute('onclick')||'').substring(0,80)
                        })).filter(x => x.text)
                """)
                print("\n=== room_detail 全ボタン ===")
                for b in all_links:
                    print(f"  [{b['text']}] href={b['href'][:70]}")

        print("\n=== 完了 ===")
        await browser.close()

asyncio.run(main())
