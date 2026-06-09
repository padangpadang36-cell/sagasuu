# -*- coding: utf-8 -*-
"""
リアプロで都道府県を手動で切り替えたときのネットワークリクエストを傍受して
AJAX呼び出しのURLとパラメータを記録する。
"""
import sys, io, asyncio, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")
REABRO_LOGIN_URL = 'https://www.realnetpro.com/index.php'
REABRO_BASE_URL  = 'https://www.realnetpro.com'
REABRO_ID   = os.getenv("REABRO_ID", "")
REABRO_PASS = os.getenv("REABRO_PASS", "")
SHOT = Path(__file__).parent / 'デバッグ' / 'screenshots'


async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, slow_mo=500, channel='chrome')
        ctx = await browser.new_context(viewport={'width': 1280, 'height': 900}, locale='ja-JP')
        page = await ctx.new_page()

        # ネットワークリクエストを傍受
        requests_log = []

        def on_request(req):
            url = req.url
            if 'realnetpro' in url and req.method in ('GET', 'POST'):
                skip = ('.css', '.js', '.png', '.jpg', '.gif', '.woff', '.ico', '.svg')
                if not any(url.endswith(s) for s in skip):
                    body = ''
                    try:
                        body = req.post_data or ''
                    except Exception:
                        pass
                    requests_log.append({'method': req.method, 'url': url, 'body': body[:200]})

        page.on('request', on_request)

        # ── ログイン ──
        await page.goto(REABRO_LOGIN_URL, wait_until='domcontentloaded')
        await asyncio.sleep(2)
        await page.locator('input[name="id"]').fill(REABRO_ID)
        await page.locator('input[name="pass"]').fill(REABRO_PASS)
        await page.locator('button:has-text("ログイン")').first.click()
        await asyncio.sleep(3)

        # ── 建物一覧 ──
        requests_log.clear()
        await page.goto(REABRO_BASE_URL + '/main.php?method=estate&display=building',
                        wait_until='networkidle')
        await asyncio.sleep(3)

        # ── step1 パネルを表示 ──
        await page.evaluate("""
            (() => {
                const panel = document.querySelector('.step1.pref_select.detail_select_box');
                if (panel) panel.style.display = 'block';
                // step1_m も表示
                const m = document.querySelector('.step1_m');
                if (m) console.log('step1_m HTML:', m.innerHTML.substring(0, 300));
            })()
        """)
        await asyncio.sleep(0.5)
        await page.screenshot(path=str(SHOT / 'reabro_panel_open.png'))

        # ── 都道府県選択UIを探す ──
        # 「エリアから絞り込む」「都道府県」系のテキストを持つ要素を探す
        triggers = await page.evaluate("""
            (() => {
                const all = [];
                // クリック可能な全要素
                document.querySelectorAll('a, button, li, span, div').forEach(el => {
                    const txt = (el.innerText || '').trim();
                    if (txt.length > 0 && txt.length < 15 &&
                        (txt.includes('茨城') || txt.includes('都道府県') ||
                         txt.includes('エリア') || txt.includes('絞り込'))) {
                        const rect = el.getBoundingClientRect();
                        all.push({
                            tag: el.tagName, text: txt, cls: el.className.substring(0,30),
                            visible: rect.width > 0 && rect.height > 0,
                            x: Math.round(rect.x), y: Math.round(rect.y)
                        });
                    }
                });
                return all;
            })()
        """)
        print('=== エリア/都道府県 UI要素 ===')
        for t in triggers:
            print(' ', t)

        # 現在の step1_m の中身（都道府県選択UIがあるか）
        step1m_html = await page.evaluate("""
            (() => {
                const m = document.querySelector('.step1_m');
                return m ? m.innerHTML : 'なし';
            })()
        """)
        print('\n=== step1_m HTML ===')
        print(step1m_html[:3000])

        # ── search_pref 要素を探す ──
        search_pref = await page.evaluate("""
            (() => {
                const el = document.querySelector('.search_pref');
                if (!el) return 'なし';
                return {
                    html: el.outerHTML.substring(0, 1000),
                    visible: el.getBoundingClientRect().width > 0
                };
            })()
        """)
        print('\n=== search_pref ===')
        print(search_pref)

        await browser.close()


asyncio.run(main())
