# -*- coding: utf-8 -*-
import sys, io, asyncio
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
        browser = await pw.chromium.launch(headless=False, slow_mo=300, channel='chrome')
        ctx = await browser.new_context(viewport={'width': 1280, 'height': 900}, locale='ja-JP')
        page = await ctx.new_page()

        # ── ログイン ──
        await page.goto(REABRO_LOGIN_URL, wait_until='domcontentloaded')
        await asyncio.sleep(2)
        await page.locator('input[name="id"]').fill(REABRO_ID)
        await page.locator('input[name="pass"]').fill(REABRO_PASS)
        await page.locator('button:has-text("ログイン")').first.click()
        await asyncio.sleep(3)
        print('ログイン後URL:', page.url)

        # ── 建物一覧 ──
        await page.goto(REABRO_BASE_URL + '/main.php?method=estate&display=building',
                        wait_until='networkidle')
        await asyncio.sleep(3)

        # ── step1 パネルを強制表示 + 茨城(08)チェック ──
        await page.evaluate("""
            (() => {
                const panel = document.querySelector('.step1.pref_select.detail_select_box');
                if (panel) panel.style.display = 'block';
                const cb = document.querySelector('input[name="pref_code"][value="08"]');
                if (cb) cb.click();
            })()
        """)
        await asyncio.sleep(4)
        await page.screenshot(path=str(SHOT / 'reabro_pref08_clicked.png'))
        print('茨城チェック完了')

        # ── 都市リスト確認 ──
        cities = await page.evaluate("""
            (() => {
                const all = Array.from(document.querySelectorAll('input[name="city_code[]"]'));
                return all.map(el => {
                    const lbl = el.parentElement ? el.parentElement.textContent.trim() : '';
                    return {value: el.value, label: lbl.substring(0, 15)};
                }).slice(0, 40);
            })()
        """)
        print('=== 都市リスト (最初40件) ===')
        for c in cities:
            print(' ', c)

        # ── かすみがうら市のラベルを探す ──
        kasumi = await page.evaluate("""
            (() => {
                const labels = Array.from(document.querySelectorAll('label'));
                const found = labels.filter(l => l.textContent.includes('かすみがうら'));
                return found.map(l => ({text: l.textContent.trim(), cls: l.className}));
            })()
        """)
        print('かすみがうら市ラベル:', kasumi)

        # ── かすみがうら市をクリック ──
        if kasumi:
            await page.evaluate("""
                (() => {
                    const labels = Array.from(document.querySelectorAll('label'));
                    const lbl = labels.find(l => l.textContent.includes('かすみがうら'));
                    if (lbl) lbl.click();
                })()
            """)
            await asyncio.sleep(1)
            print('かすみがうら市クリック完了')

        # ── 家賃上限 rental_cost2 = 70000 ──
        await page.select_option('select[name="rental_cost2"]', '70000')
        print('家賃上限: 7万円 設定完了')

        # ── 検索ボタン ──
        search_btn = page.locator('button:has-text("検索")').first
        await search_btn.click()
        try:
            await page.wait_for_load_state('networkidle', timeout=12000)
        except Exception:
            pass
        await asyncio.sleep(4)
        await page.screenshot(path=str(SHOT / 'reabro_kasumi_result.png'))
        print('検索後URL:', page.url)

        # ── 結果取得 ──
        rooms = await page.evaluate("""
            (() => {
                const results = [];
                document.querySelectorAll('.room_system_menu[title]').forEach(el => {
                    const t = el.getAttribute('title');
                    if (!t || !t.includes(',')) return;
                    const parts = t.split(',');
                    const id = parts[0].trim();
                    if (!id || !/^\\d+$/.test(id)) return;
                    results.push({room_id: id, name: (parts[1]||'').trim(), room: (parts[2]||'').trim()});
                });
                return results;
            })()
        """)
        print(f'=== 検索結果: {len(rooms)}件 ===')
        for r in rooms[:10]:
            print(' ', r)

        await browser.close()


asyncio.run(main())
