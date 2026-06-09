# -*- coding: utf-8 -*-
"""
確定版フロー:
  1. アコーディオン → step2 (東京の市区郡)
  2. .step1_m_text クリック → step1 (都道府県選択)
  3. label.one_pref[value=08] クリック → 茨城選択
  4. div.next_step_button.next_action クリック → step2 (茨城+東京の市区郡)
  5. かすみがうら市クリック
  6. ×とじる → rental_cost2 → 検索
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
SHOT.mkdir(parents=True, exist_ok=True)


async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, slow_mo=400, channel='chrome')
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

        # ── A: アコーディオン → step2 (東京の市区郡) ──
        await page.locator('.one_slide_search_box .click_menu').first.click()
        await asyncio.sleep(2)
        print('A: アコーディオン opened')

        # ── B: step2 の「都道府県の設定」(.step1_m_text) → step1 へ ──
        await page.evaluate("() => { const el = document.querySelector('.step1_m_text'); if(el) el.click(); }")
        await asyncio.sleep(1.5)
        print('B: 都道府県の設定 → step1')

        # ── C: 茨城 (label.one_pref[value=08]) クリック ──
        ibaraki_lbl = page.locator('label.one_pref:has(input[value="08"])')
        cnt = await ibaraki_lbl.count()
        print(f'C: 茨城ラベル count={cnt}')
        if cnt > 0:
            await ibaraki_lbl.first.click()
        await asyncio.sleep(1.5)
        await page.screenshot(path=str(SHOT / 'sf_03_ibaraki.png'))

        # ── D: 「市区郡の設定へ進む」(.next_step_button.next_action) クリック ──
        next_btn = page.locator('.next_step_button.next_action')
        cnt2 = await next_btn.count()
        print(f'D: next_step_button count={cnt2}')
        if cnt2 > 0:
            await next_btn.first.click()
        await asyncio.sleep(2)
        await page.screenshot(path=str(SHOT / 'sf_04_step2_ibaraki.png'))
        print('D: 市区郡の設定へ進む クリック')

        # step2 に茨城の市区郡が表示されたか確認
        step2_content = await page.evaluate("""
            () => {
                const s2 = document.querySelector('.step2.city_select.detail_select_box');
                if (!s2) return {found: false, reason: 'no step2'};
                const text = s2.innerText || '';
                const ibaraki = text.includes('茨城') || text.includes('かすみがうら');
                const inputs = Array.from(s2.querySelectorAll('input[name="city_code[]"]'));
                const ib = inputs.filter(i => i.value.startsWith('08'));
                return {
                    found: ibaraki || ib.length > 0,
                    ibaraki_count: ib.length,
                    total: inputs.length,
                    preview: text.substring(0, 300)
                };
            }
        """)
        print(f'D 後 step2: found={step2_content["found"]}, ibaraki_inputs={step2_content["ibaraki_count"]}')
        print(f'  preview: {step2_content["preview"][:200]}')

        if step2_content.get('found'):
            print('★★ 茨城の市区郡リストが表示されました！')

            # ── E: かすみがうら市クリック ──
            kasumi = await page.evaluate("""
                () => {
                    const s2 = document.querySelector('.step2.city_select.detail_select_box');
                    const labels = Array.from(s2 ? s2.querySelectorAll('label') :
                                             document.querySelectorAll('label'));
                    const lbl = labels.find(l => l.textContent.includes('かすみがうら'));
                    if (lbl) {
                        lbl.click();
                        return {found: true, text: lbl.textContent.trim()};
                    }
                    // 全ラベル（デバッグ用）
                    const ib_labels = labels.filter(l => {
                        const inp = l.querySelector('input');
                        return inp && inp.value.startsWith('08');
                    }).map(l => l.textContent.trim());
                    return {found: false, ibaraki_labels: ib_labels.slice(0, 40)};
                }
            """)
            print(f'E: かすみがうら → {kasumi}')
            await asyncio.sleep(1)
            await page.screenshot(path=str(SHOT / 'sf_05_kasumi.png'))

            # ── F: ×とじる ──
            closed = await page.evaluate("""
                () => {
                    const spans = Array.from(document.querySelectorAll('span'));
                    const close = spans.find(s => s.textContent.trim() === '×とじる' &&
                                                  s.getBoundingClientRect().width > 0);
                    if (close) { close.click(); return true; }
                    return false;
                }
            """)
            print(f'F: ×とじる={closed}')
            await asyncio.sleep(1)

            # ── G: rental_cost2 ──
            try:
                await page.select_option('select[name="rental_cost2"]', '70000')
                print('G: 家賃上限 7万円')
            except Exception as e:
                print(f'G エラー: {e}')

            # ── H: 検索 ──
            await page.screenshot(path=str(SHOT / 'sf_05b_before_search.png'))
            # モーダルが閉じた後の visible な 検索ボタンをクリック
            clicked_search = await page.evaluate("""
                () => {
                    // visible な 検索 button/input を探す
                    const candidates = Array.from(
                        document.querySelectorAll('button, input[type="button"], input[type="submit"]')
                    );
                    const btn = candidates.find(el => {
                        const t = (el.innerText || el.value || '').trim();
                        const r = el.getBoundingClientRect();
                        return t === '検索' && r.width > 0 && r.height > 0;
                    });
                    if (btn) { btn.click(); return {found: true, tag: btn.tagName, cls: btn.className}; }
                    return {found: false};
                }
            """)
            print(f'H: 検索ボタン = {clicked_search}')
            if not clicked_search.get('found'):
                # フォームを直接 submit
                await page.evaluate("() => { document.getElementById('main_form')?.submit(); }")
                print('H: フォーム submit (fallback)')
            try:
                await page.wait_for_load_state('networkidle', timeout=12000)
            except Exception:
                pass
            await asyncio.sleep(4)
            await page.screenshot(path=str(SHOT / 'sf_06_result.png'))
            print('H: 検索後 URL:', page.url)

            rooms = await page.evaluate("""
                () => {
                    const r = [];
                    document.querySelectorAll('.room_system_menu[title]').forEach(el => {
                        const t = el.getAttribute('title');
                        if (t && t.includes(',')) {
                            const p = t.split(',');
                            if (/^\\d+$/.test(p[0].trim()))
                                r.push({id: p[0].trim(), name: (p[1]||'').trim()});
                        }
                    });
                    return r;
                }
            """)
            print(f'結果: {len(rooms)}件')
            for r in rooms[:10]:
                print(' ', r)
        else:
            print('✗ 茨城が表示されませんでした')
            print('preview:', step2_content.get('preview', '')[:300])

        await browser.close()


asyncio.run(main())
