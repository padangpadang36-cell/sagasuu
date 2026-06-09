# -*- coding: utf-8 -*-
"""ATBBインフォシートの編集メニューを調査してPDFを2種類取得する
インフォシートURLはハッシュ認証なので直接アクセス可能
"""
import sys, io, asyncio, re, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from pathlib import Path
from playwright.async_api import async_playwright

OUT_DIR = Path(__file__).parent / "デバッグ" / "atbb_infosheet"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 直近の main.py 実行で取得したインフォシートURL
INFOSHEET_URL = "https://zmn.atbb.athome.co.jp/infosheets/88ade02e985813da306125a4a834184db2c0bf5"

async def investigate_infosheet(page, url: str, shot_prefix: str):
    """インフォシートページの構造を調査"""
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(5)   # React SPA の描画を待つ
    await page.screenshot(path=str(OUT_DIR / f"{shot_prefix}_01_default.png"))
    print(f"\n=== {shot_prefix} URL: {page.url} ===")

    # ページテキスト
    body = await page.evaluate("() => document.body.innerText.substring(0, 3000)")
    print(f"テキスト:\n{body[:1200]}")

    # 全インタラクティブ要素
    els = await page.evaluate("""
        () => Array.from(document.querySelectorAll('button, a[href], [role="button"], select, input, [onclick], svg'))
            .filter(el => el.offsetParent !== null || el.closest('[class*="header"],[class*="menu"],[class*="nav"]'))
            .map(el => ({
                text: (el.innerText||el.value||el.getAttribute('aria-label')||el.getAttribute('title')||'')
                    .trim().replace(/\\s+/g,' ').substring(0,50),
                tag: el.tagName,
                id: el.id||'',
                cls: el.className.substring(0,60),
                role: el.getAttribute('role')||'',
                type: el.type||''
            }))
            .filter(x => x.text.length > 0 || x.id.length > 0)
    """)
    print(f"\n全インタラクティブ要素 ({len(els)}件):")
    for el in els:
        mark = '★' if any(k in el['text'] for k in ['編集', '設定', 'メニュー', 'PDF', '印刷', '一般', '客付', '手数料']) else ' '
        print(f"  {mark}[{el['tag']}] '{el['text'][:45]}' id={el['id'][:20]}")

    return body, els


async def try_edit_menu(page, shot_prefix: str):
    """編集メニューをクリックして内容を確認"""
    print(f"\n=== {shot_prefix}: 編集メニュー探索 ===")
    found = False

    # ① テキストで探す
    for label in ["編集メニュー", "編集", "設定", "メニュー", "オプション"]:
        try:
            matches = await page.locator(f"text='{label}'").all()
            for m in matches:
                if await m.is_visible(timeout=500):
                    print(f"  テキスト '{label}' 発見")
                    await m.click()
                    await asyncio.sleep(2)
                    await page.screenshot(path=str(OUT_DIR / f"{shot_prefix}_02_edit_clicked.png"))
                    found = True
                    break
            if found:
                break
        except Exception:
            continue

    # ② アイコンボタン（SVGベース）で探す
    if not found:
        try:
            # 右上のハンバーガーメニューや歯車アイコン
            icon_btns = await page.evaluate("""
                () => Array.from(document.querySelectorAll('button, [role="button"]'))
                    .filter(el => {
                        const t = (el.innerText||'').trim();
                        return t === '' || t.length < 5;
                    })
                    .map(el => ({
                        id: el.id||'',
                        cls: el.className.substring(0,80),
                        html: el.outerHTML.substring(0,150)
                    }))
                    .slice(0, 20)
            """)
            print(f"  アイコンボタン: {len(icon_btns)}件")
            for b in icon_btns:
                print(f"    id={b['id']} cls={b['cls'][:60]}")
                print(f"    html={b['html'][:100]}")
        except Exception as e:
            print(f"  アイコンボタン探索エラー: {e}")

    # ③ メニュー項目を確認
    after_els = await page.evaluate("""
        () => Array.from(document.querySelectorAll('*'))
            .filter(el => el.offsetParent !== null && el.children.length === 0)
            .filter(el => {
                const t = (el.innerText||el.textContent||'').trim();
                return t.length > 0 && t.length < 40 &&
                    (t.includes('手数料') || t.includes('一般') || t.includes('客付') ||
                     t.includes('社宅') || t.includes('PDF') || t.includes('印刷') ||
                     t.includes('表示') || t.includes('設定') || t.includes('編集'));
            })
            .map(el => ({
                text: (el.innerText||el.textContent||'').trim(),
                tag: el.tagName,
                cls: el.className.substring(0,60)
            }))
            .slice(0, 30)
    """)
    print(f"\n  関連テキスト要素 ({len(after_els)}件):")
    for e in after_els:
        print(f"    [{e['tag']}] '{e['text']}' cls={e['cls'][:40]}")

    return found


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, channel="chrome", slow_mo=200)
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="ja-JP",
            accept_downloads=True,
        )
        page = await ctx.new_page()

        # ① デフォルトインフォシートを開く
        body, els = await investigate_infosheet(page, INFOSHEET_URL, "A")

        # ② 編集メニューを試みる
        await try_edit_menu(page, "A")

        # ③ 元図面をPDF保存
        print("\n=== 元図面PDF保存 ===")
        moto_pdf = str(OUT_DIR / "mototsuke.pdf")
        await page.goto(INFOSHEET_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(4)
        await page.pdf(path=moto_pdf, format="A4", print_background=True)
        print(f"  元図面: {moto_pdf} ({os.path.getsize(moto_pdf):,} bytes)")

        # ④ URLパラメータを試す
        print("\n=== URLパラメータテスト ===")
        base_url = INFOSHEET_URL.split('?')[0]
        for param in [
            "?printMode=1",
            "?hideCommissionFee=true",
            "?display=general",
            "?mode=client",
            "?type=2",
            "?showFee=false",
        ]:
            test_url = base_url + param
            await page.goto(test_url, wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(3)
            # ページが変わったか確認
            current_text = await page.evaluate("() => document.body.innerText.substring(0, 300)")
            print(f"  {param}")
            print(f"  → URL: {page.url[:70]}")
            print(f"  テキスト変化: {current_text[:100]}")
            print()

        # ⑤ HTMLを保存して確認
        await page.goto(INFOSHEET_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)
        html = await page.content()
        with open(str(OUT_DIR / "infosheet.html"), "w", encoding="utf-8") as f:
            f.write(html)
        print(f"HTML保存: {OUT_DIR}/infosheet.html ({len(html):,} bytes)")

        # ⑥ Reactコンポーネントの状態を確認
        react_state = await page.evaluate("""
            () => {
                // Reactの内部状態を探す
                const root = document.getElementById('root') || document.querySelector('[data-reactroot]');
                if (!root) return 'Reactルートなし';
                // React Fiberを探す
                const key = Object.keys(root).find(k => k.startsWith('__reactFiber'));
                if (!key) return 'React Fiberなし';
                return 'React Fiber発見: ' + key;
            }
        """)
        print(f"\nReact状態: {react_state}")

        # ⑦ ネットワークリクエストを監視してAPIを確認
        print("\n=== ネットワーク監視 (5秒) ===")
        api_calls = []
        page.on("request", lambda r: api_calls.append(("REQ", r.method, r.url[:80])))
        page.on("response", lambda r: api_calls.append(("RES", r.status, r.url[:80])))
        await page.reload()
        await asyncio.sleep(5)
        for call in api_calls:
            if not any(ext in call[-1] for ext in ['.js', '.css', '.png', '.jpg', '.woff', '.ico']):
                print(f"  {call[0]} {call[1]} {call[2]}")

        print("\n完了")
        await asyncio.sleep(3)
        await browser.close()

asyncio.run(main())
