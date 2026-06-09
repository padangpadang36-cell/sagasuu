# -*- coding: utf-8 -*-
"""レオパレス21 北区リストURLを特定し物件詳細PDF取得"""
import sys, io, asyncio, re, os
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
        browser = await pw.chromium.launch(headless=False, channel="chrome", slow_mo=200)
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="ja-JP",
            accept_downloads=True,
        )
        page = await ctx.new_page()

        # ① 大阪府ページで北区の直接URLを取得
        print("=== 北区URLを取得 ===")
        await page.goto("https://www.leopalace21.com/search/chintai/area?prefectureCode=27",
                        wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)

        # 全Aリンクから大阪市北区を探す
        kitaku_url = await page.evaluate("""
            () => {
                const links = Array.from(document.querySelectorAll('a'));
                const match = links.find(a =>
                    (a.innerText || '').trim() === '大阪市北区' ||
                    (a.innerText || '').trim().startsWith('大阪市北区')
                );
                return match ? match.href : null;
            }
        """)
        print(f"大阪市北区URL: {kitaku_url}")

        if not kitaku_url:
            # LABEL から探す
            kitaku_url = await page.evaluate("""
                () => {
                    // label から input[type=checkbox] → 対応するvalue/data属性
                    const label = Array.from(document.querySelectorAll('label'))
                        .find(l => (l.innerText||'').includes('大阪市北区'));
                    if (!label) return null;
                    return label.href || null;
                }
            """)
            print(f"Label href: {kitaku_url}")

        # ② 北区物件リストへ直接ナビゲート
        if kitaku_url:
            print(f"\n北区URLへナビゲート: {kitaku_url}")
            await page.goto(kitaku_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(4)
            await page.screenshot(path=str(OUT_DIR / "30_kitaku_list.png"))
            print(f"URL: {page.url}")
        else:
            # フォールバック: LABEL をクリックして「検索」ボタン
            print("URLが見つからず - LABEL クリックを試みる")
            label = page.locator("label").filter(has_text="大阪市北区").first
            await label.click()
            await asyncio.sleep(2)
            # 検索ボタンをクリック
            search_btn = page.locator("button").filter(has_text=re.compile(r"検索（\d+件）")).first
            if await search_btn.is_visible(timeout=3000):
                await search_btn.click()
                await asyncio.sleep(4)
            await page.screenshot(path=str(OUT_DIR / "30_kitaku_list.png"))
            print(f"URL: {page.url}")

        # ③ 物件カードを探す
        print("\n=== 物件カード ===")
        # HTML保存
        html = await page.content()
        with open(str(OUT_DIR / "kitaku_list.html"), "w", encoding="utf-8") as f:
            f.write(html)

        # ページテキスト
        body = await page.evaluate("() => document.body.innerText.substring(0, 3000)")
        print(f"ページテキスト:\n{body[:2000]}")

        # 物件リンクを全件取得
        prop_links = await page.evaluate("""
            () => {
                const seen = new Set();
                return Array.from(document.querySelectorAll('a[href]'))
                    .filter(a => {
                        const h = a.href || '';
                        return h.match(/properties\\/[a-z0-9-]+$/) && !h.includes('/area/') && !h.includes('/favorite');
                    })
                    .map(a => {
                        const card = a.closest('li, article') || a.parentElement;
                        const text = (card ? card.innerText : a.innerText || '').trim().replace(/\\s+/g, ' ');
                        return { href: a.href, text: text.substring(0, 100) };
                    })
                    .filter(x => {
                        if (seen.has(x.href)) return false;
                        seen.add(x.href);
                        return true;
                    });
            }
        """)
        print(f"\n物件リンク: {len(prop_links)}件")
        for p in prop_links[:5]:
            print(f"  {p['href'][:80]}")
            print(f"    {p['text'][:60]}")

        # 家賃フィルタ
        rent_filter = await page.evaluate("""
            () => {
                const selects = Array.from(document.querySelectorAll('select'))
                    .map(s => ({
                        name: s.name||'', id: s.id||'',
                        options: Array.from(s.options).map(o => ({value: o.value, text: o.text})).slice(0,15)
                    }));
                return selects;
            }
        """)
        print(f"\n家賃セレクト: {len(rent_filter)}件")
        for r in rent_filter:
            print(f"  name={r['name']} id={r['id']}")
            for o in r['options'][:10]:
                print(f"    value={o['value']} text={o['text']}")

        # ④ 詳細条件パネル
        print("\n=== 詳細条件パネル ===")
        # ボタン一覧
        all_btns = await page.evaluate("""
            () => Array.from(document.querySelectorAll('button, a'))
                .filter(el => el.offsetParent !== null)
                .map(el => ({
                    text: (el.innerText||'').trim().replace(/\\s+/g,' ').substring(0,40),
                    tag: el.tagName, href: el.href||''
                }))
                .filter(x => x.text.length > 0)
        """)
        print(f"ボタン: {len(all_btns)}件")
        for b in all_btns:
            print(f"  [{b['tag']}] {b['text'][:40]} | {b['href'][:50]}")

        # ⑤ 詳細条件を開く
        try:
            detail_btn = page.locator("button, a").filter(has_text=re.compile("詳細条件|絞り込み|フィルタ")).first
            if await detail_btn.is_visible(timeout=3000):
                await detail_btn.click()
                await asyncio.sleep(2)
                print("\n詳細条件を開いた後の要素:")
                after_els = await page.evaluate("""
                    () => Array.from(document.querySelectorAll('select, input[type="range"], input[name*="rent"]'))
                        .filter(el => el.offsetParent !== null)
                        .map(el => ({tag: el.tagName, name: el.name||'', id: el.id||'',
                            options: Array.from(el.options||[]).map(o => o.text).slice(0,10)}))
                """)
                print(f"フィルタ要素: {after_els}")
        except Exception as e:
            print(f"詳細条件エラー: {e}")

        # ⑥ 物件詳細ページへ
        if prop_links:
            detail_url = prop_links[0]['href']
            print(f"\n=== 物件詳細: {detail_url} ===")
            await page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(4)
            await page.screenshot(path=str(OUT_DIR / "31_prop_detail.png"))
            print(f"詳細URL: {page.url}")

            detail_text = await page.evaluate("() => document.body.innerText.substring(0, 3000)")
            print(f"テキスト:\n{detail_text[:1500]}")

            # PDF生成
            pdf_path = str(OUT_DIR / "prop_detail.pdf")
            await page.pdf(path=pdf_path, format="A4", print_background=True)
            print(f"\nPDF: {pdf_path} ({os.path.getsize(pdf_path):,} bytes)")

            # 物件情報抽出
            prop_info = await page.evaluate("""
                () => {
                    const title = document.querySelector('h1');
                    const allText = document.body.innerText;
                    // 家賃
                    const rentMatch = allText.match(/(\\d{1,3},\\d{3})円/);
                    // 間取り
                    const layoutMatch = allText.match(/[1-4][SLDK]+|ワンルーム|1R/);
                    // 住所
                    const addrMatch = allText.match(/大阪[^\\n]+[区市]/);
                    return {
                        title: title ? title.innerText.trim().substring(0,50) : '',
                        rent: rentMatch ? rentMatch[0] : '',
                        layout: layoutMatch ? layoutMatch[0] : '',
                        address: addrMatch ? addrMatch[0].substring(0,50) : ''
                    };
                }
            """)
            print(f"物件情報: {prop_info}")

        print("\n完了")
        await asyncio.sleep(3)
        await browser.close()

asyncio.run(main())
