# -*- coding: utf-8 -*-
"""ATBBインフォシートのPDF出力ボタンをクリックしてPDFを取得"""
import sys, io, asyncio, re, os, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv(Path(__file__).parent.parent / ".env")
ATBB_URL  = "https://atbb.athome.jp/"
ATBB_ID   = os.getenv("ATBB_ID", "")
ATBB_PASS = os.getenv("ATBB_PASS", "")

OUT_DIR = Path(__file__).parent / "デバッグ" / "atbb_infosheet"
OUT_DIR.mkdir(parents=True, exist_ok=True)


async def login_and_get_infosheet_url(page, ctx) -> str:
    """ATBBにログインして物件インフォシートのURLを取得する"""
    # Login
    await page.goto(ATBB_URL, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(2)
    await page.locator('input[name="loginId"]').fill(ATBB_ID)
    await page.locator('input[type="password"]').fill(ATBB_PASS)
    await page.locator('input[type="submit"]').click()
    try:
        await page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    await asyncio.sleep(2)

    # Navigate to 流通物件検索
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
    except Exception as e:
        print(f"メニューエラー: {e}")

    await asyncio.sleep(3)

    # ConcurrentLoginException対応
    if "ConcurrentLoginException" in page.url:
        try:
            force_info = await page.evaluate("""
                () => { const form = document.querySelector('form'); if (!form) return null;
                    return {action: form.action}; }
            """)
            action = force_info['action'] if force_info else None
            sid_m = re.search(r'jsessionid=([A-Fa-f0-9]+)', page.url)
            if action and sid_m:
                action = action + f';jsessionid={sid_m.group(1)}'
            elif sid_m:
                action = f"https://atbb.athome.co.jp/front-web/login/force;jsessionid={sid_m.group(1)}"
            if action:
                await page.goto(action, wait_until="domcontentloaded", timeout=20000)
        except Exception as e:
            print(f"強制ログインエラー: {e}")
        await asyncio.sleep(4)

    await asyncio.sleep(3)
    print(f"流通物件検索URL: {page.url}")

    # 賃貸居住用を選択（locator.click()でVue reactivityを確実にトリガー）
    try:
        radio = page.locator('input[name="atbbShumokuDaibunrui"][value="06"]')
        await radio.click(force=True)
    except Exception:
        await page.evaluate("""
            () => {
                const r = document.querySelector('input[name="atbbShumokuDaibunrui"][value="06"]');
                if (r) { r.checked = true; r.click(); }
            }
        """)
    await asyncio.sleep(2)  # フリーワードフィールドが表示されるまで待機

    # フリーワード検索 - JSで直接関数呼び出し
    await page.evaluate("""
        () => {
            const hint = document.getElementById('freeWordHint');
            if (hint) hint.style.display = 'none';
            const el = document.getElementById('freeWordSearchSubject');
            if (el) {
                el.focus(); el.value = '大阪市北区 8万円以下';
                el.dispatchEvent(new Event('input', {bubbles:true}));
                el.dispatchEvent(new Event('change', {bubbles:true}));
            }
        }
    """)
    await asyncio.sleep(0.5)

    # ボタンが見えていればクリック、なければ直接JS関数呼び出し
    try:
        is_vis = await page.locator('#freeWordSearchSubjectButton').is_visible(timeout=2000)
        if is_vis:
            await page.click('#freeWordSearchSubjectButton')
        else:
            # onclick関数を直接呼び出す
            await page.evaluate("() => searchFreeWord(document.bfcm300s, 'bfcm300s008')")
    except Exception:
        await page.evaluate("() => { try { searchFreeWord(document.bfcm300s, 'bfcm300s008'); } catch(e) { document.getElementById('freeWordSearchSubjectButton').click(); } }")
    await asyncio.sleep(6)
    print(f"検索結果URL: {page.url}")

    # 物件詳細へ
    shosai0 = await page.evaluate("() => !!document.getElementById('shosai_0')")
    if not shosai0:
        print("shosai_0が見つかりません")
        return None, None

    await page.evaluate("document.getElementById('shosai_0').click()")
    await page.wait_for_load_state("domcontentloaded", timeout=20000)
    await asyncio.sleep(4)
    print(f"詳細URL: {page.url}")

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


async def download_pdf_via_form(info_tab, ctx, fee_disp: bool, out_path: str) -> bool:
    """フォームデータを修正してrequestsライブラリでPDFを直接POSTする"""
    import requests as req_lib
    try:
        # フォームデータを取得
        form_data = await info_tab.evaluate("""
            () => {
                const btn = document.getElementById('button-pdf-format');
                const form = btn.closest('form');
                const inputs = {};
                Array.from(form.querySelectorAll('input[type=hidden]')).forEach(i => {
                    if (i.name) inputs[i.name] = i.value;
                });
                return {action: form.action, inputs: inputs};
            }
        """)
        print(f"フォームアクション: {form_data['action']}")

        # infosheets JSONを解析・修正
        infosheets_raw = form_data['inputs'].get('infosheets', '[]')
        infosheets = json.loads(infosheets_raw)
        print(f"infosheets: pattern={infosheets[0].get('pattern')} feeDispFlg={infosheets[0].get('feeDispFlg')}")

        for item in infosheets:
            item['feeDispFlg'] = fee_disp

        modified_json = json.dumps(infosheets, ensure_ascii=False)
        form_action = form_data['inputs'].get  # unused
        token = form_data['inputs'].get('authenticity_token', '')
        utf8_val = '✓'  # ✓

        # Playwrightのcookiesを取得
        pw_cookies = await info_tab.context.cookies()
        session = req_lib.Session()
        for c in pw_cookies:
            if 'zmn.atbb' in c.get('domain', '') or 'atbb.athome' in c.get('domain', ''):
                session.cookies.set(c['name'], c['value'], domain=c.get('domain', ''))

        infosheet_url = info_tab.url
        action_url = form_data['action']

        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://zmn.atbb.athome.co.jp',
            'Referer': infosheet_url,
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36',
            'Accept': 'application/pdf,*/*;q=0.9',
            'X-Requested-With': 'XMLHttpRequest',
        }

        post_data = {
            'utf8': utf8_val,
            'authenticity_token': token,
            'infosheets': modified_json,
        }

        print(f"requestsでPOST: feeDispFlg={fee_disp}")
        resp = session.post(action_url, data=post_data, headers=headers, timeout=30, allow_redirects=True)
        ct = resp.headers.get('content-type', '')
        print(f"レスポンス: status={resp.status_code} ct={ct[:50]} len={len(resp.content):,}")
        print(f"  先頭16bytes: {resp.content[:16]}")

        if resp.status_code == 200 and resp.content[:4] == b'%PDF':
            with open(out_path, 'wb') as f:
                f.write(resp.content)
            print(f"✓ requests PDF保存: {out_path} ({os.path.getsize(out_path):,} bytes)")
            return True
        elif resp.status_code == 200:
            print(f"  200だがPDFではない: {resp.text[:300]}")
        else:
            print(f"  エラーレスポンス: {resp.text[:300]}")

        # フォールバック: ブラウザボタンクリック + 新規タブのネットワーク応答
        print("フォールバック: ブラウザボタンクリック + 応答インターセプト")

        # 修正したinfosheetsをフォームにセット
        modified_js = json.dumps(modified_json)
        await info_tab.evaluate(f"""
            () => {{
                const btn = document.getElementById('button-pdf-format');
                const form = btn.closest('form');
                const inf = form.querySelector('input[name="infosheets"]');
                inf.value = {modified_js};
            }}
        """)

        # 新規タブをキャプチャ
        try:
            async with ctx.expect_page(timeout=25000) as new_pg_info:
                await info_tab.click('#button-pdf-format')
            new_pg = await new_pg_info.value
            await asyncio.sleep(5)
            new_url = new_pg.url
            print(f"  新規タブURL: {new_url}")

            # 新規タブのCookieでダウンロード試行
            pw_cookies2 = await info_tab.context.cookies()
            session2 = req_lib.Session()
            for c in pw_cookies2:
                session2.cookies.set(c['name'], c['value'], domain=c.get('domain', ''))

            # 新規タブからのURLは同じaction URLなのでPOSTで再試行
            # ただしtoken更新後に再取得
            form_data2 = await new_pg.evaluate("""
                () => {
                    const forms = document.querySelectorAll('form');
                    for (const f of forms) {
                        const t = f.querySelector('input[name="authenticity_token"]');
                        if (t) return {token: t.value, action: f.action};
                    }
                    return null;
                }
            """)
            print(f"  新規タブフォーム: {form_data2}")

            await new_pg.close()
        except Exception as e2:
            print(f"  新規タブエラー: {e2}")

        return False

    except Exception as e:
        print(f"PDFダウンロードエラー: {e}")
        import traceback; traceback.print_exc()
        return False


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, channel="chrome", slow_mo=200)
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="ja-JP",
            accept_downloads=True,
        )
        page = await ctx.new_page()

        # ① ログイン→インフォシートを開く
        info_tab, search_page = await login_and_get_infosheet_url(page, ctx)
        if not info_tab:
            await browser.close()
            return

        # ② 元図面PDF (page.pdf - 現在の表示そのまま)
        moto_pdf = str(OUT_DIR / "dl_01_mototsuke_pagepdf.pdf")
        await info_tab.pdf(path=moto_pdf, format="A4", print_background=True)
        print(f"\n✓ 元図面(page.pdf): {moto_pdf} ({os.path.getsize(moto_pdf):,} bytes)")

        # ③ 手数料あり版PDF (feeDispFlg=true, pattern="a")
        pdf_fee_on = str(OUT_DIR / "dl_02_fee_on.pdf")
        ok = await download_pdf_via_form(info_tab, ctx, fee_disp=True, out_path=pdf_fee_on)

        # ④ 手数料なし版PDF (feeDispFlg=false, pattern="a") ← 社宅.com版
        pdf_fee_off = str(OUT_DIR / "dl_03_fee_off_syataku.pdf")
        ok2 = await download_pdf_via_form(info_tab, ctx, fee_disp=False, out_path=pdf_fee_off)

        print("\n=== 完了 ===")
        print(f"元図面(page.pdf): {moto_pdf}")
        print(f"手数料あり: {pdf_fee_on}")
        print(f"社宅.com版(手数料なし): {pdf_fee_off}")

        await asyncio.sleep(5)
        await browser.close()


asyncio.run(main())
