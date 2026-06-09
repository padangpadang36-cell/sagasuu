# -*- coding: utf-8 -*-
"""ATBB インフォシートの編集メニュー（社宅.com版作成）を調査"""
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

OUT_DIR = Path(__file__).parent / "デバッグ" / "atbb_edit"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 直前のデモで取得したインフォシートURL（１件目）
INFOSHEET_URL = "https://zmn.atbb.athome.co.jp/infosheets/7103062bb2a5fab01f4cfb225df5c6c955c8ed5"

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, channel="chrome", slow_mo=300)
        ctx = await browser.new_context(viewport={"width":1280,"height":900}, locale="ja-JP",
                                        accept_downloads=True)
        page = await ctx.new_page()

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

        # ─── インフォシートページへ ───
        print(f"\nインフォシートURL: {INFOSHEET_URL}")
        await page.goto(INFOSHEET_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        print(f"インフォシートURL実際: {page.url}")
        await page.screenshot(path=str(OUT_DIR / "01_infosheet.png"))

        # ─── ページ上の全ボタン・リンクを調査 ───
        print("\n=== インフォシートページの全操作要素 ===")
        all_els = await page.evaluate("""
            () => {
                const results = [];
                for (const el of document.querySelectorAll('a, button, input[type="button"], input[type="submit"], [onclick]')) {
                    const t = (el.innerText||el.value||el.textContent||'').trim().replace(/\\s+/g,' ').substring(0,50);
                    if (!t) continue;
                    results.push({
                        tag: el.tagName,
                        text: t,
                        id: el.id || '',
                        cls: el.className.substring(0,50),
                        href: el.href || '',
                        onclick: (el.getAttribute('onclick')||'').substring(0,100)
                    });
                }
                return results;
            }
        """)
        for el in all_els:
            print(f"  [{el['text']}] tag={el['tag']} id={el['id']} cls={el['cls']}")
            if el['onclick']:
                print(f"      onclick={el['onclick']}")
            if el['href']:
                print(f"      href={el['href'][:80]}")

        # ─── 「編集メニュー」「編集」などを探してクリック ───
        print("\n=== 編集メニューを探す ===")
        for label in ["編集メニュー", "編集", "メニュー", "一般向け", "客付け"]:
            try:
                el = page.get_by_text(label, exact=False).first
                if await el.is_visible(timeout=1000):
                    print(f"  発見: '{label}'")
                    break
            except Exception:
                continue

        # 編集メニュークリック
        edit_clicked = False
        for label in ["編集メニュー", "編集"]:
            try:
                btn = page.get_by_text(label, exact=False).first
                if await btn.is_visible(timeout=1000):
                    await btn.click()
                    await asyncio.sleep(2)
                    print(f"  '{label}'クリック後")
                    await page.screenshot(path=str(OUT_DIR / "02_after_edit_click.png"))
                    edit_clicked = True
                    break
            except Exception:
                continue

        if edit_clicked:
            # クリック後に現れた要素を確認
            print("\n=== 編集メニュー後の要素 ===")
            after_els = await page.evaluate("""
                () => Array.from(document.querySelectorAll('a, button, input, label, li'))
                    .filter(el => el.offsetParent !== null)  // visible only
                    .map(el => ({
                        tag: el.tagName,
                        text: (el.innerText||el.value||'').trim().replace(/\\s+/g,' ').substring(0,50),
                        id: el.id||'',
                        cls: el.className.substring(0,60),
                        type: el.type||''
                    }))
                    .filter(x => x.text)
            """)
            for el in after_els:
                if any(k in el['text'] for k in ['一般', '客付', '手数料', '出力', 'PDF', '印刷', 'ダウンロード']):
                    print(f"  ★ [{el['text']}] tag={el['tag']} id={el['id']} cls={el['cls']}")
                else:
                    print(f"    [{el['text']}]")

            # 「一般向け」を探してクリック
            for label in ["一般向け", "一般"]:
                try:
                    el = page.get_by_text(label, exact=False).first
                    if await el.is_visible(timeout=1000):
                        await el.click()
                        await asyncio.sleep(1)
                        print(f"\n  '{label}'クリック")
                        break
                except Exception:
                    continue

            # 「客付け手数料を表示しない」を探してクリック
            for label in ["客付け手数料を表示しない", "客付け", "手数料"]:
                try:
                    el = page.get_by_text(label, exact=False).first
                    if await el.is_visible(timeout=1000):
                        await el.click()
                        await asyncio.sleep(1)
                        print(f"  '{label}'クリック")
                        break
                except Exception:
                    continue

            await page.screenshot(path=str(OUT_DIR / "03_after_options.png"))

            # 出力/PDF保存ボタンを探す
            print("\n=== 出力ボタンを探す ===")
            for label in ["出力", "PDF", "保存", "ダウンロード", "印刷"]:
                try:
                    btn = page.get_by_text(label, exact=False).first
                    if await btn.is_visible(timeout=1000):
                        print(f"  発見: '{label}'")
                except Exception:
                    continue

        # ─── PDF出力を試す（印刷ダイアログをキャンセルしてURLを確認） ───
        print("\n=== PDF関連URLを確認 ===")
        net_reqs = []
        page.on("request", lambda r: net_reqs.append(f"{r.method} {r.url[:100]}"))
        # print ダイアログをキャプチャ
        page.on("dialog", lambda d: asyncio.ensure_future(d.dismiss()))

        # ページのPDF出力ボタンを全て試す
        for label in ["PDF出力", "出力", "PDFダウンロード", "印刷・PDF"]:
            try:
                btn = page.get_by_text(label, exact=False).first
                if await btn.is_visible(timeout=500):
                    print(f"  '{label}'ボタンをクリック")
                    try:
                        async with page.expect_download(timeout=5000) as dl_info:
                            await btn.click()
                        dl = await dl_info.value
                        fname = dl.suggested_filename or "infosheet.pdf"
                        await dl.save_as(str(OUT_DIR / fname))
                        print(f"  ✓ DL: {fname}")
                    except Exception as e:
                        print(f"  DLなし: {e}")
                    await asyncio.sleep(2)
                    break
            except Exception:
                continue

        # ネットワークログ
        print(f"\nネットワークリクエスト（最後10件）:")
        for r in net_reqs[-10:]:
            print(f"  {r}")

        # ─── ページのHTMLを保存して構造を確認 ───
        html = await page.content()
        with open(str(OUT_DIR / "infosheet.html"), "w", encoding="utf-8") as f:
            f.write(html)
        print(f"\nHTML保存: {OUT_DIR}/infosheet.html")

        print("\n=== 完了 ===")
        await browser.close()

asyncio.run(main())
