# -*- coding: utf-8 -*-
"""リアプロ: 空室検索→room_detail→図面ボタン(オレンジ/緑)を確認"""
import sys, io, asyncio
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import os
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv(Path(__file__).parent.parent / ".env")
REABRO_BASE_URL = "https://www.realnetpro.com"
REABRO_ID       = os.getenv("REABRO_ID", "")
REABRO_PASS     = os.getenv("REABRO_PASS", "")

OUT_DIR = Path(__file__).parent / "デバッグ" / "reabro3"
OUT_DIR.mkdir(parents=True, exist_ok=True)

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, channel="chrome", slow_mo=300)
        ctx = await browser.new_context(viewport={"width":1280,"height":900}, locale="ja-JP",
                                        accept_downloads=True)
        page = await ctx.new_page()

        # ログイン
        await page.goto(REABRO_BASE_URL + "/index.php", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)
        await page.locator('input[name="id"]').fill(REABRO_ID)
        await page.locator('input[name="pass"]').fill(REABRO_PASS)
        await page.locator('button:has-text("ログイン")').first.click()
        await asyncio.sleep(3)

        # ─── リスト検索（建物一覧）へ直接移動 ───
        list_url = REABRO_BASE_URL + "/main.php?method=estate&display=building"
        await page.goto(list_url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)
        await page.screenshot(path=str(OUT_DIR / "01_building_list.png"))

        # 検索フォームの全要素を取得
        print("=== 検索フォーム要素 ===")
        form_info = await page.evaluate("""
            () => {
                const results = [];
                for (const el of document.querySelectorAll('input, select, textarea')) {
                    results.push({
                        tag: el.tagName, type: el.type||'', name: el.name||'',
                        id: el.id||'', placeholder: el.placeholder||''
                    });
                }
                return results;
            }
        """)
        for f in form_info:
            print(f"  {f['tag']} name={f['name']} id={f['id']} type={f['type']} ph={f['placeholder']}")

        # 都道府県セレクト→大阪を選択
        try:
            pref_sel = page.locator('select[name="pref_id"], select[name*="pref"], select[name*="ken"]').first
            if await pref_sel.is_visible(timeout=2000):
                opts = await pref_sel.evaluate(
                    "el => Array.from(el.options).map(o=>({v:o.value,t:o.text}))"
                )
                print(f"\n都道府県オプション: {opts[:10]}")
                osaka = next((o for o in opts if '大阪' in o['t']), None)
                if osaka:
                    await pref_sel.select_option(value=osaka['v'])
                    print(f"大阪を選択: {osaka}")
                    await asyncio.sleep(2)
        except Exception as e:
            print(f"都道府県セレクトエラー: {e}")

        # 市区郡セレクト
        try:
            city_sel = page.locator('select[name="city_id"], select[name*="city"], select[name*="gun"]').first
            if await city_sel.is_visible(timeout=2000):
                opts = await city_sel.evaluate(
                    "el => Array.from(el.options).map(o=>({v:o.value,t:o.text}))"
                )
                print(f"市区郡オプション: {opts[:10]}")
                kitaku = next((o for o in opts if '北区' in o['t'] or '大阪市' in o['t']), None)
                if kitaku:
                    await city_sel.select_option(value=kitaku['v'])
                    print(f"北区/大阪市を選択: {kitaku}")
                    await asyncio.sleep(1)
        except Exception as e:
            print(f"市区郡セレクトエラー: {e}")

        # 賃料上限
        try:
            rent_sel = page.locator('select[name*="rent"], input[name*="rent"]').first
            if await rent_sel.is_visible(timeout=1000):
                tag = await rent_sel.evaluate("el => el.tagName")
                if tag == 'SELECT':
                    opts = await rent_sel.evaluate("el => Array.from(el.options).map(o=>({v:o.value,t:o.text}))")
                    print(f"賃料オプション: {opts[:8]}")
                    target = next((o for o in opts if '8' in o['t'] or '80000' in o['v']), None)
                    if target:
                        await rent_sel.select_option(value=target['v'])
                else:
                    await rent_sel.fill("8")
        except Exception as e:
            print(f"賃料エラー: {e}")

        # 検索ボタンクリック
        for btn_text in ["検索する", "検索", "絞り込む"]:
            try:
                btn = page.get_by_text(btn_text, exact=True).first
                if await btn.is_visible(timeout=1000):
                    await btn.click()
                    await asyncio.sleep(3)
                    print(f"検索ボタン'{btn_text}'クリック")
                    break
            except Exception:
                continue
        else:
            # submit ボタン
            try:
                await page.locator('input[type="submit"], button[type="submit"]').first.click()
                await asyncio.sleep(3)
            except Exception:
                pass

        print(f"\n検索後URL: {page.url}")
        await page.screenshot(path=str(OUT_DIR / "02_search_result.png"))

        # ─── 建物カードから「空室検索」ボタンのIDを取得 ───
        print("\n=== 建物カード（空室検索ボタン） ===")
        building_data = await page.evaluate("""
            () => {
                const results = [];
                // 空室検索ボタン
                for (const btn of document.querySelectorAll('[id][onclick*="kuushitsu"], a[href*="room"], button')) {
                    const t = btn.innerText.trim().replace(/\\s+/g,' ');
                    if (t === '空室検索' || t.includes('空室')) {
                        const bldId = btn.id || btn.getAttribute('data-id') || '';
                        const card = btn.closest('.building-card, .item, li, tr, div[class*="item"]');
                        const name = card ? card.querySelector('h2,h3,.name,.title')?.innerText.trim() : '';
                        results.push({
                            id: bldId,
                            text: t,
                            name: (name||'').substring(0,30),
                            onclick: (btn.getAttribute('onclick')||'').substring(0,80),
                            href: btn.href || ''
                        });
                    }
                }
                return results.slice(0, 5);
            }
        """)
        print(f"空室検索ボタン: {len(building_data)}件")
        for b in building_data:
            print(f"  id={b['id']} name={b['name']} onclick={b['onclick']}")

        # 空室検索ボタンのIDを直接 JavaScript で調べる
        all_btns = await page.evaluate("""
            () => {
                const results = [];
                for (const el of document.querySelectorAll('*[id]')) {
                    if (/^\\d+$/.test(el.id)) {
                        const t = el.innerText.trim().replace(/\\s+/g,' ').substring(0,20);
                        if (t === '空室検索') {
                            results.push({
                                id: el.id,
                                tag: el.tagName,
                                onclick: (el.getAttribute('onclick')||'').substring(0,100)
                            });
                        }
                    }
                }
                return results.slice(0, 5);
            }
        """)
        print(f"\n数値IDの空室検索ボタン: {len(all_btns)}件")
        for b in all_btns:
            print(f"  id={b['id']} tag={b['tag']} onclick={b['onclick']}")

        # 1件目の「空室検索」をクリック
        if all_btns:
            bld_id = all_btns[0]['id']
            print(f"\n  建物ID={bld_id}の空室検索をクリック...")
            try:
                await page.locator(f'[id="{bld_id}"]').click()
                await asyncio.sleep(3)
                print(f"  クリック後URL: {page.url}")
                await page.screenshot(path=str(OUT_DIR / "03_room_list.png"))

                # room_detail.php リンクを探す
                room_links = await page.evaluate("""
                    () => Array.from(document.querySelectorAll('a[href*="room_detail"]'))
                        .slice(0, 5)
                        .map(a => ({ href: a.href, text: a.innerText.trim().substring(0,30) }))
                """)
                print(f"\n  room_detailリンク: {len(room_links)}件")
                for r in room_links:
                    print(f"    [{r['text']}] {r['href']}")

                # 1件目の詳細へ
                if room_links:
                    await page.goto(room_links[0]['href'], wait_until="domcontentloaded", timeout=20000)
                    await asyncio.sleep(2)
                    print(f"\n  詳細ページURL: {page.url}")
                    await page.screenshot(path=str(OUT_DIR / "04_room_detail.png"))

                    # 図面ボタン（オレンジ=社宅.com版、緑=元図面）を探す
                    print("\n=== 図面・PDF ボタン ===")
                    pdf_btns = await page.evaluate("""
                        () => {
                            const results = [];
                            for (const el of document.querySelectorAll('a, button, input[type="button"]')) {
                                const t = (el.innerText||el.value||'').trim().replace(/\\s+/g,' ').substring(0,60);
                                const href = el.href || '';
                                const onclick = (el.getAttribute('onclick')||'').substring(0,100);
                                const style = (el.getAttribute('style')||el.style.cssText||'').substring(0,80);
                                const cls = el.className.substring(0,60);
                                if (t.match(/図面|印刷|出力|PDF|資料|factsheet|sheet|詳細/) ||
                                    href.match(/factsheet|pdf|sheet/) ||
                                    onclick.match(/factsheet|pdf|sheet/)) {
                                    results.push({ text: t, href, onclick, style, cls });
                                }
                            }
                            return results;
                        }
                    """)
                    for b in pdf_btns:
                        print(f"  ★ [{b['text']}]")
                        print(f"      href={b['href']}")
                        print(f"      onclick={b['onclick']}")
                        print(f"      style={b['style'][:50]}")
                        print(f"      cls={b['cls']}")

                    # サイドバー全体のリンクも確認
                    print("\n=== サイドバー・左カラムの全リンク ===")
                    sidebar_links = await page.evaluate("""
                        () => {
                            const sidebar = document.querySelector(
                                '.sidebar, .left, aside, #sidebar, [class*="left"], [class*="side"]'
                            );
                            if (!sidebar) return [{ note: 'サイドバー見つからず' }];
                            return Array.from(sidebar.querySelectorAll('a, button'))
                                .map(el => ({
                                    text: el.innerText.trim().replace(/\\s+/g,' ').substring(0,50),
                                    href: el.href || '',
                                    onclick: (el.getAttribute('onclick')||'').substring(0,80)
                                }));
                        }
                    """)
                    for s in sidebar_links:
                        if s.get('text'):
                            print(f"  [{s['text']}] href={s.get('href','')} onclick={s.get('onclick','')}")

                    # ページ全体テキスト（先頭500字）
                    body_text = await page.evaluate("() => document.body.innerText.substring(0,600)")
                    print(f"\nページテキスト:\n{body_text}")

            except Exception as e:
                print(f"  空室検索クリックエラー: {e}")
                import traceback; traceback.print_exc()

        # 空室一覧ダウンロード(PDF)も試す
        print("\n=== 空室一覧ダウンロード(PDF) ===")
        await page.goto(list_url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)
        try:
            dl_btn = page.get_by_text("空室一覧ダウンロード(PDF)").first
            if await dl_btn.is_visible(timeout=2000):
                print("  ボタン発見！クリックします")
                async with page.expect_download(timeout=15000) as dl_info:
                    await dl_btn.click()
                dl = await dl_info.value
                fname = dl.suggested_filename or "空室一覧.pdf"
                await dl.save_as(str(OUT_DIR / fname))
                print(f"  ✓ ダウンロード: {fname}")
        except Exception as e:
            print(f"  空室一覧DLエラー: {e}")

        print("\n=== 完了 ===")
        await browser.close()

asyncio.run(main())
