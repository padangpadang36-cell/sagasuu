# -*- coding: utf-8 -*-
"""ATBBインフォシートのPDF出力ボタン後の全ネットワークリクエストを監視"""
import sys, io, asyncio, re
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

OUT_DIR = Path(__file__).parent / "デバッグ" / "atbb_infosheet"
OUT_DIR.mkdir(parents=True, exist_ok=True)


async def login_search_infosheet(page, ctx):
    await page.goto(ATBB_URL, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(2)
    await page.locator('input[name="loginId"]').fill(ATBB_ID)
    await page.locator('input[type="password"]').fill(ATBB_PASS)
    await page.locator('input[type="submit"]').click()
    try: await page.wait_for_load_state("networkidle", timeout=15000)
    except: pass
    await asyncio.sleep(2)

    try:
        el = page.locator('a:has-text("物件・会社検索")').first
        await el.wait_for(state="visible", timeout=5000)
        await el.click()
        await asyncio.sleep(1)
        el2 = page.get_by_text("流通物件検索").first
        async with ctx.expect_page(timeout=8000) as np_info:
            await el2.click()
        new_page = await np_info.value
        await new_page.wait_for_load_state("domcontentloaded", timeout=15000)
        page = new_page
    except Exception as e: print(f"メニューエラー: {e}")

    await asyncio.sleep(3)
    if "ConcurrentLoginException" in page.url:
        force_info = await page.evaluate("() => { const f=document.querySelector('form'); return f ? {action:f.action} : null; }")
        action = force_info['action'] if force_info else None
        sid_m = re.search(r'jsessionid=([A-Fa-f0-9]+)', page.url)
        if action and sid_m:
            action += f';jsessionid={sid_m.group(1)}'
        if action:
            await page.goto(action, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(4)
    await asyncio.sleep(3)

    try:
        await page.locator('input[name="atbbShumokuDaibunrui"][value="06"]').click(force=True)
    except: pass
    await asyncio.sleep(2)

    await page.evaluate("""
        () => {
            const hint = document.getElementById('freeWordHint');
            if (hint) hint.style.display = 'none';
            const el = document.getElementById('freeWordSearchSubject');
            if (el) { el.focus(); el.value = '大阪市北区 8万円以下';
                el.dispatchEvent(new Event('input', {bubbles:true})); }
        }
    """)
    await asyncio.sleep(0.5)
    is_vis = await page.locator('#freeWordSearchSubjectButton').is_visible(timeout=2000)
    if is_vis:
        await page.click('#freeWordSearchSubjectButton')
    else:
        await page.evaluate("() => { try { searchFreeWord(document.bfcm300s, 'bfcm300s008'); } catch(e) {} }")
    await asyncio.sleep(6)

    shosai0 = await page.evaluate("() => !!document.getElementById('shosai_0')")
    if not shosai0:
        return None, page

    await page.evaluate("document.getElementById('shosai_0').click()")
    await page.wait_for_load_state("domcontentloaded", timeout=20000)
    await asyncio.sleep(4)

    btn = page.locator('#infoSheetButtonTop_0')
    if not await btn.is_visible(timeout=3000):
        btn = page.locator('button:has-text("インフォシート")').first
    async with ctx.expect_page(timeout=10000) as np_info:
        await btn.click()
    info_tab = await np_info.value
    await info_tab.wait_for_load_state("domcontentloaded", timeout=20000)
    await asyncio.sleep(6)
    print(f"インフォシートURL: {info_tab.url}")
    return info_tab, page


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, channel="chrome", slow_mo=200)
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="ja-JP",
            accept_downloads=True,
        )
        page = await ctx.new_page()

        info_tab, search_page = await login_search_infosheet(page, ctx)
        if not info_tab:
            await browser.close()
            return

        # 全ネットワークリクエストを監視（新規タブ含む）
        all_responses = []

        async def on_response(response):
            url = response.url
            ct = response.headers.get('content-type', '')
            status = response.status
            # 静的アセット以外
            skip_exts = ('.js', '.css', '.png', '.jpg', '.ico', '.woff', '.woff2', '.svg', '.gif')
            if any(url.endswith(e) for e in skip_exts):
                return
            if any(x in url for x in ['google', 'googleapis', 'gstatic', 'analytics', 'beacon']):
                return
            try:
                body = await response.body()
                is_pdf = body[:4] == b'%PDF'
                all_responses.append({
                    'url': url, 'status': status, 'ct': ct,
                    'len': len(body), 'is_pdf': is_pdf,
                    'body_head': body[:20],
                    'body': body  # 全バイナリを保持
                })
                flag = '★PDF' if is_pdf else ''
                print(f"  {flag} RESP {status} {ct[:30]:30} {len(body):8,}B {url[:80]}")
            except Exception as e:
                pass

        ctx.on('response', on_response)

        print("\n=== PDF出力ボタンクリック (全レスポンス監視中) ===")
        try:
            async with ctx.expect_page(timeout=15000) as new_pg_info:
                await info_tab.click('#button-pdf-format')
            new_pg = await new_pg_info.value
            await asyncio.sleep(10)  # 全リソースのロードを待つ
            print(f"\n新規タブURL: {new_pg.url}")
            print(f"新規タブタイトル: {await new_pg.title()}")

            # 新規タブのDOMを確認
            new_tab_body = await new_pg.evaluate("() => document.body ? document.body.innerHTML.substring(0, 500) : 'no body'")
            print(f"\n新規タブのDOM (500chars):\n{new_tab_body}")

        except Exception as e:
            print(f"エラー: {e}")
            new_pg = None

        print(f"\n=== 全レスポンス一覧 ({len(all_responses)}件) ===")
        for r in all_responses:
            flag = '★PDF' if r['is_pdf'] else '     '
            print(f"{flag} {r['status']} {r['ct'][:30]:30} {r['len']:8,}B {r['url'][:90]}")

        # PDF保存
        for r in all_responses:
            if r['is_pdf']:
                path = str(OUT_DIR / f"captured_{all_responses.index(r)}.pdf")
                with open(path, 'wb') as f:
                    f.write(r['body'])
                print(f"\n★ PDF保存: {path} ({r['len']:,} bytes)")

        # HTMLレスポンスも保存（調査用）
        for i, r in enumerate(all_responses):
            if r['ct'] and ('html' in r['ct'] or r['ct'] == ''):
                path = str(OUT_DIR / f"resp_{i}_{r['status']}.html")
                with open(path, 'wb') as f:
                    f.write(r['body'])
                print(f"HTML保存: {path} ({r['len']:,} bytes) {r['url'][:60]}")

        await asyncio.sleep(5)
        await browser.close()


asyncio.run(main())
