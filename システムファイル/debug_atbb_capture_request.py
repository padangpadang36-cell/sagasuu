# -*- coding: utf-8 -*-
"""ATBBインフォシートのPDF出力ボタンクリック時のネットワークリクエストを詳細に調べる"""
import sys, io, asyncio, re, json
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
    """ログイン→検索→インフォシートタブを返す"""
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

    # 賃貸居住用を選択
    try:
        await page.locator('input[name="atbbShumokuDaibunrui"][value="06"]').click(force=True)
    except: pass
    await asyncio.sleep(2)

    # フリーワード検索
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

    # 物件詳細へ
    shosai0 = await page.evaluate("() => !!document.getElementById('shosai_0')")
    if not shosai0:
        print("shosai_0なし")
        return None, page

    await page.evaluate("document.getElementById('shosai_0').click()")
    await page.wait_for_load_state("domcontentloaded", timeout=20000)
    await asyncio.sleep(4)

    # インフォシートボタン
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

        # ネットワーク監視を設定
        captured_requests = []
        captured_responses = []

        async def on_request(request):
            if 'info_sheet' in request.url or 'infosheets' in request.url:
                try:
                    body = request.post_data or ''
                    headers = dict(request.headers)
                    captured_requests.append({
                        'url': request.url,
                        'method': request.method,
                        'headers': headers,
                        'body': body[:2000] if body else ''
                    })
                except Exception as e:
                    print(f"request capture err: {e}")

        async def on_response(response):
            if 'info_sheet' in response.url or 'infosheets' in response.url:
                try:
                    ct = response.headers.get('content-type', '')
                    status = response.status
                    body_bytes = await response.body()
                    captured_responses.append({
                        'url': response.url,
                        'status': status,
                        'ct': ct,
                        'body': body_bytes[:200],
                        'body_len': len(body_bytes),
                        'is_pdf': body_bytes[:4] == b'%PDF'
                    })
                except Exception as e:
                    print(f"response capture err: {e}")

        ctx.on('request', on_request)
        ctx.on('response', on_response)

        print("\n=== PDF出力ボタンクリック (ネットワーク監視中) ===")
        try:
            async with ctx.expect_page(timeout=15000) as new_pg_info:
                await info_tab.click('#button-pdf-format')
            new_pg = await new_pg_info.value
            await asyncio.sleep(5)
            print(f"新規タブURL: {new_pg.url}")
        except Exception as e:
            print(f"新規タブエラー: {e}")

        print(f"\nキャプチャされたリクエスト: {len(captured_requests)}件")
        for r in captured_requests:
            print(f"\n--- REQUEST: {r['method']} {r['url'][:80]} ---")
            # ヘッダーで重要なもの
            for k in ['content-type', 'origin', 'referer', 'cookie', 'x-csrf-token']:
                if k in r['headers']:
                    print(f"  {k}: {r['headers'][k][:100]}")
            if r['body']:
                # URLエンコードされたbodyを解析
                try:
                    from urllib.parse import unquote_plus
                    parts = r['body'].split('&')
                    print(f"  POSTデータ:")
                    for p in parts:
                        if '=' in p:
                            k, v = p.split('=', 1)
                            print(f"    {k}: {unquote_plus(v)[:100]}")
                except:
                    print(f"  body: {r['body'][:200]}")

        print(f"\nキャプチャされたレスポンス: {len(captured_responses)}件")
        for r in captured_responses:
            print(f"\n--- RESPONSE: {r['url'][:80]} ---")
            print(f"  status={r['status']} ct={r['ct'][:50]}")
            print(f"  body: {r['body_len']:,}B, is_pdf={r['is_pdf']}, head={r['body'][:30]}")
            if r['is_pdf']:
                # PDF保存テスト
                pdf_capture_path = str(OUT_DIR / "captured_response.pdf")
                body_all = await captured_responses[-1]  # can't re-fetch...

        # PDFが取れた場合の保存
        for r in captured_responses:
            if r['is_pdf']:
                print(f"\n★ PDFレスポンスがキャプチャされました!")
                # ただしbodyは200bytesに制限されている...
                # 本当のbodyは別途取得必要

        await asyncio.sleep(10)
        await browser.close()


asyncio.run(main())
