# -*- coding: utf-8 -*-
"""東建ルームサーチのサイト構造調査スクリプト"""
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

        # フォームの input 要素を全取得
        inputs = await page.evaluate("""
            () => Array.from(document.querySelectorAll('input,select,textarea'))
                .map(el => ({tag:el.tagName, type:el.type||'', name:el.name||'',
                             id:el.id||'', placeholder:el.placeholder||'', value:el.value||''}))
        """)
        print("\\nフォーム要素:")
        for inp in inputs:
            print(f"  {inp}")

        # ── 2. ログイン試行 ──
        print("\\nログイン試行...")
        # ID入力
        for sel in ['input[name="id"]','input[name="userId"]','input[name="login_id"]',
                    'input[id*="id"]','input[type="text"]']:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=1500):
                    await el.fill(HM_ID)
                    print(f"  ID入力: {sel}")
                    break
            except Exception:
                continue

        # PASS入力
        for sel in ['input[type="password"]']:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=1500):
                    await el.fill(HM_PASS)
                    print(f"  PASS入力: {sel}")
                    break
            except Exception:
                continue

        await page.screenshot(path=str(OUT_DIR / "02_form_filled.png"))

        # ログインボタン
        for sel in ['button[type="submit"]','input[type="submit"]',
                    'button:has-text("ログイン")','input[value*="ログイン"]',
                    'a:has-text("ログイン")']:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=1500):
                    await el.click()
                    print(f"  ログインボタン: {sel}")
                    break
            except Exception:
                continue

        try:
            await page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass
        await asyncio.sleep(3)
        await page.screenshot(path=str(OUT_DIR / "03_after_login.png"))
        print(f"\\nログイン後URL: {page.url}")

        # ── 3. ログイン後のページ構造 ──
        links = await page.evaluate("""
            () => Array.from(document.querySelectorAll('a'))
                .map(a => ({text: a.textContent.trim().substring(0,30), href: a.href}))
                .filter(a => a.text)
                .slice(0, 30)
        """)
        print("\\nリンク一覧:")
        for lnk in links:
            print(f"  {lnk['text']} → {lnk['href']}")

        # ページ全文
        body_text = await page.evaluate("() => document.body.innerText.substring(0, 1000)")
        print(f"\\nページ内容(先頭1000字):\\n{body_text}")

        # HTMLを保存
        html = await page.content()
        (OUT_DIR / "03_after_login.html").write_text(html, encoding='utf-8', errors='replace')
        print(f"\\nHTML保存: {OUT_DIR / '03_after_login.html'}")

        # ── 4. 検索画面を探す ──
        search_keywords = ["物件検索", "空室検索", "賃貸", "検索", "search"]
        for kw in search_keywords:
            try:
                el = page.locator(f'a:has-text("{kw}"), button:has-text("{kw}")').first
                if await el.is_visible(timeout=1000):
                    print(f"\\n検索リンク発見: {kw}")
                    await el.click()
                    await asyncio.sleep(3)
                    await page.wait_for_load_state("domcontentloaded", timeout=10000)
                    await page.screenshot(path=str(OUT_DIR / "04_search_page.png"))
                    print(f"検索ページURL: {page.url}")
                    html2 = await page.content()
                    (OUT_DIR / "04_search_page.html").write_text(html2, encoding='utf-8', errors='replace')
                    break
            except Exception:
                continue

        input("\\n[確認] ブラウザを確認したらEnterで終了...")
        await browser.close()

asyncio.run(main())
