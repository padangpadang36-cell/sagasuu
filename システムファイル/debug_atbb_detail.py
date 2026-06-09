# -*- coding: utf-8 -*-
"""ATBB 物件詳細ページの印刷/PDFリンク構造を調査"""
import sys, io, asyncio, json, re
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

OUT_DIR = Path(__file__).parent / "デバッグ" / "atbb_detail"
OUT_DIR.mkdir(parents=True, exist_ok=True)

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, channel="chrome", slow_mo=400)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 900}, locale="ja-JP")
        page = await ctx.new_page()

        # ── ATBB ログイン ──
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
        print(f"ログイン後URL: {page.url}")
        if "login" in page.url.lower():
            print("ログイン失敗"); await browser.close(); return

        # ── 物件・会社検索 → 流通物件検索 ──
        try:
            await page.locator('a:has-text("物件・会社検索")').first.click()
            await asyncio.sleep(1)
            async with ctx.expect_page(timeout=5000) as new_page_info:
                await page.get_by_text("流通物件検索").first.click()
            new_page = await new_page_info.value
            await new_page.wait_for_load_state("domcontentloaded", timeout=15000)
            page = new_page
        except Exception as e:
            print(f"メニュー操作エラー: {e}")

        await asyncio.sleep(2)
        print(f"遷移後URL: {page.url}")

        # 他セッション検出 → 強制ログイン
        if "ConcurrentLoginException" in page.url:
            action = await page.evaluate("""
                () => {
                    const f = document.querySelector('form');
                    const sid = location.href.match(/jsessionid=([A-Fa-f0-9]+)/);
                    const base = f ? f.action : '';
                    return sid ? base + ';jsessionid=' + sid[1] : base;
                }
            """)
            await page.goto(action, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(4)
            print(f"強制ログイン後: {page.url}")

        # ── 賃貸居住用 選択 → フリーワード検索 ──
        await asyncio.sleep(3)
        try:
            await page.locator('input[name="atbbShumokuDaibunrui"][value="06"]').click()
        except Exception:
            pass
        await asyncio.sleep(1)
        try:
            fw = page.locator('input[name*="freeword"], input[name*="freeWord"]').first
            await fw.fill("大阪市北区 8万円以下")
            await page.locator('input[value="検索"]').last.click()
        except Exception as e:
            print(f"フリーワード検索エラー: {e}")

        await asyncio.sleep(4)
        await page.wait_for_load_state("domcontentloaded", timeout=20000)
        await asyncio.sleep(2)
        print(f"検索結果URL: {page.url}")
        await page.screenshot(path=str(OUT_DIR / "01_results.png"))

        # ── 1件目の詳細ボタンをクリック ──
        btn_exists = await page.evaluate("() => !!document.getElementById('shosai_0')")
        if not btn_exists:
            print("shosai_0 が見つかりません")
            input("Enterで終了..."); await browser.close(); return

        await page.evaluate("document.getElementById('shosai_0').click()")
        await page.wait_for_load_state("domcontentloaded", timeout=20000)
        await asyncio.sleep(3)
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        await asyncio.sleep(3)
        print(f"詳細URL: {page.url}")
        await page.screenshot(path=str(OUT_DIR / "02_detail.png"))

        # HTML保存
        html = await page.content()
        (OUT_DIR / "detail.html").write_text(html, encoding='utf-8', errors='replace')
        print(f"HTML保存: {OUT_DIR / 'detail.html'}")

        # ページテキスト
        body_text = await page.evaluate("() => document.body.innerText")
        print(f"\nページテキスト(先頭3000文字):\n{body_text[:3000]}")
        (OUT_DIR / "detail_text.txt").write_text(body_text, encoding='utf-8', errors='replace')

        # 全リンク・ボタンを調査
        link_btn_info = await page.evaluate("""
            () => {
                const items = [];
                // リンク
                for (const a of document.querySelectorAll('a')) {
                    const t = a.textContent.trim();
                    const h = a.href || '';
                    const oc = a.getAttribute('onclick') || '';
                    items.push({type:'link', text:t.substring(0,50), href:h.substring(0,120), onclick:oc.substring(0,80)});
                }
                // ボタン/入力
                for (const b of document.querySelectorAll('button, input[type="button"], input[type="submit"], input[type="image"]')) {
                    const t = b.textContent.trim() || b.value || b.alt || '';
                    const oc = b.getAttribute('onclick') || '';
                    const nm = b.name || b.id || '';
                    items.push({type:'button', text:t.substring(0,50), href:nm, onclick:oc.substring(0,80)});
                }
                return items;
            }
        """)

        print(f"\n=== リンク・ボタン ({len(link_btn_info)}件) ===")
        keywords = ['pdf', '印刷', 'print', 'download', '詳細', 'チラシ', '出力']
        for item in link_btn_info:
            combined = (item['text'] + item['href'] + item['onclick']).lower()
            if any(kw.lower() in combined for kw in keywords):
                print(f"  ★ [{item['type']}] {item['text']} | href={item['href']} | onclick={item['onclick']}")

        print("\n--- 全件 ---")
        for item in link_btn_info:
            print(f"  [{item['type']}] {item['text'][:30]} | {item['href'][:60]} | {item['onclick'][:40]}")

        # iframeも確認
        iframes = await page.evaluate("""
            () => Array.from(document.querySelectorAll('iframe')).map(f => ({src:f.src, id:f.id, name:f.name}))
        """)
        if iframes:
            print(f"\n=== iframes ===")
            for f in iframes:
                print(f"  {f}")

        # window.openやJavaScript関数を探す
        scripts_info = await page.evaluate("""
            () => {
                const scripts = Array.from(document.querySelectorAll('script:not([src])'));
                const funcs = [];
                for (const s of scripts) {
                    const txt = s.textContent;
                    // PDF/印刷関連の関数を探す
                    const matches = txt.match(/function\\s+(print|pdf|PDF|Print|chiraishi|chirashi|download)[\\w]*/g);
                    if (matches) funcs.push(...matches);
                    if (txt.includes('pdf') || txt.includes('印刷') || txt.includes('print')) {
                        const lines = txt.split('\\n').filter(l =>
                            l.includes('pdf') || l.includes('印刷') || l.includes('Print'));
                        funcs.push(...lines.slice(0,5));
                    }
                }
                return funcs.slice(0, 20);
            }
        """)
        if scripts_info:
            print(f"\n=== PDF/印刷関連スクリプト ===")
            for s in scripts_info:
                print(f"  {s.strip()[:120]}")

        input("\n[確認] Enterで終了...")
        await browser.close()

asyncio.run(main())
