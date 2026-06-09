# -*- coding: utf-8 -*-
"""東建ルームサーチ 検索結果ページのテーブル構造を詳しく調査"""
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
# 前回の検索結果URL（大阪市北区）
RESULT_URL = "https://www.homemate.co.jp/hmroom/srch.asp?prf=27&stjiscd=27127&kt=01&jiscd=27127"

OUT_DIR = Path(__file__).parent / "デバッグ" / "homemate"
OUT_DIR.mkdir(parents=True, exist_ok=True)

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, channel="chrome", slow_mo=500)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 900}, locale="ja-JP")
        page = await ctx.new_page()

        # ログイン
        await page.goto(HM_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)
        await page.locator('input[name="id"]').fill(HM_ID)
        await page.locator('input[name="pw"]').fill(HM_PASS)
        await page.locator('#btn_login a').click()
        await page.wait_for_load_state("domcontentloaded", timeout=15000)
        await asyncio.sleep(3)
        print(f"ログイン後URL: {page.url}")

        if "top.asp" not in page.url:
            print("ログイン失敗")
            input("Enterで終了...")
            await browser.close()
            return

        # 検索結果URLへ直接遷移
        await page.goto(RESULT_URL, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)
        await page.screenshot(path=str(OUT_DIR / "result_page.png"))
        print(f"結果URL: {page.url}")

        # HTML保存
        html = await page.content()
        (OUT_DIR / "result_page.html").write_text(html, encoding='utf-8', errors='replace')
        print(f"HTML保存: {OUT_DIR / 'result_page.html'}")

        # ページテキスト全文
        body_text = await page.evaluate("() => document.body.innerText")
        print(f"\nページテキスト(全文):\n{body_text[:5000]}")
        (OUT_DIR / "result_text.txt").write_text(body_text, encoding='utf-8', errors='replace')

        # テーブル構造を詳しく調査
        table_data = await page.evaluate("""
            () => {
                const result = {};

                // すべてのテーブルとその行
                result.tables = Array.from(document.querySelectorAll('table')).map((t, ti) => ({
                    index: ti,
                    id: t.id, class: t.className,
                    rows: Array.from(t.rows).map((tr, ri) => ({
                        index: ri,
                        cells: Array.from(tr.cells).map(td => ({
                            text: td.textContent.trim().substring(0, 60),
                            tag: td.tagName,
                            class: td.className,
                            colspan: td.colSpan,
                            links: Array.from(td.querySelectorAll('a')).map(a => ({
                                text: a.textContent.trim().substring(0, 30),
                                href: a.href.substring(0, 100)
                            }))
                        }))
                    })).slice(0, 20)
                })).slice(0, 5);

                // クラス名に "bukken" "property" "item" を含む要素
                result.bukken_els = Array.from(document.querySelectorAll(
                    '[class*="bukken"],[class*="property"],[class*="item"],[class*="result"],[class*="list"]'
                )).map(el => ({
                    tag: el.tagName, class: el.className,
                    text: el.textContent.trim().substring(0, 100)
                })).slice(0, 10);

                // すべてのリンク
                result.links = Array.from(document.querySelectorAll('a'))
                    .filter(a => a.href && !a.href.startsWith('javascript'))
                    .map(a => ({text: a.textContent.trim().substring(0, 40), href: a.href}))
                    .slice(0, 20);

                // 画像
                result.images = Array.from(document.querySelectorAll('img'))
                    .filter(img => img.src && img.naturalWidth > 50)
                    .map(img => ({src: img.src.substring(0, 100), alt: img.alt, w: img.naturalWidth, h: img.naturalHeight}))
                    .slice(0, 10);

                return result;
            }
        """)

        out_json = OUT_DIR / "result_structure.json"
        out_json.write_text(json.dumps(table_data, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"\n構造JSON保存: {out_json}")

        print("\n=== テーブル構造 ===")
        for t in table_data.get('tables', []):
            print(f"\nTable[{t['index']}] id={t['id']} class={t['class']}")
            for row in t['rows'][:10]:
                print(f"  Row[{row['index']}]: {[c['text'] for c in row['cells']]}")
                for cell in row['cells']:
                    if cell['links']:
                        print(f"    Links: {cell['links']}")

        print("\n=== リンク ===")
        for lnk in table_data.get('links', []):
            print(f"  {lnk['text']} → {lnk['href']}")

        print("\n=== 画像 ===")
        for img in table_data.get('images', []):
            print(f"  {img['alt']} | {img['w']}x{img['h']} | {img['src']}")

        input("\n[確認] Enterで終了...")
        await browser.close()

asyncio.run(main())
