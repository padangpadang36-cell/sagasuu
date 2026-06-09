# -*- coding: utf-8 -*-
"""テスト用入力Excelを作成するスクリプト"""
import openpyxl, shutil
from pathlib import Path

base = Path(__file__).parent.parent
src = base / "入力データ" / "テンプレート_依頼一覧.xlsx"
dst = base / "入力データ" / "依頼一覧_テスト.xlsx"

shutil.copy(src, dst)

wb = openpyxl.load_workbook(dst)
ws = wb.active
ws.append([
    "テスト太郎",
    "東京都新宿区西新宿2-8-1",
    "大阪府大阪市北区梅田3-1-1",
    "大阪市北区",
    "2026/06/01",
    "家具家電なし社宅",
    80000,
    "1K",
    "電車",
    "30分以内",
])
wb.save(dst)
print(f"テスト入力Excel作成: {dst}")
