# -*- coding: utf-8 -*-
"""リアプロ: 客付け資料・元付け資料リンクのURLを取得してPDFをダウンロード"""
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

OUT_DIR = Path(__file__).parent / "デバッグ" / "reabro5"
OUT_DIR.mkdir(parents=True, exist_ok=True)

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, channel="chrome", slow_mo=200)
        ctx = await browser.new_context(viewport={"width":1280,"height":900}, locale="ja-JP",
                                        accept_downloads=True)
        page = await ctx.new_page()

        # ネットワーク監視
        net_log = []
        page.on("request",  lambda r: net_log.append(("REQ", r.method, r.url)))
        page.on("response", lambda r: net_log.append(("RES", r.status,
            r.headers.get("content-type",""), r.url)))

        # ログイン
        await page.goto(REABRO_BASE_URL + "/index.php", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)
        await page.locator('input[name="id"]').fill(REABRO_ID)
        await page.locator('input[name="pass"]').fill(REABRO_PASS)
        await page.locator('button:has-text("ログイン")').first.click()
        await asyncio.sleep(3)
        net_log.clear()

        # ─── 建物リストへ（キーワード検索） ───
        list_url = REABRO_BASE_URL + "/main.php?method=estate&display=building"
        await page.goto(list_url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)

        # キーワード入力→Enter
        kw = page.locator('input[name="keyword"]').first
        await kw.fill("大阪市北区")
        await asyncio.sleep(1)
        await kw.press("Enter")
        await asyncio.sleep(4)
        await page.screenshot(path=str(OUT_DIR / "01_search.png"))

        # AJAXで動的ロードを待つ（スクロール）
        await page.evaluate("window.scrollTo(0, 300)")
        await asyncio.sleep(2)
        await page.screenshot(path=str(OUT_DIR / "02_scrolled.png"))

        # ─── 資料リンクを全て取得（JS evaluate）───
        print("=== 資料リンク（JavaScript評価）===")
        sheet_links = await page.evaluate("""
            () => {
                const results = [];
                for (const a of document.querySelectorAll('a')) {
                    const t = a.innerText.trim().replace(/\\s+/g,' ');
                    if (t.match(/客付け|元付け|資料|factsheet/)) {
                        // onclick の内容を取得
                        const handlers = [];
                        // jQuery events
                        try {
                            const ev = jQuery._data(a, 'events');
                            if (ev && ev.click) {
                                for (const h of ev.click) {
                                    handlers.push(h.handler.toString().substring(0,150));
                                }
                            }
                        } catch(e) {}
                        results.push({
                            text: t.substring(0,40),
                            href: a.href,
                            onclick: (a.getAttribute('onclick')||''),
                            cls: a.className.substring(0,60),
                            'data-params': JSON.stringify(Object.fromEntries(
                                Array.from(a.attributes).map(attr => [attr.name, attr.value])
                            )).substring(0,200),
                            handlers: handlers
                        });
                    }
                }
                return results.slice(0, 20);
            }
        """)
        for s in sheet_links:
            print(f"\n  [{s['text']}]")
            print(f"    href: {s['href']}")
            print(f"    onclick: {s['onclick']}")
            print(f"    cls: {s['cls']}")
            print(f"    attrs: {s['data-params']}")
            if s['handlers']:
                print(f"    handlers: {s['handlers']}")

        # ─── 「元付け資料」をクリックしてネットワーク監視 ───
        net_log.clear()
        print("\n=== 元付け資料をクリック ===")
        try:
            async with page.expect_download(timeout=10000) as dl_info:
                await page.get_by_text("元付け資料", exact=True).first.click()
            dl = await dl_info.value
            fname = dl.suggested_filename or "mototsuke.pdf"
            save_path = str(OUT_DIR / fname)
            await dl.save_as(save_path)
            print(f"  ✓ ダウンロード: {fname}")
        except Exception as e:
            print(f"  DLなし ({type(e).__name__}): {e}")
            await asyncio.sleep(3)

        # ネットワークログ
        print("  ネットワーク（リクエスト）:")
        for entry in net_log:
            if entry[0] == "REQ":
                print(f"    {entry[1]} {entry[2][:120]}")
            elif entry[0] == "RES" and (entry[1] in [200, 302] or 'pdf' in str(entry[2]).lower()):
                print(f"    RES[{entry[1]}] ct={entry[2][:50]} {entry[3][:100]}")

        await page.screenshot(path=str(OUT_DIR / "03_after_mototsuke.png"))

        # 新しいタブが開いたか確認
        print(f"\n  タブ数: {len(ctx.pages)}")
        for i, p in enumerate(ctx.pages):
            print(f"    tab{i}: {p.url}")
            if i > 0:
                try:
                    btext = await p.evaluate("() => document.body.innerText.substring(0,200)")
                    print(f"    text: {btext}")
                    await p.screenshot(path=str(OUT_DIR / f"tab{i}.png"))
                except Exception:
                    pass

        # ─── 「客付け＋元付け資料」をクリック ───
        net_log.clear()
        print("\n=== 客付け＋元付け資料をクリック ===")
        try:
            async with page.expect_download(timeout=10000) as dl_info:
                await page.get_by_text("客付け＋元付け資料", exact=True).first.click()
            dl = await dl_info.value
            fname = dl.suggested_filename or "kyakutsuke_mototsuke.pdf"
            await dl.save_as(str(OUT_DIR / fname))
            print(f"  ✓ ダウンロード: {fname}")
        except Exception as e:
            print(f"  DLなし ({type(e).__name__}): {e}")
            await asyncio.sleep(2)
        print("  ネットワーク（PDF関連）:")
        for entry in net_log:
            if 'pdf' in str(entry).lower() or 'factsheet' in str(entry).lower() or 'bridge' in str(entry).lower():
                print(f"    {entry}")

        # ─── 「詳細」リンクをクリックして room_detail を確認 ───
        print("\n=== 詳細リンクをクリック ===")
        net_log.clear()
        try:
            detail_link = page.get_by_text("詳細", exact=True).first
            href = await detail_link.get_attribute("href")
            print(f"  詳細href: {href}")
            await detail_link.click()
            await asyncio.sleep(3)
            print(f"  クリック後URL: {page.url}")
            await page.screenshot(path=str(OUT_DIR / "04_detail.png"))

            # room_detail リンク確認
            room_links = await page.evaluate("""
                () => Array.from(document.querySelectorAll('a'))
                    .filter(a => a.href.includes('room_detail') || a.href.includes('detail'))
                    .slice(0, 5)
                    .map(a => ({text: a.innerText.trim().substring(0,30), href: a.href}))
            """)
            print(f"  詳細ページ内のroom_detailリンク: {len(room_links)}件")
            for r in room_links:
                print(f"    [{r['text']}] {r['href']}")

            # 全リンク・ボタン
            all_els = await page.evaluate("""
                () => Array.from(document.querySelectorAll('a, button'))
                    .filter(el => el.offsetParent !== null)
                    .map(el => ({
                        text: el.innerText.trim().replace(/\\s+/g,' ').substring(0,40),
                        href: el.href||'',
                        onclick: (el.getAttribute('onclick')||'').substring(0,80)
                    }))
                    .filter(x => x.text)
            """)
            print(f"\n  詳細ページのボタン・リンク:")
            for e in all_els:
                print(f"    [{e['text']}] href={e['href'][:70]} onclick={e['onclick']}")

        except Exception as e:
            print(f"  詳細クリックエラー: {e}")

        # ─── ネットワークログ全体 ───
        print("\n=== 全ネットワークログ（重要部分） ===")
        for entry in net_log:
            url = str(entry[-1])
            if any(k in url.lower() for k in ['pdf', 'factsheet', 'detail', 'bridge', 'sheet']):
                print(f"  {entry[0]} {entry[1] if len(entry)>1 else ''} {url[:100]}")

        print("\n=== 完了 ===")
        await browser.close()

asyncio.run(main())
