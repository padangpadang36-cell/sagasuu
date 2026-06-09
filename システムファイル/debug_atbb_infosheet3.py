# -*- coding: utf-8 -*-
"""ATBBインフォシート編集メニュー調査 - 完全ログイン＋検索フロー"""
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


async def login_atbb(page, ctx) -> object:
    """ATBBログイン→流通物件検索ページへ。pageを返す"""
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

    # リダイレクト完了を待つ
    await asyncio.sleep(3)
    print(f"リダイレクト後URL: {page.url}")

    # ConcurrentLoginException対応
    if "ConcurrentLoginException" in page.url:
        print("他セッション検出 → 強制ログイン")
        try:
            force_info = await page.evaluate("""
                () => {
                    const form = document.querySelector('form');
                    if (!form) return null;
                    const params = {};
                    Array.from(form.querySelectorAll('input')).forEach(i => {
                        if (i.name) params[i.name] = i.value;
                    });
                    return {action: form.action, params: params};
                }
            """)
            print(f"フォーム: {force_info}")
            if force_info and force_info.get('action'):
                action = force_info['action']
                sid_m = re.search(r'jsessionid=([A-Fa-f0-9]+)', page.url)
                if sid_m and 'jsessionid' not in action:
                    action = action + f';jsessionid={sid_m.group(1)}'
                params = force_info.get('params') or {}
                if params:
                    qs = '&'.join(f"{k}={v}" for k, v in params.items())
                    action = action + '?' + qs
                print(f"強制ログインURL: {action}")
                await page.goto(action, wait_until="domcontentloaded", timeout=20000)
            else:
                sid_m = re.search(r'jsessionid=([A-Fa-f0-9]+)', page.url)
                sid = f";jsessionid={sid_m.group(1)}" if sid_m else ""
                force_url = f"https://atbb.athome.co.jp/front-web/login/force{sid}"
                await page.goto(force_url, wait_until="domcontentloaded", timeout=20000)
        except Exception as fe:
            print(f"強制ログインエラー: {fe}")
        await asyncio.sleep(4)
        print(f"強制ログイン後URL: {page.url}")

    await asyncio.sleep(3)
    print(f"流通物件検索URL: {page.url}")
    return page


async def search_atbb(page) -> bool:
    """ATBBで大阪市北区 8万円以下を検索。shosai_0が存在したらTrue"""
    print("\n=== 検索フォーム操作 ===")
    await page.screenshot(path=str(OUT_DIR / "s01_search_form.png"))

    # ラジオボタン情報を取得
    radio_info = await page.evaluate("""
        () => {
            const results = [];
            document.querySelectorAll('input[type=radio]').forEach(r => {
                let label = '';
                const lb = document.querySelector('label[for="' + r.id + '"]');
                if (lb) { label = lb.textContent.trim(); }
                else {
                    let sib = r.nextSibling;
                    while (sib) {
                        if (sib.nodeType === 3) label += sib.textContent.trim();
                        else if (sib.nodeType === 1) { label += sib.textContent.trim(); break; }
                        sib = sib.nextSibling;
                    }
                }
                results.push({name:r.name, value:r.value, label:label.substring(0,30), checked:r.checked});
            });
            return results;
        }
    """)
    print(f"ラジオボタン: {len(radio_info)}件")
    for r in radio_info[:15]:
        print(f"  name={r['name']} value={r['value']} label={r['label'][:25]} checked={r['checked']}")

    # 賃貸居住用を選択
    chintai_val = None
    for r in radio_info:
        if "賃貸居住用" in r.get("label", "") or "賃貸居住" in r.get("label", ""):
            chintai_val = r["value"]
            break
    if not chintai_val:
        for r in radio_info:
            if r.get("value") == "06":
                chintai_val = "06"
                break

    if chintai_val:
        try:
            await page.locator(f'input[name="atbbShumokuDaibunrui"][value="{chintai_val}"]').click()
            print(f"賃貸居住用選択: {chintai_val}")
        except Exception as e:
            try:
                await page.evaluate(f"""
                    () => {{
                        const r = document.querySelector('input[name="atbbShumokuDaibunrui"][value="{chintai_val}"]');
                        if (r) {{ r.checked = true; r.dispatchEvent(new Event('change', {{bubbles:true}})); }}
                    }}
                """)
                print(f"賃貸居住用JS選択: {chintai_val}")
            except Exception as e2:
                print(f"賃貸居住用選択失敗: {e2}")
    else:
        print("賃貸居住用ラジオが見つからず - value=06 を試みる")
        try:
            await page.evaluate("""
                () => {
                    const r = document.querySelector('input[value="06"]');
                    if (r) { r.checked = true; r.dispatchEvent(new Event('change', {bubbles:true})); }
                }
            """)
        except Exception:
            pass

    await asyncio.sleep(1)
    await page.screenshot(path=str(OUT_DIR / "s02_chintai_selected.png"))

    # フォーム内のすべてのINPUTを表示して確認
    all_inputs = await page.evaluate("""
        () => Array.from(document.querySelectorAll('input, textarea'))
            .filter(el => el.offsetParent !== null || el.type === 'hidden')
            .map(el => ({
                tag: el.tagName, type: el.type||'', name: el.name||'',
                id: el.id||'', placeholder: (el.placeholder||'').substring(0,40),
                value: (el.value||'').substring(0,20)
            }))
    """)
    print(f"フォーム入力要素: {len(all_inputs)}件")
    for inp in all_inputs:
        print(f"  [{inp['type']}] name={inp['name']} id={inp['id']} placeholder={inp['placeholder']}")

    # フリーワード検索 - フィールド名は freeWordSearchSubject
    fw_filled = False

    # 方法1: 既知のID/name
    for field_id in ['freeWordSearchSubject', 'freeWordSearch', 'freeword', 'freeWord']:
        try:
            el = page.locator(f'#{field_id}, input[name="{field_id}"]').first
            if await el.is_visible(timeout=1000):
                # labelが邪魔なのでJSで直接値をセット
                await page.evaluate(f"""
                    () => {{
                        const el = document.getElementById('{field_id}') ||
                                   document.querySelector('input[name="{field_id}"]');
                        if (el) {{
                            el.focus();
                            el.value = '大阪市北区 8万円以下';
                            el.dispatchEvent(new Event('input', {{bubbles:true}}));
                            el.dispatchEvent(new Event('change', {{bubbles:true}}));
                        }}
                    }}
                """)
                fw_filled = True
                print(f"フリーワード入力(JS): {field_id}")
                break
        except Exception:
            pass

    # 方法2: placeholderラベルを非表示にしてからクリック
    if not fw_filled:
        try:
            await page.evaluate("""
                () => {
                    // placeholderラベルを非表示に
                    const hint = document.getElementById('freeWordHint');
                    if (hint) hint.style.display = 'none';
                    const el = document.querySelector('input[type="text"]');
                    if (el) {
                        el.focus();
                        el.value = '大阪市北区 8万円以下';
                        el.dispatchEvent(new Event('input', {bubbles:true}));
                        el.dispatchEvent(new Event('change', {bubbles:true}));
                    }
                }
            """)
            fw_filled = True
            print("フリーワード入力(JS fallback)")
        except Exception as e:
            print(f"フリーワード入力失敗: {e}")

    if fw_filled:
        await asyncio.sleep(0.5)
        # 検索ボタン
        clicked = False
        for btn_id in ['freeWordSearchSubjectButton']:
            try:
                btn = page.locator(f'#{btn_id}').first
                if await btn.is_visible(timeout=1000):
                    await btn.click()
                    print(f"検索ボタンクリック: #{btn_id}")
                    clicked = True
                    break
            except Exception:
                pass
        if not clicked:
            for btn_sel in ['input[value="フリーワード検索"]', 'input[value="検索"]', 'button[id*="freeWord"]']:
                try:
                    btn = page.locator(btn_sel).first
                    if await btn.is_visible(timeout=1000):
                        await btn.click()
                        print(f"検索ボタン: {btn_sel}")
                        clicked = True
                        break
                except Exception:
                    pass
        if not clicked:
            await page.keyboard.press("Enter")
            print("Enter送信")
    else:
        print("フリーワードフィールドなし - 大阪府リンク/チェックボックスを試行")
        # 大阪府を直接クリック
        osaka_clicked = False
        try:
            osaka_link = page.locator('a:has-text("大阪府"), label:has-text("大阪府")').first
            if await osaka_link.is_visible(timeout=2000):
                await osaka_link.click()
                print("大阪府リンクをクリック")
                await asyncio.sleep(3)
                osaka_clicked = True
        except Exception as oe:
            print(f"大阪府リンクエラー: {oe}")

        if not osaka_clicked:
            # チェックボックスで大阪府を探す
            await page.evaluate("""
                () => {
                    // 「大阪府」テキストを含む要素の直近inputを探す
                    for (const el of document.querySelectorAll('*')) {
                        if (el.children.length === 0 && (el.textContent||'').trim() === '大阪府') {
                            // 親から兄弟のinputを探す
                            let p = el.parentElement;
                            for (let i = 0; i < 3; i++) {
                                if (!p) break;
                                const cb = p.querySelector('input[type=checkbox], input[type=radio]');
                                if (cb) { cb.checked = true; cb.dispatchEvent(new Event('change',{bubbles:true})); return; }
                                p = p.parentElement;
                            }
                            // 前のsibling
                            let sib = el.previousElementSibling;
                            if (sib && sib.tagName === 'INPUT') {
                                sib.checked = true; sib.dispatchEvent(new Event('change',{bubbles:true}));
                            }
                        }
                    }
                }
            """)
            await asyncio.sleep(1)

        # 検索ボタン
        for sel in ['input[type="submit"]', 'button:has-text("検索")']:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=2000):
                    await el.click()
                    print(f"検索ボタン: {sel}")
                    break
            except Exception:
                continue

    await asyncio.sleep(5)
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=15000)
    except Exception:
        pass
    await asyncio.sleep(3)

    await page.screenshot(path=str(OUT_DIR / "s03_search_results.png"))
    print(f"検索結果URL: {page.url}")

    # ページテキスト（結果確認）
    body = await page.evaluate("() => document.body.innerText.substring(0, 2000)")
    print(f"ページテキスト:\n{body[:1000]}")

    shosai0 = await page.evaluate("() => !!document.getElementById('shosai_0')")
    print(f"shosai_0 exists: {shosai0}")
    return shosai0


async def investigate_infosheet(page, ctx, prop_idx: int = 0):
    """物件詳細→インフォシートの構造調査"""
    print(f"\n=== 物件{prop_idx+1}の詳細ページへ ===")
    await page.evaluate(f"document.getElementById('shosai_{prop_idx}').click()")
    await page.wait_for_load_state("domcontentloaded", timeout=20000)
    await asyncio.sleep(4)
    print(f"詳細URL: {page.url}")
    await page.screenshot(path=str(OUT_DIR / "s04_detail.png"))

    # インフォシートボタンを探す
    btn = page.locator('#infoSheetButtonTop_0')
    if not await btn.is_visible(timeout=3000):
        btn = page.locator('button:has-text("インフォシート")').first
    if not await btn.is_visible(timeout=3000):
        # すべてのボタンを表示
        all_btns = await page.evaluate("""
            () => Array.from(document.querySelectorAll('button, a'))
                .filter(el => el.offsetParent !== null)
                .map(el => ({text:(el.innerText||'').trim().substring(0,30), id:el.id||''}))
                .filter(x => x.text)
        """)
        print("ボタン一覧:", all_btns[:20])
        return

    print("インフォシートボタン発見 → クリック")
    async with ctx.expect_page(timeout=10000) as np_info:
        await btn.click()
    info_tab = await np_info.value
    await info_tab.wait_for_load_state("domcontentloaded", timeout=20000)
    await asyncio.sleep(6)  # React SPA描画待ち

    infosheet_url = info_tab.url
    print(f"\nインフォシートURL: {infosheet_url}")
    await info_tab.screenshot(path=str(OUT_DIR / "s05_infosheet_default.png"))

    # ページテキスト
    body = await info_tab.evaluate("() => document.body.innerText")
    print(f"\nページテキスト (先頭2000文字):\n{body[:2000]}")

    # 全インタラクティブ要素
    els = await info_tab.evaluate(
        "() => Array.from(document.querySelectorAll('button, a, [role=\"button\"], select'))"
        ".map(el => ({"
        "text: (el.innerText||el.value||el.getAttribute('aria-label')||el.getAttribute('title')||'')"
        ".trim().split(/\\s+/).join(' ').substring(0,50),"
        "tag: el.tagName, id: el.id||'', cls: el.className.substring(0,60)"
        "}))"
        ".filter(x => x.text.length > 0 || x.id.length > 0)"
    )
    print(f"\n全要素 ({len(els)}件):")
    for el in els:
        mark = '★' if any(k in el['text'] for k in ['編集', '設定', 'PDF', '印刷', '一般', '客付', '手数料', 'menu', 'Menu', 'ハンバーガー']) else ' '
        print(f"  {mark}[{el['tag']}] '{el['text'][:45]}' id={el['id'][:30]} cls={el['cls'][:40]}")

    # ヘッダーボタン詳細
    header_btns = await info_tab.evaluate("""
        () => Array.from(document.querySelectorAll('header button, [class*="header"] button, [class*="Header"] button, nav button, [class*="nav"] button'))
            .map(el => ({
                text: (el.innerText||el.getAttribute('aria-label')||'').trim().substring(0,40),
                id: el.id||'',
                cls: el.className.substring(0,80),
                html: el.outerHTML.substring(0,200)
            }))
    """)
    print(f"\nヘッダーボタン: {len(header_btns)}件")
    for b in header_btns:
        print(f"  text='{b['text']}' id={b['id']}")
        print(f"    cls={b['cls'][:60]}")
        print(f"    html={b['html'][:120]}")

    # 座標ソート済み全ボタン
    all_btns = await info_tab.evaluate("""
        () => Array.from(document.querySelectorAll('button, [role="button"]'))
            .map(el => {
                const r = el.getBoundingClientRect();
                return {
                    x: Math.round(r.left), y: Math.round(r.top),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: (el.innerText||el.getAttribute('aria-label')||'').trim().substring(0,30),
                    id: el.id||'',
                    cls: el.className.substring(0,60)
                };
            })
            .filter(b => b.h > 0)
            .sort((a,b) => a.y - a.y || a.x - b.x)
    """)
    print(f"\n全ボタン ({len(all_btns)}件):")
    for b in all_btns[:20]:
        print(f"  ({b['x']},{b['y']}) {b['w']}x{b['h']} text='{b['text'][:25]}' id={b['id'][:20]} cls={b['cls'][:40]}")

    # SVGアイコン系ボタン（テキストなし）
    icon_btns = await info_tab.evaluate("""
        () => Array.from(document.querySelectorAll('button, [role="button"]'))
            .filter(el => {
                const t = (el.innerText||'').trim();
                return t.length < 3 && el.querySelector('svg');
            })
            .map(el => ({
                id: el.id||'',
                cls: el.className.substring(0,80),
                html: el.outerHTML.substring(0,250),
                'aria-label': el.getAttribute('aria-label')||''
            }))
    """)
    print(f"\nSVGアイコンボタン ({len(icon_btns)}件):")
    for b in icon_btns:
        print(f"  id={b['id']} aria-label={b['aria-label']}")
        print(f"  cls={b['cls'][:60]}")
        print(f"  html={b['html'][:150]}")
        print()

    # 手数料・一般・客付け関連テキスト
    fee_els = await info_tab.evaluate("""
        () => Array.from(document.querySelectorAll('*'))
            .filter(el => {
                const t = (el.innerText||el.textContent||'').trim();
                return t.length > 0 && t.length < 60 &&
                    (t.includes('手数料') || t.includes('一般') || t.includes('客付') ||
                     t.includes('表示') || t.includes('設定') || t.includes('チェック') ||
                     t.includes('社宅') || t.includes('編集') || t.includes('メニュー'));
            })
            .filter(el => el.children.length === 0 && el.offsetParent !== null)
            .map(el => ({
                text: (el.innerText||el.textContent||'').trim(),
                tag: el.tagName, cls: el.className.substring(0,50), id: el.id||''
            }))
    """)
    print(f"\n関連テキスト要素 ({len(fee_els)}件):")
    for e in fee_els:
        print(f"  [{e['tag']}] '{e['text']}' cls={e['cls'][:40]} id={e['id']}")

    # ── 元図面PDF保存 ──
    moto_pdf = str(OUT_DIR / "s_mototsuke.pdf")
    await info_tab.pdf(path=moto_pdf, format="A4", print_background=True)
    print(f"\n✓ 元図面PDF: {moto_pdf} ({os.path.getsize(moto_pdf):,} bytes)")

    # HTML保存
    html = await info_tab.content()
    with open(str(OUT_DIR / "infosheet.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML保存: {len(html):,} bytes")

    # ── 編集メニュー探索 ──
    print("\n\n=== 編集メニュー探索 ===")

    # ① テキストベース
    for label in ["編集メニュー", "編集", "設定", "メニュー", "オプション"]:
        try:
            matches = await info_tab.locator(f":text('{label}')").all()
            for m in matches:
                if await m.is_visible(timeout=300):
                    bb = await m.bounding_box()
                    print(f"  テキスト '{label}' at ({bb['x']:.0f},{bb['y']:.0f})")
                    await m.click()
                    await asyncio.sleep(2)
                    await info_tab.screenshot(path=str(OUT_DIR / "s06_after_edit_click.png"))
                    # クリック後のメニュー要素
                    after = await info_tab.evaluate("""
                        () => Array.from(document.querySelectorAll('li, [role="menuitem"], [role="option"]'))
                            .filter(el => el.offsetParent !== null && (el.innerText||'').trim())
                            .map(el => ({text:(el.innerText||'').trim().substring(0,40), cls:el.className.substring(0,40)}))
                    """)
                    print(f"  クリック後メニュー項目: {after[:10]}")
                    break
        except Exception:
            pass

    # ② SVGアイコンボタンを全部試してみる
    print("\n=== SVGアイコンボタンを順に試す ===")
    for i, b in enumerate(icon_btns[:5]):
        try:
            sel = f"#{b['id']}" if b['id'] else None
            if not sel:
                # クラスで探す
                cls_part = b['cls'].split()[0] if b['cls'].split() else ''
                sel = f".{cls_part}" if cls_part else None
            if not sel:
                continue
            el = info_tab.locator(sel).first
            if await el.is_visible(timeout=300):
                print(f"  アイコンボタン{i+1}クリック: {sel}")
                await el.click()
                await asyncio.sleep(2)
                await info_tab.screenshot(path=str(OUT_DIR / f"s07_icon_btn_{i}.png"))
                # クリック後の新要素
                after2 = await info_tab.evaluate("""
                    () => Array.from(document.querySelectorAll('li, [role="menuitem"], [role="option"], [class*="menu"], [class*="Menu"]'))
                        .filter(el => el.offsetParent !== null && (el.innerText||'').trim())
                        .map(el => ({text:(el.innerText||'').trim().substring(0,50), cls:el.className.substring(0,50)}))
                """)
                if after2:
                    print(f"  → 出現要素: {after2[:10]}")
                    # 手数料・一般・客付けが含まれるか
                    fee_items = [x for x in after2 if any(k in x['text'] for k in ['手数料', '一般', '客付', '表示', '非表示'])]
                    if fee_items:
                        print(f"  ★ 手数料関連項目発見: {fee_items}")
        except Exception as e2:
            print(f"  アイコンボタン{i+1}エラー: {e2}")

    print(f"\n=== 完了。ブラウザを30秒開けています ===")
    await asyncio.sleep(30)
    await info_tab.close()


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
        page = await login_atbb(page, ctx)

        # ② 検索
        has_results = await search_atbb(page)

        if not has_results:
            print("\nshosai_0が見つかりません - スクリーンショットを確認してください")
            print("ブラウザを60秒開けています...")
            await asyncio.sleep(60)
            await browser.close()
            return

        # ③ インフォシート調査
        await investigate_infosheet(page, ctx, prop_idx=0)

        await browser.close()


asyncio.run(main())
