# -*- coding: utf-8 -*-
"""東建ルームサーチのサイト構造調査スクリプト（ログイン修正版）"""
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

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, channel="chrome", slow_mo=500)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 900}, locale="ja-JP")
        page = await ctx.new_page()

        # ── 1. トップページ ──
        await page.goto(HM_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)
        await page.screenshot(path=str(OUT_DIR / "01_top.png"))
        print(f"トップURL: {page.url}")

        # ── 2. ログイン ──
        print("\nログイン試行...")
        await page.locator('input[name="id"]').fill(HM_ID)
        await page.locator('input[name="pw"]').fill(HM_PASS)
        await page.screenshot(path=str(OUT_DIR / "02_form_filled.png"))

        # ログインボタンは javascript:getLogin() - #btn_login a をクリック
        await page.locator('#btn_login a').click()
        print("  ログインボタンクリック: #btn_login a")

        try:
            await page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass
        await asyncio.sleep(3)
        await page.screenshot(path=str(OUT_DIR / "03_after_login.png"))
        print(f"\nログイン後URL: {page.url}")

        # ページ全文
        body_text = await page.evaluate("() => document.body.innerText.substring(0, 2000)")
        print(f"\nページ内容(先頭2000字):\n{body_text}")

        # HTMLを保存
        html = await page.content()
        (OUT_DIR / "03_after_login.html").write_text(html, encoding='utf-8', errors='replace')
        print(f"\nHTML保存: {OUT_DIR / '03_after_login.html'}")

        # ── 3. リンク一覧 ──
        links = await page.evaluate("""
            () => Array.from(document.querySelectorAll('a'))
                .map(a => ({text: a.textContent.trim().substring(0,40), href: a.href}))
                .filter(a => a.text || a.href)
                .slice(0, 40)
        """)
        print("\nリンク一覧:")
        for lnk in links:
            print(f"  {lnk['text']} → {lnk['href']}")

        # ── 4. 空室検索リンクを探す ──
        search_keywords = ["空室検索", "物件検索", "検索", "search"]
        for kw in search_keywords:
            try:
                el = page.locator(f'a:has-text("{kw}"), button:has-text("{kw}")').first
                if await el.is_visible(timeout=1000):
                    href = await el.get_attribute("href") or ""
                    print(f"\n検索リンク発見: {kw} → {href}")
                    await el.click()
                    await asyncio.sleep(3)
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=10000)
                    except Exception:
                        pass
                    await asyncio.sleep(2)
                    await page.screenshot(path=str(OUT_DIR / "04_search_page.png"))
                    print(f"検索ページURL: {page.url}")

                    # 検索フォーム要素を取得
                    form_els = await page.evaluate("""
                        () => Array.from(document.querySelectorAll('input,select,textarea'))
                            .map(el => ({tag:el.tagName, type:el.type||'', name:el.name||'',
                                         id:el.id||'', placeholder:el.placeholder||'',
                                         value:el.value||'', options: el.tagName==='SELECT'
                                            ? Array.from(el.options).map(o=>({v:o.value,t:o.text})).slice(0,20)
                                            : []}))
                    """)
                    print(f"\n検索フォーム要素 ({len(form_els)}件):")
                    for el2 in form_els:
                        print(f"  {el2}")

                    html2 = await page.content()
                    (OUT_DIR / "04_search_page.html").write_text(html2, encoding='utf-8', errors='replace')
                    print(f"\n検索ページHTML保存: {OUT_DIR / '04_search_page.html'}")
                    break
            except Exception as e:
                print(f"  {kw}: {e}")
                continue

        input("\n[確認] ブラウザを確認したらEnterで終了...")
        await browser.close()

asyncio.run(main())
