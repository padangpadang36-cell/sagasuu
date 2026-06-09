# -*- coding: utf-8 -*-
"""リアプロ 住居検索→リスト検索 の構造調査"""
import sys, io, asyncio
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import os
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv(Path(__file__).parent.parent / ".env")
REABRO_LOGIN_URL = "https://www.realnetpro.com/index.php"
REABRO_BASE_URL  = "https://www.realnetpro.com"
REABRO_ID        = os.getenv("REABRO_ID", "")
REABRO_PASS      = os.getenv("REABRO_PASS", "")

OUT_DIR = Path(__file__).parent / "デバッグ" / "reabro2"
OUT_DIR.mkdir(parents=True, exist_ok=True)

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, channel="chrome", slow_mo=400)
        ctx = await browser.new_context(viewport={"width":1280,"height":900}, locale="ja-JP")
        page = await ctx.new_page()

        # ─── ログイン ───
        await page.goto(REABRO_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)
        await page.locator('input[name="id"]').fill(REABRO_ID)
        await page.locator('input[name="pass"]').fill(REABRO_PASS)
        await page.locator('button:has-text("ログイン")').first.click()
        await asyncio.sleep(3)
        print(f"ログイン後URL: {page.url}")
        await page.screenshot(path=str(OUT_DIR / "01_after_login.png"))

        # ─── メニュー構造を調査 ───
        print("\n=== メニューリンク一覧 ===")
        menu_links = await page.evaluate("""
            () => Array.from(document.querySelectorAll('a, button'))
                .map(el => ({
                    text: el.innerText.trim().replace(/\\s+/g,' ').substring(0,40),
                    href: el.href || '',
                    id: el.id || '',
                    cls: el.className.substring(0,40)
                }))
                .filter(x => x.text)
        """)
        for m in menu_links:
            print(f"  [{m['text']}] href={m['href'][:60]} id={m['id']}")

        # ─── 住居検索リンクを探してクリック ───
        print("\n=== 住居検索を探す ===")
        for keyword in ["住居検索", "住居", "物件検索", "検索", "room", "estate"]:
            try:
                el = page.get_by_text(keyword, exact=False).first
                if await el.is_visible(timeout=1000):
                    print(f"  発見: '{keyword}'")
                    href = await el.get_attribute("href") or ""
                    print(f"  href: {href}")
                    break
            except Exception:
                continue

        # 住居検索クリック
        try:
            await page.get_by_text("住居検索", exact=False).first.click()
            await asyncio.sleep(2)
            print(f"  住居検索クリック後URL: {page.url}")
            await page.screenshot(path=str(OUT_DIR / "02_juukyo_search.png"))
        except Exception as e:
            print(f"  住居検索クリック失敗: {e}")
            # サイドバーなどを探す
            try:
                await page.locator('a[href*="room"]').first.click()
                await asyncio.sleep(2)
                print(f"  roomリンク後URL: {page.url}")
            except Exception:
                pass

        # ─── リスト検索を探す ───
        print("\n=== リスト検索/マップ検索を探す ===")
        sub_links = await page.evaluate("""
            () => Array.from(document.querySelectorAll('a, button'))
                .map(el => ({
                    text: el.innerText.trim().replace(/\\s+/g,' ').substring(0,40),
                    href: el.href || ''
                }))
                .filter(x => x.text)
        """)
        for m in sub_links:
            if any(k in m['text'] for k in ['リスト', 'マップ', '検索', 'list', 'map', 'search']):
                print(f"  [{m['text']}] {m['href'][:80]}")

        # リスト検索クリック
        for label in ["リスト検索", "リスト", "一覧"]:
            try:
                el = page.get_by_text(label, exact=False).first
                if await el.is_visible(timeout=1000):
                    await el.click()
                    await asyncio.sleep(3)
                    print(f"  '{label}'クリック後URL: {page.url}")
                    await page.screenshot(path=str(OUT_DIR / "03_list_search.png"))
                    break
            except Exception:
                continue

        # ─── 検索フォームの構造を調査 ───
        print("\n=== 検索フォーム要素 ===")
        form_els = await page.evaluate("""
            () => {
                const results = [];
                for (const el of document.querySelectorAll('input, select, textarea, button[type="submit"]')) {
                    results.push({
                        tag: el.tagName,
                        type: el.type || '',
                        name: el.name || '',
                        id: el.id || '',
                        placeholder: el.placeholder || '',
                        value: (el.value || '').substring(0,30)
                    });
                }
                return results;
            }
        """)
        for f in form_els:
            print(f"  {f['tag']} name={f['name']} id={f['id']} type={f['type']} placeholder={f['placeholder']}")

        # ─── 大阪市北区で検索してみる ───
        print("\n=== 条件入力して検索 ===")
        filled = False
        for field in ['area', 'keyword', 'address', 'city', 'pref', 'addr', 'freeword']:
            try:
                el = page.locator(f'input[name="{field}"]').first
                if await el.is_visible(timeout=500):
                    await el.fill("大阪市北区")
                    print(f"  '{field}'に入力")
                    filled = True
                    break
            except Exception:
                continue

        # 都道府県セレクト
        try:
            sel = page.locator('select[name*="pref"], select[name*="ken"]').first
            if await sel.is_visible(timeout=500):
                await sel.select_option(label="大阪府")
                print("  都道府県: 大阪府を選択")
        except Exception:
            pass

        # 検索ボタン
        for btn_sel in ['button[type="submit"]', 'input[type="submit"]', 'button:has-text("検索")']:
            try:
                btn = page.locator(btn_sel).first
                if await btn.is_visible(timeout=500):
                    await btn.click()
                    await asyncio.sleep(4)
                    print(f"  検索後URL: {page.url}")
                    break
            except Exception:
                continue

        await page.screenshot(path=str(OUT_DIR / "04_search_result.png"))

        # ─── 結果のリンク構造を調査 ───
        print("\n=== 検索結果リンク ===")
        result_links = await page.evaluate("""
            () => Array.from(document.querySelectorAll('a[href]'))
                .filter(a => a.href.includes('room') || a.href.includes('detail') || a.href.includes('bukken'))
                .slice(0, 20)
                .map(a => ({text: a.innerText.trim().substring(0,30), href: a.href}))
        """)
        for r in result_links:
            print(f"  [{r['text']}] {r['href']}")

        # ─── 1件目をクリックして詳細ページを確認 ───
        if result_links:
            print(f"\n=== 詳細ページを確認 ===")
            await page.goto(result_links[0]['href'], wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(2)
            print(f"  詳細URL: {page.url}")
            await page.screenshot(path=str(OUT_DIR / "05_detail.png"))

            # 図面ボタンを探す
            print("\n=== 図面ボタン（オレンジ・緑） ===")
            buttons = await page.evaluate("""
                () => Array.from(document.querySelectorAll('a, button'))
                    .map(el => ({
                        text: el.innerText.trim().replace(/\\s+/g,' ').substring(0,50),
                        href: el.href || '',
                        onclick: (el.getAttribute('onclick') || '').substring(0,80),
                        style: el.getAttribute('style') || '',
                        cls: el.className.substring(0,50)
                    }))
                    .filter(x => x.text.length > 0)
            """)
            for b in buttons:
                if any(k in (b['text']+b['href']+b['onclick']).lower()
                       for k in ['図面', 'factsheet', 'pdf', '印刷', '出力', '資料', 'sheet', 'org']):
                    print(f"  ★ [{b['text']}] href={b['href'][:60]} onclick={b['onclick'][:60]}")
                    print(f"      style={b['style']} cls={b['cls']}")

        print("\n=== 完了 ===")
        await browser.close()

asyncio.run(main())
