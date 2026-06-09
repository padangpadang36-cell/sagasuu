# -*- coding: utf-8 -*-
"""東建ルームサーチ 物件詳細ページのPDFリンク構造を調査"""
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

# 既知の詳細URL（大阪市北区 サウスガーデンレジデンス 1002号室）
DETAIL_URL = "https://www.homemate.co.jp/hmroom/dtl.asp?bn=7014316101002"

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
            await browser.close()
            return

        # 詳細ページへ遷移
        await page.goto(DETAIL_URL, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)
        await page.screenshot(path=str(OUT_DIR / "detail_page.png"))
        print(f"詳細URL: {page.url}")

        # HTML保存
        html = await page.content()
        (OUT_DIR / "detail_page.html").write_text(html, encoding='utf-8', errors='replace')

        # ページテキスト
        body_text = await page.evaluate("() => document.body.innerText")
        print(f"\nページテキスト(先頭2000文字):\n{body_text[:2000]}")

        # すべてのリンクを調査
        link_info = await page.evaluate("""
            () => {
                const links = Array.from(document.querySelectorAll('a'));
                return links.map(a => ({
                    text: a.textContent.trim().substring(0, 50),
                    href: a.href,
                    onclick: a.getAttribute('onclick') || ''
                })).filter(l => l.text || l.href);
            }
        """)
        print(f"\n=== 全リンク ({len(link_info)}件) ===")
        for l in link_info:
            if any(kw in (l['text']+l['href']+l['onclick']).lower()
                   for kw in ['pdf', '詳細', '印刷', 'print', 'download']):
                print(f"  *** {l['text']} → {l['href']} [onclick={l['onclick'][:50]}]")
            else:
                print(f"  {l['text'][:30]} → {l['href'][:60]}")

        # ボタンも確認
        btn_info = await page.evaluate("""
            () => {
                const btns = Array.from(document.querySelectorAll('button, input[type="button"], input[type="submit"]'));
                return btns.map(b => ({
                    text: b.textContent.trim() || b.value || '',
                    type: b.type,
                    onclick: b.getAttribute('onclick') || ''
                }));
            }
        """)
        print(f"\n=== ボタン ({len(btn_info)}件) ===")
        for b in btn_info:
            print(f"  [{b['type']}] {b['text']} [onclick={b['onclick'][:60]}]")

        input("\n[確認] Enterで終了...")
        await browser.close()

asyncio.run(main())
