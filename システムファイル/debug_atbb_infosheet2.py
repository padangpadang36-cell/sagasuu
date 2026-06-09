# -*- coding: utf-8 -*-
"""ATBBインフォシート編集メニュー調査 - 正しいリダイレクト待機付き"""
import sys, io, asyncio, re, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv(Path(__file__).parent.parent / ".env")
ATBB_URL  = "https://atbb.athome.jp/"
ATBB_ID   = os.getenv("ATBB_ID", "")
ATBB_PASS = os.getenv("ATBB_PASS", "")

OUT_DIR = Path(__file__).parent / "デバッグ" / "atbb_infosheet"
OUT_DIR.mkdir(parents=True, exist_ok=True)

async def login_atbb(ctx, page):
    """ATBBフルログインフロー (main.pyと同じ)"""
    await page.goto(ATBB_URL, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(2)
    await page.locator('input[name="loginId"]').fill(ATBB_ID)
    await page.locator('input[type="password"]').fill(ATBB_PASS)
    await page.locator('input[type="submit"]').click()
    try:
        await page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    await asyncio.sleep(3)
    print(f"ログイン後URL: {page.url}")

    # 物件・会社検索 → 流通物件検索
    try:
        el = page.locator('a:has-text("物件・会社検索")').first
        await el.wait_for(state="visible", timeout=5000)
        await el.click()
        await asyncio.sleep(1)
        el2 = page.get_by_text("流通物件検索").first
        await el2.wait_for(state="visible", timeout=3000)
        async with ctx.expect_page(timeout=8000) as np_info:
            await el2.click()
        new_page = await np_info.value
        await new_page.wait_for_load_state("domcontentloaded", timeout=15000)
        print(f"新規タブ: {new_page.url}")
        page = new_page
    except Exception as e:
        print(f"メニューエラー: {e}")

    # ★ リダイレクト完了を待つ（ここが重要）
    await asyncio.sleep(3)
    print(f"リダイレクト後URL: {page.url}")

    # ConcurrentLoginException対応
    if "ConcurrentLoginException" in page.url:
        print("他セッション検出 → 強制ログイン")
        sid_m = re.search(r'jsessionid=([A-Fa-f0-9]+)', page.url)
        sid = f";jsessionid={sid_m.group(1)}" if sid_m else ""
        force_url = f"https://atbb.athome.co.jp/front-web/login/force{sid}"
        print(f"強制ログインURL: {force_url}")
        await page.goto(force_url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(4)
        print(f"強制ログイン後URL: {page.url}")

    await asyncio.sleep(3)
    print(f"流通物件検索URL: {page.url}")
    return page


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, channel="chrome", slow_mo=200)
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="ja-JP",
            accept_downloads=True,
        )
        page = await ctx.new_page()

        # ① ログイン
        page = await login_atbb(ctx, page)

        # ② 検索
        await page.evaluate("""
            () => {
                const r = document.querySelector('input[value="06"]');
                if (r) { r.checked = true; r.dispatchEvent(new Event('change')); }
            }
        """)
        await asyncio.sleep(1)

        kw = page.locator('input[name="freeword"]').first
        if await kw.is_visible(timeout=3000):
            await kw.click(click_count=3)
            await kw.fill("大阪市北区 8万円以下")
            await kw.press("Enter")
        await asyncio.sleep(5)
        print(f"検索結果URL: {page.url}")

        # ③ 物件詳細
        exists = await page.evaluate("() => !!document.getElementById('shosai_0')")
        print(f"shosai_0 exists: {exists}")
        if not exists:
            print("shosai_0が見つかりません - ブラウザを確認してください")
            await asyncio.sleep(30)
            await browser.close()
            return

        await page.evaluate("document.getElementById('shosai_0').click()")
        await page.wait_for_load_state("domcontentloaded", timeout=20000)
        await asyncio.sleep(4)
        print(f"詳細URL: {page.url}")

        # ④ インフォシートボタン → 新規タブ
        btn = page.locator('#infoSheetButtonTop_0')
        if not await btn.is_visible(timeout=3000):
            btn = page.locator('button:has-text("インフォシート")').first

        try:
            async with ctx.expect_page(timeout=10000) as np_info:
                await btn.click()
            info_tab = await np_info.value
            await info_tab.wait_for_load_state("domcontentloaded", timeout=20000)
            await asyncio.sleep(6)  # React SPA描画待ち（長め）
            infosheet_url = info_tab.url
            print(f"\nインフォシートURL: {infosheet_url}")

            await info_tab.screenshot(path=str(OUT_DIR / "01_default.png"))

            # ページテキスト（React描画後）
            body = await info_tab.evaluate("() => document.body.innerText")
            print(f"\nページテキスト (先頭1500文字):\n{body[:1500]}")

            # 全インタラクティブ要素
            els = await info_tab.evaluate("""
                () => Array.from(document.querySelectorAll('button, a[href], [role="button"], select'))
                    .map(el => ({
                        text: (el.innerText||el.value||el.getAttribute('aria-label')||'')
                            .trim().replace(/[ \t\n]+/g,' ').substring(0,50),
                        tag: el.tagName,
                        id: el.id||'',
                        cls: el.className.substring(0,70)
                    }))
                    .filter(x => x.text.length > 0 || x.id.length > 0)
            """)
            print(f"\n全要素 ({len(els)}件):")
            for el in els:
                mark = '★' if any(k in el['text'] for k in ['編集', '設定', 'PDF', '印刷', '一般', '客付', '手数料', 'menu']) else ' '
                print(f"  {mark}[{el['tag']}] '{el['text'][:45]}' id={el['id'][:20]}")

            # ── 元図面PDF保存 ──
            moto_pdf = str(OUT_DIR / "01_mototsuke.pdf")
            await info_tab.pdf(path=moto_pdf, format="A4", print_background=True)
            print(f"\n✓ 元図面PDF: {moto_pdf} ({os.path.getsize(moto_pdf):,} bytes)")

            # ── 編集メニューを探す ──
            print("\n=== 編集メニュー探索 ===")
            found = False

            # テキストベース
            for label in ["編集メニュー", "編集", "設定", "Edit", "Menu"]:
                try:
                    matches = await info_tab.locator(f":text('{label}')").all()
                    for m in matches:
                        if await m.is_visible(timeout=500):
                            bb = await m.bounding_box()
                            print(f"  '{label}' at ({bb['x']:.0f},{bb['y']:.0f}) size {bb['width']:.0f}x{bb['height']:.0f}")
                            await m.click()
                            await asyncio.sleep(2)
                            await info_tab.screenshot(path=str(OUT_DIR / "02_after_edit.png"))
                            found = True
                            break
                    if found:
                        break
                except Exception:
                    pass

            # ページ右上のボタン（アイコン系）
            if not found:
                # ヘッダー内のボタンを全て試す
                header_btns = await info_tab.evaluate("""
                    () => Array.from(document.querySelectorAll('header button, [class*="header"] button, [class*="Header"] button, nav button'))
                        .map(el => ({
                            text: (el.innerText||el.getAttribute('aria-label')||'').trim().substring(0,30),
                            id: el.id||'',
                            cls: el.className.substring(0,60),
                            html: el.outerHTML.substring(0,150)
                        }))
                """)
                print(f"\nヘッダーボタン: {len(header_btns)}件")
                for b in header_btns:
                    print(f"  '{b['text']}' id={b['id']} cls={b['cls'][:40]}")
                    print(f"    {b['html'][:100]}")

                # 右上端のボタン（座標ベース）
                all_btns = await info_tab.evaluate("""
                    () => {
                        const vw = window.innerWidth;
                        return Array.from(document.querySelectorAll('button, [role="button"]'))
                            .map(el => {
                                const r = el.getBoundingClientRect();
                                return {
                                    x: r.left, y: r.top, w: r.width, h: r.height,
                                    text: (el.innerText||el.getAttribute('aria-label')||'').trim().substring(0,30),
                                    id: el.id||''
                                };
                            })
                            .filter(b => b.x > 0 && b.y > 0 && b.h > 0)
                            .sort((a,b) => b.x - a.x);  // 右端のものから
                    }
                """)
                print(f"\n全ボタン（座標ソート）: {len(all_btns)}件")
                for b in all_btns[:15]:
                    print(f"  ({b['x']:.0f},{b['y']:.0f}) {b['w']:.0f}x{b['h']:.0f} '{b['text'][:30]}' id={b['id']}")

            # クリック後のメニュー項目
            print("\n=== 現在の全テキスト要素（手数料関連） ===")
            fee_els = await info_tab.evaluate("""
                () => Array.from(document.querySelectorAll('*'))
                    .filter(el => {
                        const t = (el.innerText||el.textContent||'').trim();
                        return t.length > 0 && t.length < 50 &&
                            (t.includes('手数料') || t.includes('一般') || t.includes('客付') ||
                             t.includes('表示') || t.includes('設定') || t.includes('チェック'));
                    })
                    .filter(el => el.children.length === 0 && el.offsetParent !== null)
                    .map(el => ({
                        text: (el.innerText||el.textContent||'').trim(),
                        tag: el.tagName, cls: el.className.substring(0,50),
                        id: el.id||''
                    }))
            """)
            print(f"関連テキスト: {len(fee_els)}件")
            for e in fee_els:
                print(f"  [{e['tag']}] '{e['text']}' cls={e['cls'][:40]}")

            # HTML保存
            html = await info_tab.content()
            with open(str(OUT_DIR / "infosheet.html"), "w", encoding="utf-8") as f:
                f.write(html)
            print(f"\nHTML保存: {len(html):,} bytes")

            print("\n=== 完了。ブラウザを10秒開けています ===")
            await asyncio.sleep(10)
            await info_tab.close()

        except Exception as e:
            print(f"インフォシートエラー: {e}")
            import traceback; traceback.print_exc()

        await browser.close()

asyncio.run(main())
