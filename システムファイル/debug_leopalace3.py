# -*- coding: utf-8 -*-
"""レオパレス21 北区物件リストと詳細ページ構造把握"""
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

        # ① 大阪府・北区を選択して物件リストへ
        print("=== 大阪府ページ ===")
        await page.goto("https://www.leopalace21.com/search/chintai/area?prefectureCode=27",
                        wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(4)
        await page.screenshot(path=str(OUT_DIR / "20_osaka_pref.png"))

        # 北区のlabelを探してクリック
        # "大阪市北区" というラベルを正確に探す
        label_found = False
        labels = await page.evaluate("""
            () => Array.from(document.querySelectorAll('label, li, a'))
                .filter(el => el.offsetParent !== null)
                .map(el => ({
                    text: (el.innerText||'').trim().replace(/\\s+/g,' '),
                    tag: el.tagName,
                    cls: el.className.substring(0,40),
                    href: el.href||''
                }))
                .filter(x => x.text.includes('北区'))
        """)
        print(f"北区を含む要素: {len(labels)}件")
        for l in labels:
            print(f"  [{l['tag']}] cls={l['cls']} text={l['text'][:50]} href={l['href'][:60]}")

        # 大阪市北区のリンクを直接クリック
        # LabelもしくはAタグを探す
        for l in labels:
            if '大阪市北区' in l['text']:
                print(f"\n大阪市北区をクリック: [{l['tag']}] {l['text'][:30]}")
                # タグに応じてクリック
                if l['href']:
                    await page.goto(l['href'], wait_until="domcontentloaded", timeout=30000)
                else:
                    # セレクタでクリック
                    el = page.locator(f"{l['tag'].lower()}").filter(has_text="大阪市北区").first
                    await el.click()
                await asyncio.sleep(3)
                label_found = True
                break

        if not label_found:
            # 別の方法: テキストで探す
            try:
                el = page.get_by_text("大阪市北区", exact=True).first
                if await el.is_visible(timeout=3000):
                    await el.click()
                    await asyncio.sleep(3)
                    label_found = True
            except Exception as e:
                print(f"テキスト検索エラー: {e}")

        await page.screenshot(path=str(OUT_DIR / "21_after_kitaku_click.png"))
        print(f"クリック後URL: {page.url}")

        # ② 検索ボタンを探してクリック
        print("\n=== 検索ボタン ===")
        search_btns = await page.evaluate("""
            () => Array.from(document.querySelectorAll('button, a'))
                .filter(el => el.offsetParent !== null)
                .map(el => ({
                    text: (el.innerText||'').trim().replace(/\\s+/g,' '),
                    tag: el.tagName,
                    href: el.href||''
                }))
                .filter(x => x.text.includes('検索') || x.text.includes('件'))
        """)
        print(f"検索ボタン候補: {len(search_btns)}件")
        for b in search_btns:
            print(f"  [{b['tag']}] text={b['text'][:50]} href={b['href'][:60]}")

        # 「検索」ボタンをクリック（「家具・家電」優先）
        clicked_search = False
        for priority in ["家具・家電付き物件を検索", "検索"]:
            try:
                btn = page.get_by_text(priority, exact=False).first
                if await btn.is_visible(timeout=2000):
                    print(f"\n'{priority}'ボタンをクリック")
                    await btn.click()
                    await asyncio.sleep(4)
                    clicked_search = True
                    break
            except Exception:
                continue

        await page.screenshot(path=str(OUT_DIR / "22_after_search.png"))
        print(f"検索後URL: {page.url}")

        # ③ 物件一覧の確認
        print("\n=== 物件一覧 ===")
        await asyncio.sleep(2)

        # HTML保存
        html = await page.content()
        with open(str(OUT_DIR / "list2.html"), "w", encoding="utf-8") as f:
            f.write(html)

        # テキスト確認
        body = await page.evaluate("() => document.body.innerText.substring(0, 3000)")
        print(f"ページテキスト:\n{body[:1500]}")

        # 物件カードを探す
        prop_links = await page.evaluate("""
            () => {
                const seen = new Set();
                return Array.from(document.querySelectorAll('a[href]'))
                    .filter(a => {
                        const h = a.href||'';
                        return (h.includes('/properties/') && !h.includes('/favorite')) ||
                               h.includes('/chintai/');
                    })
                    .map(a => {
                        const card = a.closest('li, article, div[class*="card"], div[class*="item"]') || a;
                        return {
                            href: a.href,
                            text: (a.innerText||card.innerText||'').trim().replace(/\\s+/g,' ').substring(0, 80),
                        };
                    })
                    .filter(x => {
                        if (seen.has(x.href)) return false;
                        seen.add(x.href);
                        return true;
                    })
                    .slice(0, 20);
            }
        """)
        print(f"\n物件リンク: {len(prop_links)}件")
        for p in prop_links:
            print(f"  {p['href'][:80]}")
            if p['text']:
                print(f"    {p['text'][:60]}")

        # ④ 物件詳細ページへ
        if prop_links and len(prop_links) > 0:
            # 最初の有効な物件リンクへ
            detail_url = None
            for pl in prop_links:
                if '/chintai/' in pl['href'] or ('/properties/' in pl['href'] and 'favorite' not in pl['href']):
                    detail_url = pl['href']
                    break

            if detail_url:
                print(f"\n=== 物件詳細ページ: {detail_url} ===")
                await page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(4)
                await page.screenshot(path=str(OUT_DIR / "23_detail.png"))
                print(f"詳細URL: {page.url}")

                # ページテキスト
                detail_text = await page.evaluate("() => document.body.innerText.substring(0, 2000)")
                print(f"詳細テキスト:\n{detail_text[:800]}")

                # 物件名・家賃・間取りを抽出
                info = await page.evaluate("""
                    () => {
                        // タイトル
                        const title = document.querySelector('h1, h2, [class*="title"], [class*="name"]');
                        // 家賃
                        const rentEl = Array.from(document.querySelectorAll('*'))
                            .find(el => el.innerText && el.innerText.match(/\\d+,\\d{3}円|\\d+万円/));
                        return {
                            title: (title ? title.innerText : '').trim().substring(0,50),
                            rent: rentEl ? rentEl.innerText.trim().substring(0,30) : '',
                            url: location.href
                        };
                    }
                """)
                print(f"物件情報: {info}")

                # HTML保存
                html2 = await page.content()
                with open(str(OUT_DIR / "detail.html"), "w", encoding="utf-8") as f:
                    f.write(html2)

                # PDF生成テスト
                pdf_path = str(OUT_DIR / "detail_test.pdf")
                await page.pdf(path=pdf_path, format="A4", print_background=True)
                import os
                size = os.path.getsize(pdf_path)
                print(f"\nPDF保存: {pdf_path} ({size:,} bytes)")

                # 印刷用ページが別途あるか確認
                print_links = await page.evaluate("""
                    () => Array.from(document.querySelectorAll('a, button'))
                        .filter(el => {
                            const t = (el.innerText||el.value||'').trim();
                            return t.includes('印刷') || t.includes('PDF') || t.includes('print');
                        })
                        .map(el => ({
                            text: (el.innerText||el.value||'').trim().substring(0,40),
                            href: el.href||'',
                            onclick: (el.getAttribute('onclick')||'').substring(0,60)
                        }))
                """)
                print(f"\n印刷/PDFボタン: {print_links}")

        # ⑤ 家賃フィルタURLを確認
        print("\n\n=== 家賃フィルタ ===")
        # 現在のURLから家賃フィルタを追加
        curr_url = page.url
        # 戻る
        await page.go_back()
        await asyncio.sleep(2)
        curr_url2 = page.url

        # フィルタ要素確認
        filters = await page.evaluate("""
            () => Array.from(document.querySelectorAll('select, input[type="range"], input[name*="rent"], input[name*="price"]'))
                .map(el => ({
                    tag: el.tagName, name: el.name||'', id: el.id||'',
                    value: el.value||'', options: Array.from(el.options||[]).map(o => o.text).slice(0,10)
                }))
        """)
        print(f"フィルタ要素: {filters}")

        await page.screenshot(path=str(OUT_DIR / "24_back_to_list.png"))
        print(f"\n戻りURL: {curr_url2}")

        print("\n完了")
        await asyncio.sleep(3)
        await browser.close()

asyncio.run(main())
