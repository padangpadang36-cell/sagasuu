# -*- coding: utf-8 -*-
"""レオパレス21 エリア検索フローを詳細把握"""
import sys, io, asyncio, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from pathlib import Path
from playwright.async_api import async_playwright

OUT_DIR = Path(__file__).parent / "デバッグ" / "leopalace"
OUT_DIR.mkdir(parents=True, exist_ok=True)

AREA = "大阪市北区"
RENT_MAX = 80000

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, channel="chrome", slow_mo=300)
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="ja-JP",
            accept_downloads=True,
        )
        page = await ctx.new_page()

        # 市区町村から検索ページ
        print("=== 市区町村から検索 ===")
        await page.goto("https://www.leopalace21.com/search/chintai/area", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(4)
        await page.screenshot(path=str(OUT_DIR / "10_area_search.png"))
        print(f"URL: {page.url}")

        # テキスト確認
        body = await page.evaluate("() => document.body.innerText.substring(0, 1000)")
        print(f"テキスト: {body[:400]}")

        # フォーム要素
        inputs = await page.evaluate("""
            () => Array.from(document.querySelectorAll('input, select, button'))
                .filter(el => el.offsetParent !== null)
                .map(el => ({
                    tag: el.tagName, type: el.type||'', name: el.name||'',
                    id: el.id||'', text: (el.innerText||el.value||el.placeholder||'').trim().substring(0,40),
                    cls: el.className.substring(0,50)
                }))
                .slice(0, 30)
        """)
        print(f"\n要素 ({len(inputs)}件):")
        for el in inputs:
            print(f"  [{el['tag']}] type={el['type']} name={el['name']} id={el['id']} text={el['text']}")

        # 大阪 ボタンを探してクリック
        print("\n=== 大阪をクリック ===")
        try:
            osaka_btn = page.get_by_text("大阪", exact=False).first
            if await osaka_btn.is_visible(timeout=3000):
                await osaka_btn.click()
                await asyncio.sleep(3)
                await page.screenshot(path=str(OUT_DIR / "11_osaka.png"))
                print(f"URL after 大阪: {page.url}")
        except Exception as e:
            print(f"大阪クリックエラー: {e}")

        # 北区を探してクリック
        print("\n=== 北区をクリック ===")
        try:
            # テキスト一覧
            all_text = await page.evaluate("""
                () => Array.from(document.querySelectorAll('a, button, label, li'))
                    .filter(el => el.offsetParent !== null)
                    .map(el => ({
                        text: (el.innerText||'').trim().replace(/\\s+/g,' ').substring(0,30),
                        href: el.href||'',
                        tag: el.tagName
                    }))
                    .filter(x => x.text.length > 0)
                    .slice(0, 50)
            """)
            print("クリック可能要素:")
            for el in all_text:
                print(f"  [{el['tag']}] {el['text']} | {el['href'][:50]}")

            kitaku = page.get_by_text("北区", exact=False).first
            if await kitaku.is_visible(timeout=3000):
                await kitaku.click()
                await asyncio.sleep(4)
                await page.screenshot(path=str(OUT_DIR / "12_kitaku.png"))
                print(f"URL after 北区: {page.url}")
        except Exception as e:
            print(f"北区クリックエラー: {e}")

        # 物件一覧が表示されたか確認
        print("\n=== 物件一覧 ===")
        await asyncio.sleep(2)
        list_url = page.url
        print(f"現在URL: {list_url}")

        # HTML保存
        html = await page.content()
        with open(str(OUT_DIR / "list.html"), "w", encoding="utf-8") as f:
            f.write(html)
        print("HTML保存: list.html")

        # 物件カードを探す
        cards = await page.evaluate("""
            () => {
                // 物件リンクを探す
                const links = Array.from(document.querySelectorAll('a[href]'))
                    .filter(a => a.href.includes('/properties/') || a.href.includes('/bukken/'))
                    .map(a => ({
                        href: a.href,
                        text: (a.innerText||'').trim().replace(/\\s+/g,' ').substring(0,60)
                    }))
                    .filter(x => x.text.length > 0);
                return links.slice(0, 10);
            }
        """)
        print(f"物件リンク: {len(cards)}件")
        for c in cards:
            print(f"  {c['href'][:80]} | {c['text'][:40]}")

        # ページ全テキスト（物件名探し）
        body_text = await page.evaluate("() => document.body.innerText.substring(0, 2000)")
        print(f"\nページテキスト:\n{body_text[:1000]}")

        # ⑤ 物件詳細ページに移動してPDF取得テスト
        if cards:
            print(f"\n=== 物件詳細ページ: {cards[0]['href']} ===")
            await page.goto(cards[0]['href'], wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)
            await page.screenshot(path=str(OUT_DIR / "13_detail.png"))
            print(f"詳細URL: {page.url}")

            # PDF 取得
            pdf_path = str(OUT_DIR / "test_detail.pdf")
            await page.pdf(path=pdf_path, format="A4", print_background=True)
            import os
            size = os.path.getsize(pdf_path)
            print(f"PDF保存: {pdf_path} ({size:,} bytes)")

        # ⑥ 家賃上限フィルタのURL構造を調べる
        print("\n=== 家賃上限フィルタ ===")
        # 家賃フィルタがあるかチェック
        await page.go_back()
        await asyncio.sleep(2)
        rent_inputs = await page.evaluate("""
            () => Array.from(document.querySelectorAll('input, select'))
                .filter(el => {
                    const n = (el.name||el.id||el.placeholder||'').toLowerCase();
                    return n.includes('rent') || n.includes('price') || n.includes('yachin') || n.includes('chin');
                })
                .map(el => ({
                    tag: el.tagName, name: el.name||'', id: el.id||'',
                    placeholder: el.placeholder||''
                }))
        """)
        print(f"家賃フィルタ: {rent_inputs}")

        # URLパラメータで家賃指定を試す
        print("\n=== URLパラメータ検索 ===")
        # レオパレスの既知URLパターン
        test_urls = [
            f"https://www.leopalace21.com/bukken/search?prefectureCode=27&cityCode=2721&rentMax={RENT_MAX}",
            f"https://www.leopalace21.com/bukken/list?prefectureCode=27&cityCode=2721&rent_max={RENT_MAX}",
        ]
        for url in test_urls:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(3)
            print(f"  {url[:80]}")
            print(f"  → {page.url[:80]}")
            body = await page.evaluate("() => document.body.innerText.substring(0,300)")
            print(f"  テキスト: {body[:200]}")

        print("\n完了")
        await asyncio.sleep(3)
        await browser.close()

asyncio.run(main())
