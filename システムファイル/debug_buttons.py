# -*- coding: utf-8 -*-
"""ATBBの検索結果ページのボタン・リンク構造を調べるデバッグスクリプト"""
import sys, io, asyncio, json
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

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, channel="chrome", slow_mo=400)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 900}, locale="ja-JP")
        page = await ctx.new_page()

        # ログイン
        await page.goto(ATBB_URL, wait_until="domcontentloaded", timeout=30000)
        await page.locator('input[name="loginId"]').fill(ATBB_ID)
        await page.locator('input[type="password"]').fill(ATBB_PASS)
        await page.locator('input[type="submit"]').click()
        await page.wait_for_load_state("networkidle", timeout=20000)
        print(f"ログイン後: {page.url}")

        # 物件検索ページへ
        el = page.locator('a:has-text("物件・会社検索")').first
        await el.click()
        await asyncio.sleep(1)

        import re as _re
        async with ctx.expect_page(timeout=5000) as np_info:
            await page.get_by_text("流通物件検索").first.click()
        new_page = await np_info.value
        await new_page.wait_for_load_state("domcontentloaded", timeout=15000)
        await asyncio.sleep(2)

        # ConcurrentLoginException 対応
        if "ConcurrentLoginException" in new_page.url:
            force_info = await new_page.evaluate("() => { const f=document.querySelector('form'); return f ? {action:f.action} : null; }")
            sid = _re.search(r'jsessionid=([A-Fa-f0-9]+)', new_page.url)
            action = force_info['action']
            if sid and 'jsessionid' not in action:
                action += f';jsessionid={sid.group(1)}'
            await new_page.goto(action, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(4)

        # 賃貸居住用を選択して検索
        await new_page.locator('input[name="atbbShumokuDaibunrui"][value="06"]').click()
        fw = new_page.locator('input[name*="freeword"], input[name*="freeWord"]').first
        await fw.fill("大阪市北区 8万円以下")
        await new_page.locator('input[value="検索"]').last.click()
        await asyncio.sleep(4)
        await new_page.wait_for_load_state("domcontentloaded", timeout=20000)
        await asyncio.sleep(2)
        print(f"検索結果URL: {new_page.url}")

        # ページのボタン・リンク・フォーム情報を取得
        result = await new_page.evaluate("""
            () => {
                const info = {};

                // すべてのinput[type=button/submit/image]
                info.inputs = Array.from(document.querySelectorAll('input[type=button],input[type=submit],input[type=image]'))
                    .map(el => ({tag:'input', type:el.type, id:el.id, name:el.name, value:el.value, class:el.className}))
                    .slice(0,30);

                // ボタン要素
                info.buttons = Array.from(document.querySelectorAll('button'))
                    .map(el => ({tag:'button', id:el.id, name:el.name, text:el.textContent.trim().substring(0,30), class:el.className}))
                    .slice(0,20);

                // "詳細"を含むリンク・要素
                info.detail_links = Array.from(document.querySelectorAll('a'))
                    .filter(a => a.textContent.includes('詳細') || a.href.includes('detail') || a.href.includes('shosai'))
                    .map(a => ({text:a.textContent.trim().substring(0,30), href:a.href, id:a.id, class:a.className}))
                    .slice(0,10);

                // shosaiを含む要素
                info.shosai_els = Array.from(document.querySelectorAll('[id*=shosai],[name*=shosai],[class*=shosai],[onclick*=shosai]'))
                    .map(el => ({tag:el.tagName, id:el.id, class:el.className, onclick:el.getAttribute('onclick'), href:el.href||''}))
                    .slice(0,10);

                // onclick属性を持つ要素のうち "bukken" や "detail" を含むもの
                info.onclick_els = Array.from(document.querySelectorAll('[onclick]'))
                    .filter(el => {
                        const oc = el.getAttribute('onclick') || '';
                        return oc.includes('detail') || oc.includes('bukken') || oc.includes('shosai') || oc.includes('open');
                    })
                    .map(el => ({tag:el.tagName, id:el.id, onclick:el.getAttribute('onclick').substring(0,80)}))
                    .slice(0,10);

                return info;
            }
        """)

        out = Path(__file__).parent / "デバッグ" / "button_structure.json"
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"保存: {out}")
        print(json.dumps(result, ensure_ascii=False, indent=2))

        await browser.close()

asyncio.run(main())
