# -*- coding: utf-8 -*-
"""レオパレス21 検索フローを把握する"""
import sys, io, asyncio, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from pathlib import Path
from playwright.async_api import async_playwright

OUT_DIR = Path(__file__).parent / "デバッグ" / "leopalace"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# エリア・家賃上限
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

        # ① トップページ
        await page.goto("https://www.leopalace21.com/", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)
        await page.screenshot(path=str(OUT_DIR / "01_top.png"))
        print(f"トップURL: {page.url}")

        # ② フリーワード検索を探す
        inputs = await page.evaluate("""
            () => Array.from(document.querySelectorAll('input, select, textarea'))
                .map(el => ({
                    tag: el.tagName, type: el.type||'', name: el.name||'',
                    id: el.id||'', placeholder: el.placeholder||'',
                    cls: el.className.substring(0,50)
                }))
                .filter(x => x.type !== 'hidden')
                .slice(0, 20)
        """)
        print(f"\n入力フィールド ({len(inputs)}件):")
        for el in inputs:
            print(f"  [{el['tag']}] type={el['type']} name={el['name']} id={el['id']} placeholder={el['placeholder'][:30]}")

        # リンク・ボタン
        btns = await page.evaluate("""
            () => Array.from(document.querySelectorAll('a, button'))
                .filter(el => el.offsetParent !== null)
                .map(el => ({
                    text: (el.innerText||'').trim().replace(/\s+/g,' ').substring(0,40),
                    href: el.href||'', tag: el.tagName
                }))
                .filter(x => x.text)
                .slice(0, 30)
        """)
        print(f"\nボタン/リンク (先頭30件):")
        for b in btns:
            print(f"  [{b['text']}] {b['href'][:60]}")

        # ③ 検索ページに直接アクセス
        print("\n\n=== 検索ページに直接アクセス ===")
        search_url = "https://www.leopalace21.com/bukken/search/"
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        await page.screenshot(path=str(OUT_DIR / "02_search.png"))
        print(f"検索URL: {page.url}")

        # ④ フォーム要素
        inputs2 = await page.evaluate("""
            () => Array.from(document.querySelectorAll('input, select, textarea'))
                .map(el => ({
                    tag: el.tagName, type: el.type||'', name: el.name||'',
                    id: el.id||'', placeholder: el.placeholder||'',
                    value: (el.value||'').substring(0,30)
                }))
                .filter(x => x.type !== 'hidden')
                .slice(0, 30)
        """)
        print(f"\n検索フォーム ({len(inputs2)}件):")
        for el in inputs2:
            print(f"  [{el['tag']}] type={el['type']} name={el['name']} id={el['id']} placeholder={el['placeholder'][:30]} value={el['value']}")

        # ⑤ エリア入力を試みる
        # フリーワード系のフィールドを探す
        for sel in ['input[name*="city"]', 'input[name*="area"]', 'input[name*="keyword"]',
                    'input[placeholder*="市区"]', 'input[placeholder*="エリア"]', 'input[placeholder*="地名"]',
                    '#keyword', '#area', '#city']:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=1000):
                    await el.fill(AREA)
                    print(f"  エリア入力: {sel} → {AREA}")
                    break
            except Exception:
                continue

        await asyncio.sleep(1)
        await page.screenshot(path=str(OUT_DIR / "03_filled.png"))

        # ⑥ HTML 保存
        html = await page.content()
        with open(str(OUT_DIR / "search.html"), "w", encoding="utf-8") as f:
            f.write(html)
        print("HTML保存: search.html")

        # ⑦ 家具家電付きフィルタを探す
        furniture_els = await page.evaluate("""
            () => Array.from(document.querySelectorAll('input[type="checkbox"], label'))
                .filter(el => {
                    const t = (el.innerText||el.value||el.getAttribute('for')||'').trim();
                    return t.includes('家具') || t.includes('家電') || t.includes('備付');
                })
                .map(el => ({
                    tag: el.tagName, text: (el.innerText||el.value||'').trim().substring(0,40),
                    name: el.name||'', id: el.id||'', checked: el.checked||false
                }))
        """)
        print(f"\n家具家電フィルタ: {furniture_els}")

        # ⑧ 別URLパターンを試す
        print("\n\n=== 別URLパターンを試す ===")
        # エリアコード付きURL等を試す
        for test_url in [
            "https://www.leopalace21.com/bukken/search/?pref=27&city=272&keyword=大阪市北区",
            "https://www.leopalace21.com/bukken/list/?pref=27",
            "https://www.leopalace21.com/search/",
        ]:
            try:
                await page.goto(test_url, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(2)
                print(f"  {test_url[:60]} → {page.url[:60]}")
            except Exception as e:
                print(f"  {test_url[:60]} → エラー: {e}")

        await page.screenshot(path=str(OUT_DIR / "04_alt_urls.png"))

        # ⑨ 検索フォームを submit してみる
        print("\n\n=== 検索フォームをsubmit ===")
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        # フォーム内容を確認
        forms = await page.evaluate("""
            () => Array.from(document.querySelectorAll('form'))
                .map(f => ({
                    action: f.action,
                    method: f.method,
                    inputs: Array.from(f.querySelectorAll('input,select'))
                        .filter(el => el.name)
                        .map(el => ({name: el.name, type: el.type||'', value: (el.value||'').substring(0,30)}))
                        .slice(0, 20)
                }))
        """)
        print(f"フォーム数: {len(forms)}")
        for i, f in enumerate(forms):
            print(f"  フォーム{i}: action={f['action'][:60]} method={f['method']}")
            for inp in f['inputs']:
                print(f"    [{inp['name']}] type={inp['type']} value={inp['value']}")

        print("\n完了。スクリーンショット: " + str(OUT_DIR))
        await asyncio.sleep(5)
        await browser.close()

asyncio.run(main())
