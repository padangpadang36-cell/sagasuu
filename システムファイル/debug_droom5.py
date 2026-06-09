# -*- coding: utf-8 -*-
"""D-Room: bb-checkboxラベル内のチェックボックス選択 → 一括出力"""
import sys, io, asyncio
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import os
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv(Path(__file__).parent.parent / ".env")
DROOM_URL     = "https://anavi.daiwaliving.co.jp/dp/login"
DROOM_TENPO   = os.getenv("DROOM_TENPO", "")
DROOM_TANTO   = os.getenv("DROOM_TANTO", "")
DROOM_PASS    = os.getenv("DROOM_PASS", "")
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

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, channel="chrome", slow_mo=300)
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 900}, locale="ja-JP",
            accept_downloads=True)
        page = await ctx.new_page()

        await login_droom(page)
        try:
            await page.get_by_text("メニューに進む").first.click()
            await asyncio.sleep(2)
        except Exception:
            pass

        await page.goto(ROOM_LIST_URL, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)

        # 住所検索（大阪市北区）
        try:
            await page.locator('input[name="address"]').fill("大阪市北区")
        except Exception:
            pass

        # フォームsubmit
        await page.evaluate("() => { const f=document.querySelector('form'); if(f) f.submit(); }")
        await asyncio.sleep(5)
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass
        await asyncio.sleep(2)
        print(f"検索URL: {page.url}")

        # 物件選択チェックボックスを探す（.bb-checkbox の中の input[type=checkbox]）
        print(f"\n=== .bb-checkbox チェックボックス確認 ===")
        bb_cbs_info = await page.evaluate("""
            () => {
                const results = [];
                const labels = document.querySelectorAll('label.bb-checkbox, .bb-checkbox');
                for (const lb of labels) {
                    const cb = lb.querySelector('input[type="checkbox"]');
                    if (cb) {
                        results.push({
                            label_text: lb.textContent.trim().substring(0,20),
                            cb_name: cb.name || cb.id || '',
                            cb_value: cb.value || '',
                            cb_checked: cb.checked,
                            cb_class: cb.className || ''
                        });
                    }
                }
                return results;
            }
        """)
        print(f".bb-checkbox数: {len(bb_cbs_info)}")
        for c in bb_cbs_info:
            print(f"  {c}")

        # 全チェックボックスを確認（全部）
        print(f"\n=== 全チェックボックス (上限30件) ===")
        all_cbs_info = await page.evaluate("""
            () => {
                const results = [];
                for (const cb of document.querySelectorAll('input[type="checkbox"]')) {
                    results.push({
                        name: cb.name || '',
                        id: cb.id || '',
                        value: cb.value || '',
                        checked: cb.checked,
                        parent_class: (cb.parentElement && cb.parentElement.className) || ''
                    });
                }
                return results;
            }
        """)
        print(f"全CB数: {len(all_cbs_info)}")
        for c in all_cbs_info[:40]:
            print(f"  {c}")
        if len(all_cbs_info) > 40:
            print(f"  ... ({len(all_cbs_info) - 40}件省略)")

        # 物件選択用チェックボックス（.bb-checkbox またはname*="room"/"select"）をチェック
        print(f"\n=== 物件選択チェックボックスをON ===")
        selected_count = await page.evaluate("""
            () => {
                // .bb-checkbox 内のチェックボックスを全てON
                let cnt = 0;
                const labels = document.querySelectorAll('label.bb-checkbox');
                for (const lb of labels) {
                    const cb = lb.querySelector('input[type="checkbox"]');
                    if (cb && !cb.disabled) {
                        cb.checked = true;
                        // change/click イベントを発火
                        cb.dispatchEvent(new Event('change', {bubbles: true}));
                        cb.dispatchEvent(new Event('click', {bubbles: true}));
                        cnt++;
                    }
                }
                return cnt;
            }
        """)
        print(f"  JSで選択: {selected_count}件")
        await asyncio.sleep(1)

        # 選択件数カウンターを確認
        sel_count_text = await page.evaluate("""
            () => {
                const el = document.querySelector('.select-count, [id*="select-count"], .bb-select-count');
                return el ? el.textContent.trim() :
                    document.body.innerText.match(/選択件数[:：]\\s*(\\d+)件/)?.[0] || '不明';
            }
        """)
        print(f"  選択件数表示: {sel_count_text}")
        await page.screenshot(path=str(OUT_DIR / "D1_selected.png"))

        # D-roomシート一括出力ボタンをクリック
        print(f"\n=== D-roomシート一括出力クリック ===")
        # ネットワーク監視
        net_log = []
        page.on("request", lambda r: net_log.append(f"REQ {r.method} {r.url[:120]}") if any(k in r.url.lower() for k in ['sheet', 'pdf', 'download', 'droom', 'output']) else None)
        page.on("response", lambda r: net_log.append(f"RES [{r.status}] {r.headers.get('content-type','')[:50]} {r.url[:100]}") if r.status == 200 and any(k in r.headers.get('content-type','').lower() for k in ['pdf','octet','zip','stream']) else None)

        try:
            async with page.expect_download(timeout=20000) as dl_info:
                await page.locator('#btn-yikkatudownload').click()
            dl = await dl_info.value
            fname = dl.suggested_filename
            save_path = str(OUT_DIR / fname)
            await dl.save_as(save_path)
            import os
            size = os.path.getsize(save_path)
            print(f"  ✓ ダウンロード: {fname} ({size:,} bytes)")
            with open(save_path, 'rb') as f:
                hdr = f.read(10)
            print(f"  ヘッダー: {hdr}")
        except Exception as dl_err:
            print(f"  ダウンロードエラー({type(dl_err).__name__}): {dl_err}")
            await asyncio.sleep(4)
            print(f"  現在URL: {page.url}")
            print(f"  タブ数: {len(ctx.pages)}")

            # 現在ページのテキスト（エラーメッセージ確認）
            cur_text = await page.evaluate("() => document.body.innerText.substring(0, 500)")
            print(f"  ページテキスト: {cur_text}")

            # alertが出ていないか
            for i, p in enumerate(ctx.pages):
                print(f"  タブ{i}: {p.url}")

        print(f"\nネットワークログ:")
        for r in net_log:
            print(f"  {r}")

        # 個別D-roomシートボタンを試す
        print(f"\n=== 個別D-roomシートボタン ===")
        # チェックボックスなしで個別ボタンをクリック
        sheet_btns = page.locator('button:has-text("D-roomシート")')
        cnt = await sheet_btns.count()
        print(f"D-roomシートボタン数: {cnt}")

        if cnt > 0:
            print(f"  1件目をクリック...")
            # ボタンのデータ属性を確認
            btn_data = await sheet_btns.first.evaluate("""
                el => {
                    const attrs = {};
                    for (const a of el.attributes) attrs[a.name] = a.value;
                    return attrs;
                }
            """)
            print(f"  ボタン属性: {btn_data}")

            # jQuery イベントハンドラを確認
            jquery_handlers = await page.evaluate("""
                () => {
                    const btns = document.querySelectorAll('button');
                    for (const btn of btns) {
                        if (btn.textContent.trim() === 'D-roomシート') {
                            const data = jQuery ? jQuery._data(btn, 'events') : null;
                            return data ? JSON.stringify(data).substring(0,200) : 'no jquery data';
                        }
                    }
                    return 'not found';
                }
            """)
            print(f"  jQuery handlers: {jquery_handlers}")

            try:
                async with page.expect_download(timeout=15000) as dl_info:
                    await sheet_btns.first.click()
                dl = await dl_info.value
                fname = dl.suggested_filename
                save_path = str(OUT_DIR / fname)
                await dl.save_as(save_path)
                print(f"  ✓ 個別DL: {fname}")
            except Exception as e:
                print(f"  個別DL失敗: {e}")
                await asyncio.sleep(3)
                print(f"  URL: {page.url}")
                for i, p in enumerate(ctx.pages):
                    u = p.url
                    print(f"    タブ{i}: {u}")
                    if i > 0:
                        try:
                            t = await p.evaluate("() => document.body.innerText")
                            print(f"    テキスト(先頭200): {t[:200]}")
                            await p.screenshot(path=str(OUT_DIR / f"D2_tab{i}.png"))
                        except Exception:
                            pass

        print(f"\n=== 完了 ===")
        await browser.close()

asyncio.run(main())
