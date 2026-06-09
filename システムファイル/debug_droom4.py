# -*- coding: utf-8 -*-
"""D-Room 選択ボタン → Droomシート一括出力の動作を確認"""
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
    print(f"ログイン後URL: {page.url}")

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

        # 物件リストへ（大阪市北区で検索）
        await page.goto(ROOM_LIST_URL, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)

        # エリアで検索
        try:
            await page.locator('input[name="address"]').fill("大阪市北区")
        except Exception:
            pass
        # 家賃上限
        try:
            await page.locator('input[name="rentTo"]').fill("8")
        except Exception:
            pass

        # 検索フォームsubmit
        await page.evaluate("""
            () => {
                const f = document.querySelector('form[action*="RoomList"]') ||
                         document.querySelector('form');
                if (f) f.submit();
            }
        """)
        await asyncio.sleep(5)
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass
        await asyncio.sleep(2)

        print(f"検索結果URL: {page.url}")
        print(f"検索件数確認:")
        cnt_text = await page.evaluate("""
            () => {
                const el = document.querySelector('.bb-count, .count, [class*="count"]');
                return el ? el.textContent.trim() : document.body.innerText.substring(0, 500);
            }
        """)
        print(f"  {cnt_text[:200]}")

        # 「選択」ボタンの構造を詳しく確認
        print(f"\n=== 「選択」ボタン詳細 ===")
        select_btns = await page.evaluate("""
            () => {
                const results = [];
                for (const el of document.querySelectorAll('button, a, input[type="button"]')) {
                    const t = (el.textContent.trim() || el.value || '').replace(/\\s+/g,' ');
                    if (t === '選択' || t.includes('選択') && t.length < 5) {
                        results.push({
                            tag: el.tagName,
                            id: el.id || '',
                            name: el.name || '',
                            text: t,
                            onclick: (el.getAttribute('onclick') || '').substring(0,150),
                            'data-room-id': el.getAttribute('data-room-id') || '',
                            'data-building-id': el.getAttribute('data-building-id') || '',
                            class: el.className || '',
                            'data-id': el.getAttribute('data-id') || '',
                            'data-select': el.getAttribute('data-select') || '',
                            'data-nyukyo': el.getAttribute('data-nyukyo') || '',
                        });
                    }
                }
                return results;
            }
        """)
        print(f"選択ボタン数: {len(select_btns)}")
        for b in select_btns:
            print(f"  {b}")

        # 全「選択」ボタンのdata属性を確認（より広く検索）
        all_data_attrs = await page.evaluate("""
            () => {
                const results = [];
                // 「選択」テキストを含む全要素
                const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
                while (walker.nextNode()) {
                    const el = walker.currentNode;
                    if (el.textContent.trim() === '選択') {
                        const attrs = {};
                        for (const attr of el.attributes) {
                            attrs[attr.name] = attr.value.substring(0, 50);
                        }
                        results.push({tag: el.tagName, attrs: attrs});
                    }
                }
                return results.slice(0, 10);
            }
        """)
        print(f"\n全「選択」要素の属性:")
        for item in all_data_attrs:
            print(f"  {item['tag']}: {item['attrs']}")

        # 検索件数をカウント
        result_count = await page.evaluate("""
            () => {
                // 「件中」テキストを含む要素を探す
                const text = document.body.innerText;
                const m = text.match(/(\\d+)\\s*件中/);
                return m ? parseInt(m[1]) : 0;
            }
        """)
        print(f"\n検索結果件数: {result_count}")

        if result_count == 0:
            print("検索結果なし。条件を緩めて再検索...")
            await page.goto(ROOM_LIST_URL, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(3)
            await page.evaluate("""
                () => {
                    const f = document.querySelector('form');
                    if (f) f.submit();
                }
            """)
            await asyncio.sleep(5)
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception:
                pass
            await asyncio.sleep(2)
            print(f"全件検索URL: {page.url}")

        await page.screenshot(path=str(OUT_DIR / "C1_results.png"))

        # 「選択」ボタンをクリックして選択状態にする
        print(f"\n=== 選択ボタンをクリック ===")
        select_btn_locator = page.locator('button.bb-select-check, button[class*="select"], button:has-text("選択")').first
        try:
            if await select_btn_locator.is_visible(timeout=3000):
                # クリック前の選択件数
                before_count = await page.locator('#select-count, [id*="count"], .select-count').first.text_content() if await page.locator('#select-count, [id*="count"]').count() > 0 else "?"
                print(f"  クリック前選択件数: {before_count}")

                await select_btn_locator.click()
                await asyncio.sleep(1)

                # クリック後のカウント確認
                after_text = await page.evaluate("() => document.body.innerText.substring(0, 300)")
                print(f"  クリック後テキスト(先頭300): {after_text}")

                await page.screenshot(path=str(OUT_DIR / "C2_after_select.png"))
        except Exception as e:
            print(f"  選択ボタンエラー: {e}")

        # D-roomシート一括出力をクリック
        print(f"\n=== D-roomシート一括出力クリック ===")
        # ネットワーク監視
        net_log = []
        page.on("request", lambda r: net_log.append(f"REQ {r.method} {r.url[:100]}"))
        page.on("response", lambda r: net_log.append(f"RES [{r.status}] ct={r.headers.get('content-type','')[:40]} {r.url[:80]}"))

        droom_btn = page.locator('#btn-yikkatudownload').first
        if await droom_btn.is_visible(timeout=3000):
            print("  #btn-yikkatudownload 発見")
            try:
                async with page.expect_download(timeout=20000) as dl_info:
                    await droom_btn.click()
                dl = await dl_info.value
                fname = dl.suggested_filename
                save_path = str(OUT_DIR / fname)
                await dl.save_as(save_path)
                print(f"  ✓ ダウンロード成功: {fname}")
                import os
                size = os.path.getsize(save_path)
                print(f"  ファイルサイズ: {size:,} bytes")
                with open(save_path, 'rb') as f:
                    hdr = f.read(10)
                print(f"  ヘッダー: {hdr}")
            except Exception as dl_err:
                print(f"  ダウンロード失敗({type(dl_err).__name__}): {dl_err}")
                await asyncio.sleep(3)
                print(f"  現在URL: {page.url}")
                print(f"  タブ数: {len(ctx.pages)}")
                for i, p in enumerate(ctx.pages):
                    print(f"    タブ{i}: {p.url}")
                    if i > 0:
                        try:
                            t = await p.evaluate("() => document.body.innerText")
                            print(f"    テキスト: {t[:200]}")
                        except Exception:
                            pass

                # dialog/alertが出ていないか確認
                print(f"\n  現在のページテキスト(先頭500):")
                print(await page.evaluate("() => document.body.innerText.substring(0, 500)"))
        else:
            print("  #btn-yikkatudownload が見えません")

        # ネットワークログ
        print(f"\nネットワークログ({len(net_log)}件):")
        for r in net_log[-30:]:
            print(f"  {r}")

        # 個別D-roomシートも試す
        print(f"\n=== 個別D-roomシートボタン ===")
        droom_sheet_btns = await page.evaluate("""
            () => {
                const results = [];
                for (const btn of document.querySelectorAll('button')) {
                    const t = btn.textContent.trim();
                    if (t === 'D-roomシート') {
                        const attrs = {};
                        for (const a of btn.attributes) attrs[a.name] = a.value.substring(0,80);
                        results.push({text: t, attrs: attrs});
                    }
                }
                return results;
            }
        """)
        print(f"個別D-roomシートボタン: {len(droom_sheet_btns)}件")
        for b in droom_sheet_btns:
            print(f"  {b}")

        if droom_sheet_btns:
            print("\n  個別D-roomシートをクリック...")
            single_btn = page.locator('button:has-text("D-roomシート")').first
            try:
                async with page.expect_download(timeout=15000) as dl_info:
                    await single_btn.click()
                dl = await dl_info.value
                fname = dl.suggested_filename
                save_path = str(OUT_DIR / fname)
                await dl.save_as(save_path)
                print(f"  ✓ 個別DL: {fname}")
                with open(save_path, 'rb') as f:
                    hdr = f.read(10)
                print(f"  ヘッダー: {hdr}")
            except Exception as e:
                print(f"  個別DL失敗({type(e).__name__}): {e}")
                await asyncio.sleep(3)
                print(f"  URL: {page.url}, タブ: {len(ctx.pages)}")
                for i, p in enumerate(ctx.pages):
                    url = p.url
                    print(f"    タブ{i}: {url}")
                    if 'sheet' in url.lower() or 'pdf' in url.lower() or 'download' in url.lower():
                        await p.screenshot(path=str(OUT_DIR / f"C3_sheet_tab.png"))
                        print(f"    → SSを保存")

        print(f"\n=== 完了 ===")
        await browser.close()

asyncio.run(main())
