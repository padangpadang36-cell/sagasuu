# -*- coding: utf-8 -*-
"""リアブロ (リアネットプロ) 物件詳細PDFダウンロードの調査"""
import sys, io, asyncio
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import os
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv(Path(__file__).parent.parent / ".env")
REABRO_URL  = "https://www.realnetpro.com/index.php"
REABRO_ID   = os.getenv("REABRO_ID", "")
REABRO_PASS = os.getenv("REABRO_PASS", "")

OUT_DIR = Path(__file__).parent / "デバッグ" / "reabro"
OUT_DIR.mkdir(parents=True, exist_ok=True)

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, channel="chrome", slow_mo=400)
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 900}, locale="ja-JP",
            accept_downloads=True)
        page = await ctx.new_page()

        # ── ログイン ──
        print(f"ログインページへ: {REABRO_URL}")
        await page.goto(REABRO_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)
        await page.screenshot(path=str(OUT_DIR / "01_login.png"))

        # ページタイトル確認
        title = await page.title()
        print(f"ページタイトル: {title}")
        body_text = await page.evaluate("() => document.body.innerText")
        print(f"ページテキスト(先頭500):\n{body_text[:500]}")

        # フォームフィールド
        fields = await page.evaluate("""
            () => Array.from(document.querySelectorAll('input')).map(i => ({
                name: i.name, id: i.id, type: i.type, placeholder: i.placeholder
            }))
        """)
        print(f"\nログインフォームフィールド:")
        for f in fields:
            print(f"  {f}")

        # ID・パスワード入力
        try:
            id_el = page.locator('input[name="id"], input[name*="user"], input[name*="login"]').first
            if not await id_el.is_visible(timeout=3000):
                id_el = page.locator('input[type="text"]').first
            await id_el.fill(REABRO_ID)
            print("  ID入力")
        except Exception as e:
            print(f"  ID入力エラー: {e}")

        try:
            await page.locator('input[type="password"]').fill(REABRO_PASS)
            print("  パスワード入力")
        except Exception as e:
            print(f"  パスワード入力エラー: {e}")

        await page.screenshot(path=str(OUT_DIR / "02_form_filled.png"))

        # ログインボタン
        for sel in ['input[type="submit"]', 'button[type="submit"]',
                    'button:has-text("ログイン")', 'a:has-text("ログイン")',
                    'input[value="ログイン"]', 'input[value*="login"]']:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=2000):
                    await el.click()
                    print(f"  ログインボタン: {sel}")
                    break
            except Exception:
                continue
        else:
            await page.keyboard.press("Enter")
            print("  Enter送信")

        try:
            await page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            pass
        await asyncio.sleep(3)
        print(f"\nログイン後URL: {page.url}")
        await page.screenshot(path=str(OUT_DIR / "03_after_login.png"))

        title = await page.title()
        body_text = await page.evaluate("() => document.body.innerText")
        print(f"タイトル: {title}")
        print(f"テキスト(先頭1000):\n{body_text[:1000]}")

        # ナビゲーション確認
        links = await page.evaluate("""
            () => Array.from(document.querySelectorAll('a')).map(a => ({
                text: a.textContent.trim().substring(0,40),
                href: a.href.substring(0,80)
            })).filter(l => l.text || l.href).slice(0, 30)
        """)
        print(f"\nリンク一覧:")
        for l in links:
            print(f"  {l['text']} → {l['href']}")

        # 物件検索へ
        print(f"\n=== 物件検索 ===")
        for text in ['物件検索', '空室検索', '物件一覧', '賃貸物件']:
            try:
                el = page.get_by_text(text).first
                if await el.is_visible(timeout=2000):
                    await el.click()
                    await asyncio.sleep(2)
                    print(f"  {text}クリック → {page.url}")
                    break
            except Exception:
                continue

        await page.screenshot(path=str(OUT_DIR / "04_search.png"))
        html = await page.content()
        (OUT_DIR / "search_page.html").write_text(html[:15000], encoding='utf-8', errors='replace')
        body_text = await page.evaluate("() => document.body.innerText")
        print(f"\n検索ページテキスト(先頭2000):\n{body_text[:2000]}")

        # フォームフィールド確認
        form_fields = await page.evaluate("""
            () => {
                const items = [];
                for (const el of document.querySelectorAll('input, select, textarea')) {
                    const ph = el.placeholder || '';
                    const nm = el.name || el.id || '';
                    const lb_el = document.querySelector('label[for="' + el.id + '"]');
                    const lb = lb_el ? lb_el.textContent.trim().substring(0,20) : '';
                    items.push({tag: el.tagName, type: el.type || '', name: nm.substring(0,20), placeholder: ph.substring(0,20), label: lb});
                }
                return items.slice(0, 30);
            }
        """)
        print("\nフォームフィールド:")
        for f in form_fields:
            print(f"  {f}")

        # 検索実行（条件なし全件）
        for sel in ['input[value="検索"]', 'input[value*="検索"]', 'button:has-text("検索")',
                    'input[type="submit"]', 'button[type="submit"]']:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=2000):
                    await el.click()
                    print(f"  検索ボタン: {sel}")
                    break
            except Exception:
                continue

        await asyncio.sleep(4)
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass
        await asyncio.sleep(2)
        print(f"\n検索結果URL: {page.url}")
        await page.screenshot(path=str(OUT_DIR / "05_results.png"))

        body_text = await page.evaluate("() => document.body.innerText")
        print(f"検索結果テキスト(先頭2000):\n{body_text[:2000]}")

        # 1件目の物件詳細へ
        print(f"\n=== 1件目詳細 ===")
        detail_links = await page.evaluate("""
            () => {
                const items = [];
                for (const a of document.querySelectorAll('a')) {
                    const t = a.textContent.trim();
                    const h = a.href || '';
                    if (t.includes('詳細') || h.includes('detail') || h.includes('bukken') || h.includes('property')) {
                        items.push({text: t.substring(0,40), href: h.substring(0,80)});
                    }
                }
                return items.slice(0, 10);
            }
        """)
        print(f"詳細リンク: {len(detail_links)}件")
        for l in detail_links:
            print(f"  {l}")

        # 最初の詳細リンクをクリック
        if detail_links:
            await page.goto(detail_links[0]['href'], wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(3)
        else:
            # 最初の物件行をクリック
            try:
                rows = page.locator('tr, .result-row, .bukken-row, li.bukken').first
                await rows.click()
                await asyncio.sleep(3)
            except Exception:
                pass

        print(f"詳細URL: {page.url}")
        await page.screenshot(path=str(OUT_DIR / "06_detail.png"))

        html = await page.content()
        (OUT_DIR / "detail.html").write_text(html[:20000], encoding='utf-8', errors='replace')

        body_text = await page.evaluate("() => document.body.innerText")
        print(f"\n詳細テキスト(先頭2000):\n{body_text[:2000]}")

        # 左サイドバーのメニューを確認
        print(f"\n=== 左サイドバー / メニュー ===")
        sidebar = await page.evaluate("""
            () => {
                // 左サイドバーまたはナビゲーション
                const navSels = ['nav', '.nav', '.sidebar', '.side', '.left', '#nav', '#sidebar',
                                  '.menu', '#menu', 'aside', '.subnav'];
                for (const sel of navSels) {
                    const el = document.querySelector(sel);
                    if (el) return {sel: sel, text: el.innerText.substring(0,500)};
                }
                return null;
            }
        """)
        if sidebar:
            print(f"サイドバー({sidebar['sel']}):\n{sidebar['text']}")

        # 全リンク・ボタン（PDFや印刷関連を優先）
        all_items = await page.evaluate("""
            () => {
                const items = [];
                for (const el of document.querySelectorAll('a, button, input[type="button"], input[type="submit"]')) {
                    const t = (el.textContent.trim() || el.value || '').substring(0,50);
                    const h = (el.href || '').substring(0,80);
                    const oc = (el.getAttribute('onclick') || '').substring(0,60);
                    items.push({text: t, href: h, onclick: oc});
                }
                return items;
            }
        """)
        print(f"\n=== 全リンク・ボタン ({len(all_items)}件) ===")
        keywords = ['pdf', '印刷', 'print', '詳細資料', '元付', '出力', 'download', '地図', '資料']
        for item in all_items:
            combined = (item['text'] + item['href'] + item['onclick']).lower()
            if any(kw.lower() in combined for kw in keywords):
                print(f"  ★ {item['text']} | {item['href']} | {item['onclick']}")
        print("--- 全件 ---")
        for item in all_items:
            print(f"  {item['text'][:30]} | {item['href'][:50]}")

        # 「詳細資料印刷出力」「元付詳細資料出力」「地図」のクリック試行
        print(f"\n=== 詳細資料印刷出力 クリック試行 ===")
        for text in ['詳細資料印刷出力', '詳細資料', '元付詳細資料出力', '元付詳細資料', '地図', '現地地図']:
            try:
                el = page.get_by_text(text).first
                if await el.is_visible(timeout=2000):
                    print(f"  '{text}'が見つかりました")
                    try:
                        async with ctx.expect_download(timeout=8000) as dl_info:
                            await el.click()
                        dl = await dl_info.value
                        print(f"  ✓ ダウンロード: {dl.suggested_filename}")
                        save_path = str(OUT_DIR / dl.suggested_filename)
                        await dl.save_as(save_path)
                    except Exception as dl_err:
                        print(f"  ダウンロードなし({dl_err})")
                        await asyncio.sleep(2)
                        print(f"  クリック後URL: {page.url}")
                        print(f"  タブ数: {len(ctx.pages)}")
                        if len(ctx.pages) > 1:
                            new_tab = [p for p in ctx.pages if p != page][-1]
                            print(f"  新タブURL: {new_tab.url}")
                            await new_tab.screenshot(path=str(OUT_DIR / f"new_tab_{text[:10]}.png"))
                    break
            except Exception:
                continue

        input("\n[確認] Enterで終了...")
        await browser.close()

asyncio.run(main())
