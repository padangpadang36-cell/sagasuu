# -*- coding: utf-8 -*-
"""
「所在地絞り込み ＋」をクリック → 茨城県選択 → かすみがうら市選択 → 検索
"""
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
        browser = await pw.chromium.launch(headless=False, slow_mo=500, channel='chrome')
        ctx = await browser.new_context(viewport={'width': 1280, 'height': 900}, locale='ja-JP')
        page = await ctx.new_page()

        # ── ログイン ──
        await page.goto(REABRO_LOGIN_URL, wait_until='domcontentloaded')
        await asyncio.sleep(2)
        await page.locator('input[name="id"]').fill(REABRO_ID)
        await page.locator('input[name="pass"]').fill(REABRO_PASS)
        await page.locator('button:has-text("ログイン")').first.click()
        await asyncio.sleep(3)

        # ── 建物一覧 ──
        await page.goto(REABRO_BASE_URL + '/main.php?method=estate&display=building',
                        wait_until='networkidle')
        await asyncio.sleep(3)
        await page.screenshot(path=str(SHOT / 'ra_01_default.png'))

        # ── Step1: 「所在地絞り込み ＋」をクリック ──
        slide_btn = page.locator('.one_slide_search_box .click_menu').first
        await slide_btn.click()
        await asyncio.sleep(2)
        await page.screenshot(path=str(SHOT / 'ra_02_area_open.png'))
        print('所在地パネル opened')

        # ── パネル内の都道府県チェックボックスを確認 ──
        pref_visible = await page.evaluate("""
            (() => {
                const cb = document.querySelector('input[name="pref_code"][value="08"]');
                if (!cb) return {found: false};
                const rect = cb.getBoundingClientRect();
                return {found: true, visible: rect.width > 0 && rect.height > 0,
                        x: Math.round(rect.x), y: Math.round(rect.y)};
            })()
        """)
        print('pref_code=08 状態:', pref_visible)

        # ── Step2: 茨城県(08)をクリック ──
        if pref_visible.get('visible'):
            pref_cb = page.locator('input[name="pref_code"][value="08"]')
            await pref_cb.click()
            try:
                await page.wait_for_load_state('networkidle', timeout=8000)
            except Exception:
                pass
            await asyncio.sleep(3)
            await page.screenshot(path=str(SHOT / 'ra_03_ibaraki.png'))
            print('茨城県チェック完了')
        else:
            # 直接座標クリック (x=50, y=200付近)
            print('pref_code=08 が不可視 → evaluate でクリック')
            await page.evaluate("""
                (() => {
                    const cb = document.querySelector('input[name="pref_code"][value="08"]');
                    if (cb) {
                        cb.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
                    }
                })()
            """)
            await asyncio.sleep(4)

        # ── 現在の都市リストを確認 ──
        cities = await page.evaluate("""
            (() => {
                const all = Array.from(document.querySelectorAll('input[name="city_code[]"]'));
                return all.map(el => {
                    const lbl = el.closest('label') || el.parentElement;
                    const txt = lbl ? lbl.textContent.trim() : '';
                    const rect = el.getBoundingClientRect();
                    return {value: el.value, label: txt.substring(0,15), visible: rect.width>0};
                }).slice(0, 30);
            })()
        """)
        print(f'=== 都市リスト ({len(cities)}件) ===')
        for c in cities:
            print(' ', c)

        # ── Step3: かすみがうら市ラベルを探してクリック ──
        label_info = await page.evaluate("""
            (() => {
                const labels = Array.from(document.querySelectorAll('label'));
                return labels
                    .filter(l => l.textContent.includes('かすみがうら') ||
                                 l.textContent.includes('かすみ'))
                    .map(l => {
                        const rect = l.getBoundingClientRect();
                        return {text: l.textContent.trim(), visible: rect.width>0, x: rect.x, y: rect.y};
                    });
            })()
        """)
        print('かすみがうら市ラベル:', label_info)

        if label_info and label_info[0].get('visible'):
            lbl = page.locator('label').filter(has_text='かすみがうら').first
            await lbl.click()
            await asyncio.sleep(1)
            print('かすみがうら市 クリック完了')

        # ── 「次のステップへ」または「絞り込み」ボタン ──
        # 都市選択後の次アクションを確認
        next_btns = await page.evaluate("""
            (() => {
                const all = [];
                document.querySelectorAll('button, a, div, span').forEach(el => {
                    const txt = (el.innerText || '').trim();
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && txt.length > 0 && txt.length < 20 &&
                        (txt.includes('次') || txt.includes('絞り込み') ||
                         txt.includes('検索') || txt.includes('決定') || txt.includes('設定'))) {
                        all.push({tag: el.tagName, text: txt, cls: el.className.substring(0,30),
                                  x: Math.round(rect.x), y: Math.round(rect.y)});
                    }
                });
                return all;
            })()
        """)
        print('=== 次のアクションボタン ===')
        for b in next_btns:
            print(' ', b)

        await page.screenshot(path=str(SHOT / 'ra_04_city_selected.png'))
        await browser.close()


asyncio.run(main())
