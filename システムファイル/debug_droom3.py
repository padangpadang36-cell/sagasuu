# -*- coding: utf-8 -*-
"""D-Room Droomシート一括出力ボタンのclick動作を詳しく調査"""
import sys, io, asyncio
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import os
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv(Path(__file__).parent.parent / ".env")
DROOM_URL    = "https://anavi.daiwaliving.co.jp/dp/login"
DROOM_TENPO  = os.getenv("DROOM_TENPO", "")
DROOM_TANTO  = os.getenv("DROOM_TANTO", "")
DROOM_PASS   = os.getenv("DROOM_PASS", "")
ROOM_LIST_URL = "https://anavi.daiwaliving.co.jp/dp/navi/room/RoomList/menu"

OUT_DIR = Path(__file__).parent / "デバッグ" / "droom"
OUT_DIR.mkdir(parents=True, exist_ok=True)

async def login_droom(page):
    await page.goto(DROOM_URL, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(2)
    await page.locator('#txtEnterpriseId').fill(DROOM_TENPO)
    await page.locator('#txtUserId').fill(DROOM_TANTO)
    await page.locator('#txtPassword').fill(DROOM_PASS)
    await page.locator('#btnLoginButton').click()
    try:
        await page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    await asyncio.sleep(2)
    if "CheckLogin" in page.url:
        try:
            await page.locator('#forcepassword').fill(DROOM_PASS)
        except Exception:
            pass
        await page.locator('#forceloginok').click()
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        await asyncio.sleep(3)
    print(f"ログイン後URL: {page.url}")

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, channel="chrome", slow_mo=200)
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 900}, locale="ja-JP",
            accept_downloads=True)
        page = await ctx.new_page()

        await login_droom(page)
        # メニュー → 物件リスト
        try:
            await page.get_by_text("メニューに進む").first.click()
            await asyncio.sleep(2)
        except Exception:
            pass
        await page.goto(ROOM_LIST_URL, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)

        # 住所で検索（大阪市北区）
        try:
            await page.locator('input[name="address"]').fill("大阪市北区")
            print("  住所入力: 大阪市北区")
        except Exception as e:
            print(f"  住所入力エラー: {e}")

        # 家賃上限入力
        try:
            await page.locator('input[name="rentTo"]').fill("8")
            print("  家賃上限: 8万円")
        except Exception as e:
            print(f"  家賃上限エラー: {e}")

        # 検索実行 - フォームsubmit
        try:
            await page.evaluate("""
                () => {
                    // 検索フォームを探してsubmit
                    const forms = document.querySelectorAll('form');
                    for (const f of forms) {
                        const inputs = f.querySelectorAll('input[name="address"]');
                        if (inputs.length > 0) { f.submit(); return 'submitted'; }
                    }
                    return 'no form';
                }
            """)
            print("  フォームsubmit")
        except Exception as e:
            print(f"  submit失敗: {e}")
        await asyncio.sleep(5)
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass
        await asyncio.sleep(2)
        print(f"検索後URL: {page.url}")
        await page.screenshot(path=str(OUT_DIR / "B1_search_result.png"))

        body = await page.evaluate("() => document.body.innerText")
        print(f"結果テキスト(先頭1000):\n{body[:1000]}")

        # ── ボタンの詳細を取得 ──
        btn_info = await page.evaluate("""
            () => {
                const results = [];
                for (const el of document.querySelectorAll('a, button, input[type="button"], input[type="submit"], input[type="image"]')) {
                    const t = (el.textContent.trim() || el.value || el.alt || '').replace(/\\s+/g,' ').substring(0,80);
                    results.push({
                        tag: el.tagName,
                        id: el.id || '',
                        name: el.name || '',
                        text: t,
                        href: el.href || '',
                        onclick: el.getAttribute('onclick') || '',
                        'data-url': el.getAttribute('data-url') || '',
                        'data-form': el.getAttribute('data-form') || '',
                        class: el.className || ''
                    });
                }
                return results;
            }
        """)
        print(f"\n=== 全ボタン ({len(btn_info)}件) ===")
        for b in btn_info:
            txt = b['text']
            if any(k in (txt + b['onclick'] + b['href'] + b.get('data-url','')).lower()
                   for k in ['droom', 'sheet', '一括', '出力', 'csv', '選択']):
                print(f"  ★ {b}")
            else:
                print(f"  {b['tag']} [{b['id']}] '{txt[:30]}' onclick={b['onclick'][:50]}")

        # チェックボックスを探して選択
        print(f"\n=== チェックボックス選択 ===")
        cbs = await page.locator('input[type="checkbox"]').all()
        print(f"チェックボックス数: {len(cbs)}")

        # 各CBのname/id/value/onclickを確認
        for i, cb in enumerate(cbs[:10]):
            try:
                nm = await cb.get_attribute('name') or ''
                id_ = await cb.get_attribute('id') or ''
                val = await cb.get_attribute('value') or ''
                oc = await cb.get_attribute('onclick') or ''
                print(f"  CB[{i}] name={nm} id={id_} value={val[:30]} onclick={oc[:50]}")
            except Exception:
                pass

        # 最初の3件を選択
        selected = 0
        for i, cb in enumerate(cbs):
            try:
                nm = await cb.get_attribute('name') or ''
                if 'select' in nm.lower() or 'room' in nm.lower() or nm == '':
                    if not await cb.is_checked():
                        await cb.check()
                        selected += 1
                        if selected >= 3:
                            break
            except Exception:
                pass
        print(f"  {selected}件チェック")
        await asyncio.sleep(1)
        await page.screenshot(path=str(OUT_DIR / "B2_checked.png"))

        # ネットワークリクエストを監視
        requests_log = []
        def on_req(req):
            if 'sheet' in req.url.lower() or 'droom' in req.url.lower() or 'pdf' in req.url.lower():
                requests_log.append(f"REQ {req.method} {req.url[:120]}")
        def on_resp(resp):
            ct = resp.headers.get('content-type','')
            if 'pdf' in ct.lower() or 'octet' in ct.lower() or 'zip' in ct.lower():
                requests_log.append(f"RES [{resp.status}] ct={ct[:60]} {resp.url[:80]}")
        page.on("request", on_req)
        page.on("response", on_resp)

        # D-roomシート一括出力をクリック
        print(f"\n=== D-roomシート一括出力クリック ===")
        droom_btn = None
        for text in ['D-roomシート一括出力', 'Droomシート一括出力', 'D-room', 'droom', '一括出力']:
            try:
                el = page.get_by_text(text, exact=False).first
                if await el.is_visible(timeout=1000):
                    droom_btn = el
                    print(f"  ボタン発見: '{text}'")
                    break
            except Exception:
                continue

        if droom_btn:
            print("  ダウンロード監視開始...")
            try:
                async with ctx.expect_download(timeout=20000) as dl_info:
                    await droom_btn.click()
                dl = await dl_info.value
                fname = dl.suggested_filename
                save_path = str(OUT_DIR / fname)
                await dl.save_as(save_path)
                print(f"  ✓ ダウンロード: {fname}")
                print(f"  保存: {save_path}")
                with open(save_path, 'rb') as f:
                    hdr = f.read(10)
                print(f"  ファイル先頭: {hdr}")
            except Exception as dl_err:
                print(f"  ダウンロードなし({type(dl_err).__name__}: {dl_err})")
                await asyncio.sleep(4)
                print(f"  現在URL: {page.url}")
                print(f"  タブ数: {len(ctx.pages)}")
                for i, p in enumerate(ctx.pages):
                    print(f"    タブ{i}: {p.url}")

                # 新規タブを確認
                if len(ctx.pages) > 1:
                    new_tab = ctx.pages[-1]
                    nurl = new_tab.url
                    print(f"  新規タブ: {nurl}")
                    await new_tab.screenshot(path=str(OUT_DIR / "B3_new_tab.png"))
                    nt_text = await new_tab.evaluate("() => document.body.innerText")
                    print(f"  新規タブテキスト: {nt_text[:300]}")
        else:
            print("  D-roomシート一括出力ボタンが見つかりません！")
            print("  見つかったテキスト:")
            all_texts = await page.evaluate("() => Array.from(document.querySelectorAll('a,button,input[type=submit],input[type=button]')).map(e=>(e.textContent||e.value||'').trim()).filter(t=>t)")
            for t in all_texts:
                print(f"    '{t}'")

        print(f"\nネットワークログ:")
        for r in requests_log:
            print(f"  {r}")

        # 個別のD-roomシートも試す
        print(f"\n=== 個別 D-roomシートボタンを確認 ===")
        individual_btns = await page.evaluate("""
            () => {
                const results = [];
                for (const el of document.querySelectorAll('a, button')) {
                    const t = (el.textContent.trim() || '').replace(/\\s+/g,' ');
                    if (t === 'D-roomシート' || t === 'Droomシート') {
                        results.push({
                            text: t,
                            href: el.href || '',
                            onclick: (el.getAttribute('onclick') || '').substring(0,100),
                            'data-url': el.getAttribute('data-url') || ''
                        });
                    }
                }
                return results.slice(0, 5);
            }
        """)
        print(f"個別ボタン: {len(individual_btns)}件")
        for b in individual_btns:
            print(f"  {b}")

        if individual_btns and not droom_btn:
            print("\n個別D-roomシートをクリック試行")
            try:
                first_btn = page.get_by_text("D-roomシート", exact=True).first
                try:
                    async with ctx.expect_download(timeout=15000) as dl_info:
                        await first_btn.click()
                    dl = await dl_info.value
                    save_path = str(OUT_DIR / dl.suggested_filename)
                    await dl.save_as(save_path)
                    print(f"  ✓ 個別DL: {dl.suggested_filename}")
                except Exception as e:
                    print(f"  個別DLエラー: {e}")
                    await asyncio.sleep(3)
                    print(f"  現在URL: {page.url}")
                    print(f"  タブ数: {len(ctx.pages)}")
            except Exception as e:
                print(f"  ボタン操作エラー: {e}")

        print(f"\n=== 完了 ===")
        await browser.close()

asyncio.run(main())
