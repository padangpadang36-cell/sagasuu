# -*- coding: utf-8 -*-
"""D-Room 物件リスト→Droomシート一括出力の詳細調査"""
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

    # 強制ログイン
    if "CheckLogin" in page.url:
        try:
            await page.locator('#forcepassword').fill(DROOM_PASS)
        except Exception:
            pass
        try:
            await page.locator('#forceloginok').click()
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            await asyncio.sleep(3)
        except Exception as e:
            print(f"強制ログインエラー: {e}")

    print(f"ログイン後URL: {page.url}")
    return "login" not in page.url.lower()

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, channel="chrome", slow_mo=300)
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 900}, locale="ja-JP",
            accept_downloads=True)
        page = await ctx.new_page()

        await login_droom(page)
        await page.screenshot(path=str(OUT_DIR / "A1_logged_in.png"))

        # お知らせページ → メニュー → 物件リスト
        try:
            await page.get_by_text("メニューに進む").first.click()
            await asyncio.sleep(2)
            print(f"メニューURL: {page.url}")
        except Exception:
            pass

        # 物件リストへ直接遷移
        await page.goto(ROOM_LIST_URL, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)
        print(f"物件リストURL: {page.url}")
        await page.screenshot(path=str(OUT_DIR / "A2_roomlist.png"))

        body_text = await page.evaluate("() => document.body.innerText")
        print(f"\n物件リストテキスト(先頭3000):\n{body_text[:3000]}")

        html = await page.content()
        (OUT_DIR / "roomlist.html").write_text(html[:30000], encoding='utf-8', errors='replace')

        # フォームフィールドを確認
        form_fields = await page.evaluate("""
            () => {
                const items = [];
                for (const el of document.querySelectorAll('input, select')) {
                    const lb_el = document.querySelector('label[for="'+el.id+'"]');
                    const lb = lb_el ? lb_el.textContent.trim().substring(0,20) : '';
                    items.push({
                        tag: el.tagName, type: el.type||'select',
                        name: (el.name||el.id||'').substring(0,30),
                        placeholder: (el.placeholder||'').substring(0,20),
                        label: lb,
                        value: (el.value||'').substring(0,30)
                    });
                }
                return items;
            }
        """)
        print(f"\n=== フォームフィールド ===")
        for f in form_fields:
            print(f"  {f}")

        # 全ボタン・リンク
        all_items = await page.evaluate("""
            () => Array.from(document.querySelectorAll('a, button, input[type="button"], input[type="submit"], input[type="image"]'))
                .map(el => ({
                    text: (el.textContent.trim() || el.value || el.alt || '').substring(0,60),
                    href: (el.href || '').substring(0,100),
                    onclick: (el.getAttribute('onclick') || '').substring(0,80),
                    id: (el.id||'').substring(0,30)
                }))
                .filter(e => e.text || e.href)
        """)
        print(f"\n=== 全ボタン・リンク ({len(all_items)}件) ===")
        keywords = ['droom', 'ドルーム', '一括', 'シート', '出力', 'pdf', '印刷']
        for item in all_items:
            combined = (item['text'] + item['href'] + item['onclick']).lower()
            if any(kw.lower() in combined for kw in keywords):
                print(f"  ★ {item}")
        print("--- 全件 ---")
        for item in all_items:
            print(f"  {item['text'][:40]} | {item['href'][:60]} | {item['onclick'][:40]}")

        # 検索実行（条件なし）
        print(f"\n=== 検索実行 ===")
        # selectボックスの内容を確認
        selects = await page.evaluate("""
            () => {
                const results = [];
                for (const sel of document.querySelectorAll('select')) {
                    const opts = Array.from(sel.options).map(o => ({v:o.value, t:o.text.trim()}));
                    results.push({name: sel.name||sel.id, options: opts.slice(0,10)});
                }
                return results;
            }
        """)
        print(f"セレクトボックス:")
        for s in selects:
            print(f"  {s['name']}: {s['options']}")

        # 検索ボタンクリック
        for sel in ['input[value="検索"]', 'input[value*="検索"]', 'button:has-text("検索")',
                    'a:has-text("検索")', 'input[type="submit"]']:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=2000):
                    await el.click()
                    print(f"  検索クリック: {sel}")
                    break
            except Exception:
                continue

        await asyncio.sleep(5)
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass
        await asyncio.sleep(2)

        print(f"\n検索結果URL: {page.url}")
        await page.screenshot(path=str(OUT_DIR / "A3_results.png"))
        html = await page.content()
        (OUT_DIR / "results.html").write_text(html[:40000], encoding='utf-8', errors='replace')

        body_text = await page.evaluate("() => document.body.innerText")
        print(f"\n検索結果テキスト(先頭3000):\n{body_text[:3000]}")

        # チェックボックスを確認して選択
        cbs = await page.locator('input[type="checkbox"]').count()
        print(f"\nチェックボックス数: {cbs}")
        if cbs > 0:
            # 全選択チェックボックスを探す
            all_select = await page.locator('input[type="checkbox"][id*="all"], input[type="checkbox"][id*="All"], input[type="checkbox"][name*="all"]').count()
            if all_select > 0:
                await page.locator('input[type="checkbox"][id*="all"], input[type="checkbox"][id*="All"], input[type="checkbox"][name*="all"]').first.check()
                print("  全選択チェックボックスをON")
                await asyncio.sleep(1)
            else:
                # 個別に最初の3件を選択
                for i in range(min(3, cbs)):
                    try:
                        await page.locator('input[type="checkbox"]').nth(i).check()
                        print(f"  CB[{i}]チェック")
                    except Exception as e:
                        print(f"  CB[{i}]エラー: {e}")
            await asyncio.sleep(1)
            await page.screenshot(path=str(OUT_DIR / "A4_checked.png"))

        # チェック後の全ボタン・リンク
        all_items2 = await page.evaluate("""
            () => Array.from(document.querySelectorAll('a, button, input[type="button"], input[type="submit"], input[type="image"]'))
                .map(el => ({
                    text: (el.textContent.trim() || el.value || el.alt || '').substring(0,80),
                    href: (el.href || '').substring(0,100),
                    onclick: (el.getAttribute('onclick') || '').substring(0,100),
                    id: (el.id||'').substring(0,30),
                    name: (el.name||'').substring(0,30)
                }))
                .filter(e => e.text || e.href)
        """)
        print(f"\n=== チェック後 全ボタン・リンク ({len(all_items2)}件) ===")
        keywords2 = ['droom', 'ドルーム', '一括', 'シート', '出力', 'pdf', '印刷', 'download']
        for item in all_items2:
            combined = (item['text'] + item['href'] + item['onclick']).lower()
            if any(kw.lower() in combined for kw in keywords2):
                print(f"  ★ {item}")
        print("--- 全件 ---")
        for item in all_items2:
            print(f"  [{item['id']}] {item['text'][:40]} | {item['href'][:60]} | {item['onclick'][:60]}")

        # Droomシートボタンをクリック
        print(f"\n=== Droomシート一括出力クリック試行 ===")
        droom_found = False
        for text in ['Droomシート一括出力', 'D-roomシート', 'droomシート', 'Droom', '一括出力']:
            try:
                el = page.get_by_text(text, exact=False).first
                if await el.is_visible(timeout=1000):
                    print(f"  '{text}'発見")
                    try:
                        async with ctx.expect_download(timeout=15000) as dl_info:
                            await el.click()
                        dl = await dl_info.value
                        fname = dl.suggested_filename
                        save_path = str(OUT_DIR / fname)
                        await dl.save_as(save_path)
                        print(f"  ✓ ダウンロード: {fname} → {save_path}")
                        droom_found = True
                    except Exception as dl_err:
                        print(f"  ダウンロードなし({dl_err})")
                        await asyncio.sleep(3)
                        print(f"  現在URL: {page.url}")
                        print(f"  タブ数: {len(ctx.pages)}")
                        for i, p in enumerate(ctx.pages):
                            print(f"    タブ{i}: {p.url}")
                        if len(ctx.pages) > 1:
                            new_tab = ctx.pages[-1]
                            await new_tab.screenshot(path=str(OUT_DIR / "A5_new_tab.png"))
                            t = await new_tab.evaluate("() => document.body.innerText")
                            print(f"    新タブテキスト: {t[:300]}")
                    break
            except Exception:
                continue

        if not droom_found:
            print("  Droomシートボタンが見つかりませんでした")

        # 1件の物件詳細も確認
        print(f"\n=== 物件詳細確認 ===")
        detail_hrefs = await page.evaluate("""
            () => {
                const hrefs = [];
                for (const a of document.querySelectorAll('a')) {
                    const h = a.href || '';
                    if (h.includes('/room/') && !h.endsWith('#') && h !== window.location.href) {
                        hrefs.push({text: a.textContent.trim().substring(0,40), href: h.substring(0,100)});
                    }
                }
                return hrefs.slice(0, 5);
            }
        """)
        print(f"物件リンク: {detail_hrefs}")

        if detail_hrefs:
            detail_url = detail_hrefs[0]['href']
            await page.goto(detail_url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(3)
            print(f"詳細URL: {page.url}")
            await page.screenshot(path=str(OUT_DIR / "A6_detail.png"))

            html = await page.content()
            (OUT_DIR / "detail.html").write_text(html[:30000], encoding='utf-8', errors='replace')

            body_text = await page.evaluate("() => document.body.innerText")
            print(f"\n詳細テキスト(先頭2000):\n{body_text[:2000]}")

            detail_items = await page.evaluate("""
                () => Array.from(document.querySelectorAll('a, button, input[type="button"], input[type="submit"]'))
                    .map(el => ({
                        text: (el.textContent.trim() || el.value || '').substring(0,80),
                        href: (el.href || '').substring(0,100),
                        onclick: (el.getAttribute('onclick') || '').substring(0,100),
                        id: (el.id||'').substring(0,30)
                    }))
                    .filter(e => e.text || e.href)
            """)
            print(f"\n=== 詳細ページ ボタン・リンク ({len(detail_items)}件) ===")
            keywords3 = ['droom', 'ドルーム', '一括', 'シート', '出力', 'pdf', '印刷', 'sheet']
            for item in detail_items:
                combined = (item['text'] + item['href'] + item['onclick']).lower()
                if any(kw.lower() in combined for kw in keywords3):
                    print(f"  ★ {item}")
            print("--- 全件 ---")
            for item in detail_items:
                print(f"  [{item['id']}] {item['text'][:50]} | {item['href'][:60]}")

        print(f"\n=== 完了 ===")
        await browser.close()

asyncio.run(main())
