# -*- coding: utf-8 -*-
"""D-Room (大和living) 物件検索・Droomシート一括出力ボタンの調査 v2"""
import sys, io, asyncio
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import os
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv(Path(__file__).parent.parent / ".env")
DROOM_URL    = "https://anavi.daiwaliving.co.jp/dp/login"
DROOM_TENPO  = os.getenv("DROOM_TENPO", "")   # 企業ID
DROOM_TANTO  = os.getenv("DROOM_TANTO", "")   # 社員ID
DROOM_PASS   = os.getenv("DROOM_PASS", "")

OUT_DIR = Path(__file__).parent / "デバッグ" / "droom"
OUT_DIR.mkdir(parents=True, exist_ok=True)

async def login_droom(page, ctx):
    """D-Roomログイン（強制ログイン対応）"""
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
    print(f"ログイン後URL: {page.url}")

    # 強制ログインが必要な場合
    if "CheckLogin" in page.url or "forcelogin" in page.url.lower():
        try:
            force_btn = page.locator('button:has-text("強制ログインする"), input[value*="強制"]').first
            if await force_btn.is_visible(timeout=3000):
                # 強制ログインフォームにもパスワードが必要かも
                try:
                    await page.locator('#forcepassword').fill(DROOM_PASS)
                except Exception:
                    pass
                await force_btn.click()
                print("  強制ログインクリック")
                try:
                    await page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass
                await asyncio.sleep(3)
                print(f"  強制ログイン後URL: {page.url}")
        except Exception as e:
            print(f"  強制ログインエラー: {e}")

    return "login" not in page.url.lower() or "CheckLogin" not in page.url

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, channel="chrome", slow_mo=300)
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 900}, locale="ja-JP",
            accept_downloads=True)
        page = await ctx.new_page()

        # ── ログイン ──
        ok = await login_droom(page, ctx)
        print(f"ログイン状態: {'OK' if ok else 'NG'}")
        await page.screenshot(path=str(OUT_DIR / "01_after_login.png"))

        # メインページを確認
        print(f"\n現在URL: {page.url}")
        body_text = await page.evaluate("() => document.body.innerText")
        print(f"ページテキスト(先頭1000):\n{body_text[:1000]}")

        html = await page.content()
        (OUT_DIR / "main.html").write_text(html[:20000], encoding='utf-8', errors='replace')

        # ナビゲーションリンクを確認
        links = await page.evaluate("""
            () => Array.from(document.querySelectorAll('a')).map(a => ({
                text: a.textContent.trim().substring(0,40),
                href: a.href.substring(0,100)
            })).filter(l => l.text || l.href)
        """)
        print(f"\n=== 全リンク ({len(links)}件) ===")
        for l in links:
            print(f"  {l['text']} → {l['href']}")

        # お知らせページ → メニューへ
        print(f"\n=== メニューへ ===")
        try:
            menu_btn = page.get_by_text("メニューに進む", exact=False).first
            if await menu_btn.is_visible(timeout=3000):
                await menu_btn.click()
                await asyncio.sleep(3)
                print(f"  メニューに進む → {page.url}")
        except Exception as e:
            print(f"  メニューボタンエラー: {e}")

        await page.screenshot(path=str(OUT_DIR / "01b_menu.png"))
        body_text2 = await page.evaluate("() => document.body.innerText")
        print(f"メニューテキスト(先頭500):\n{body_text2[:500]}")

        # メニューの全リンクを確認
        menu_links = await page.evaluate("""
            () => Array.from(document.querySelectorAll('a')).map(a => ({
                text: a.textContent.trim().substring(0,50),
                href: a.href.substring(0,100)
            })).filter(l => l.text || l.href)
        """)
        print(f"\nメニューリンク:")
        for l in menu_links:
            print(f"  {l['text']} → {l['href']}")

        # 物件検索ページへ
        print(f"\n=== 物件検索へ ===")
        search_clicked = False
        for text in ['物件検索', '空室検索', '物件一覧', '空室照会']:
            try:
                el = page.get_by_text(text, exact=False).first
                if await el.is_visible(timeout=2000):
                    await el.click()
                    await asyncio.sleep(3)
                    print(f"  '{text}'クリック → {page.url}")
                    search_clicked = True
                    break
            except Exception:
                continue

        if not search_clicked:
            print("  検索ナビが見つかりません - メニューリンクから物件検索URL確認")

        await page.screenshot(path=str(OUT_DIR / "02_search_page.png"))
        print(f"検索ページURL: {page.url}")
        body_text = await page.evaluate("() => document.body.innerText")
        print(f"\n検索ページテキスト(先頭2000):\n{body_text[:2000]}")

        html = await page.content()
        (OUT_DIR / "search_page.html").write_text(html[:30000], encoding='utf-8', errors='replace')

        # 全ナビリンクを確認
        all_links = await page.evaluate("""
            () => Array.from(document.querySelectorAll('a')).map(a => ({
                text: a.textContent.trim().substring(0,50),
                href: a.href.substring(0,100)
            })).filter(l => l.text || l.href)
        """)
        print(f"\n=== 全リンク ({len(all_links)}件) ===")
        for l in all_links:
            print(f"  {l['text']} → {l['href']}")

        # 検索フォームを操作
        print(f"\n=== 検索フォーム ===")
        form_info = await page.evaluate("""
            () => {
                const inputs = [];
                for (const el of document.querySelectorAll('input, select, textarea')) {
                    const lb_el = document.querySelector('label[for="'+el.id+'"]');
                    const lb = lb_el ? lb_el.textContent.trim().substring(0,20) : '';
                    inputs.push({
                        tag: el.tagName, type: el.type||'',
                        name: (el.name||el.id||'').substring(0,30),
                        placeholder: (el.placeholder||'').substring(0,20),
                        label: lb
                    });
                }
                return inputs;
            }
        """)
        for f in form_info:
            print(f"  {f}")

        # 検索実行
        for sel in ['input[value="検索"]', 'input[value*="検索"]', 'button:has-text("検索")',
                    'input[type="submit"]', 'button[type="submit"]']:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=2000):
                    await el.click()
                    print(f"  検索実行: {sel}")
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
        await page.screenshot(path=str(OUT_DIR / "03_results.png"))
        html = await page.content()
        (OUT_DIR / "results.html").write_text(html[:30000], encoding='utf-8', errors='replace')

        body_text = await page.evaluate("() => document.body.innerText")
        print(f"\n検索結果テキスト(先頭3000):\n{body_text[:3000]}")

        # チェックボックスを確認
        cbs = await page.locator('input[type="checkbox"]').count()
        print(f"\nチェックボックス数: {cbs}")

        # 1件以上チェック
        if cbs > 0:
            for i in range(min(3, cbs)):
                try:
                    await page.locator('input[type="checkbox"]').nth(i).check()
                except Exception:
                    pass
            print(f"  {min(3, cbs)}件チェック")
            await asyncio.sleep(1)
            await page.screenshot(path=str(OUT_DIR / "04_checked.png"))

        # 全ボタン・リンクを確認
        all_btns = await page.evaluate("""
            () => Array.from(document.querySelectorAll('a, button, input[type="button"], input[type="submit"], input[type="image"]'))
                .map(el => ({
                    text: (el.textContent.trim() || el.value || el.alt || '').substring(0,60),
                    href: (el.href || '').substring(0,100),
                    onclick: (el.getAttribute('onclick') || '').substring(0,80),
                    id: (el.id || '').substring(0,30),
                    name: (el.name || '').substring(0,30)
                }))
                .filter(e => e.text || e.href)
        """)
        print(f"\n=== 全ボタン・リンク ({len(all_btns)}件) ===")
        keywords = ['droom', 'ドルーム', '一括', 'シート', '出力', 'pdf', '印刷', 'download', '資料']
        for b in all_btns:
            combined = (b['text'] + b['href'] + b['onclick']).lower()
            if any(kw in combined for kw in keywords):
                print(f"  ★ {b}")
        print("--- 全件 ---")
        for b in all_btns:
            print(f"  {b['text'][:40]} | {b['href'][:60]} | {b['onclick'][:40]}")

        # Droomシート一括出力を探してクリック
        droom_keywords = ['droom', 'Droom', 'D-room', 'ドルーム', 'シート', '一括出力']
        for kw in droom_keywords:
            try:
                el = page.get_by_text(kw, exact=False).first
                if await el.is_visible(timeout=1000):
                    print(f"\n=== '{kw}'ボタンを発見・クリック ===")
                    try:
                        async with ctx.expect_download(timeout=15000) as dl_info:
                            await el.click()
                        dl = await dl_info.value
                        fname = dl.suggested_filename
                        save_path = str(OUT_DIR / fname)
                        await dl.save_as(save_path)
                        print(f"✓ ダウンロード成功: {fname}")
                        print(f"  保存: {save_path}")
                    except Exception as dl_err:
                        print(f"  ダウンロードなし({dl_err})")
                        await asyncio.sleep(3)
                        print(f"  現在URL: {page.url}")
                        print(f"  タブ数: {len(ctx.pages)}")
                        for i, p in enumerate(ctx.pages):
                            print(f"    タブ{i}: {p.url}")
                    break
            except Exception:
                continue

        # 1件目の物件詳細へ
        print(f"\n=== 1件目詳細 ===")
        detail_links = await page.evaluate("""
            () => {
                const hrefs = [];
                for (const a of document.querySelectorAll('a')) {
                    const h = a.href || '';
                    const t = a.textContent.trim();
                    if (h && h !== window.location.href && !h.endsWith('#')) {
                        hrefs.push({text: t.substring(0,40), href: h.substring(0,100)});
                    }
                }
                return hrefs.slice(0, 20);
            }
        """)
        print(f"リンク一覧:")
        for l in detail_links:
            print(f"  {l['text']} → {l['href']}")

        # 詳細ページへ遷移試行
        detail_nav_done = False
        for l in detail_links:
            if any(kw in l['href'].lower() for kw in ['detail', 'bukken', 'property', 'room']):
                await page.goto(l['href'], wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(3)
                print(f"  詳細ページへ: {page.url}")
                detail_nav_done = True
                break

        if not detail_nav_done and detail_links:
            # 最初のリンク
            await page.goto(detail_links[0]['href'], wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(3)
            print(f"  詳細(先頭)ページ: {page.url}")

        await page.screenshot(path=str(OUT_DIR / "05_detail.png"))
        html = await page.content()
        (OUT_DIR / "detail.html").write_text(html[:30000], encoding='utf-8', errors='replace')

        body_text = await page.evaluate("() => document.body.innerText")
        print(f"\n詳細テキスト(先頭3000):\n{body_text[:3000]}")

        # 詳細ページの全リンク・ボタン
        detail_items = await page.evaluate("""
            () => Array.from(document.querySelectorAll('a, button, input[type="button"], input[type="submit"]'))
                .map(el => ({
                    text: (el.textContent.trim() || el.value || '').substring(0,60),
                    href: (el.href || '').substring(0,100),
                    onclick: (el.getAttribute('onclick') || '').substring(0,80),
                }))
                .filter(e => e.text || e.href)
        """)
        print(f"\n=== 詳細ページ 全ボタン・リンク ({len(detail_items)}件) ===")
        keywords2 = ['droom', 'ドルーム', '一括', 'シート', '出力', 'pdf', '印刷', 'download']
        for item in detail_items:
            combined = (item['text'] + item['href'] + item['onclick']).lower()
            if any(kw in combined for kw in keywords2):
                print(f"  ★ {item}")
        print("--- 全件 ---")
        for item in detail_items:
            print(f"  {item['text'][:40]} | {item['href'][:60]}")

        print("\n=== 完了 ===")
        await browser.close()

asyncio.run(main())
