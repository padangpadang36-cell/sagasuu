# -*- coding: utf-8 -*-
"""
Gmail APIからヒアリングメール（部屋探し依頼通知）を読み込み、
進捗IDと就業先情報を抽出するモジュール。

【対応メール書式】
----
000000 入居者名様についての新規依頼（部屋探し依頼）が登録されました。

進捗ID: 74377
...
進捗詳細情報

進捗ID: 74377
企業名: マグ・イゾベール株式会社
所在地: 〒315-8518 茨城県 かすみがうら市上稲吉2046番地１号
就業開始日: 2026年7月1日（水）
依頼上限賃料:
最寄駅:
入居希望日: 2026年6月27日（土）
通勤方法: 自転車 バス
社宅条件その他: 家具付き
...
----

【初回セットアップ手順】
1. Google Cloud Console (https://console.cloud.google.com/) でプロジェクト作成
2. 「APIとサービス」→「ライブラリ」→「Gmail API」を有効化
3. 「APIとサービス」→「認証情報」→「OAuthクライアントID（デスクトップアプリ）」を作成
4. ダウンロードしたJSONを「credentials.json」という名前で
   システムファイル/フォルダに置く
5. 初回実行時にブラウザが開いてGoogleログインを求められるので承認する
   → token.json が自動生成されて以降は自動ログイン
"""

import sys
import re
import base64
from pathlib import Path
from typing import Optional

if __name__ == '__main__' and hasattr(sys.stdout, 'buffer'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

BASE_DIR         = Path(__file__).parent
CREDENTIALS_PATH = BASE_DIR / "credentials.json"
TOKEN_PATH       = BASE_DIR / "token.json"
SCOPES           = ['https://www.googleapis.com/auth/gmail.readonly']


# ══════════════════════════════════════════════════════════
#  Gmail 認証
# ══════════════════════════════════════════════════════════

def get_gmail_service():
    """Gmail APIサービスオブジェクトを取得する（初回はブラウザ認証）"""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_PATH.exists():
                raise FileNotFoundError(
                    f"credentials.json が見つかりません: {CREDENTIALS_PATH}\n"
                    "Google Cloud ConsoleでOAuthクライアントIDを作成し、\n"
                    "credentials.json としてシステムファイル/フォルダに配置してください。"
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, 'w', encoding='utf-8') as f:
            f.write(creds.to_json())

    from googleapiclient.discovery import build
    return build('gmail', 'v1', credentials=creds)


# ══════════════════════════════════════════════════════════
#  メール本文取得
# ══════════════════════════════════════════════════════════

def _decode_part(part: dict) -> str:
    data = part.get('body', {}).get('data', '')
    if not data:
        return ''
    return base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')


def get_email_body(payload: dict) -> str:
    """メッセージペイロードからプレーンテキスト本文を抽出する"""
    mime = payload.get('mimeType', '')

    if mime == 'text/plain':
        return _decode_part(payload)

    if mime == 'text/html':
        return re.sub(r'<[^>]+>', '', _decode_part(payload))

    if 'multipart' in mime:
        # text/plain を最優先
        for part in payload.get('parts', []):
            if part.get('mimeType') == 'text/plain':
                body = _decode_part(part)
                if body.strip():
                    return body
        # ネストされた multipart
        for part in payload.get('parts', []):
            if 'multipart' in part.get('mimeType', ''):
                for sub in part.get('parts', []):
                    if sub.get('mimeType') == 'text/plain':
                        body = _decode_part(sub)
                        if body.strip():
                            return body
        # text/html にフォールバック
        for part in payload.get('parts', []):
            if part.get('mimeType') == 'text/html':
                return re.sub(r'<[^>]+>', '', _decode_part(part))

    return ''


def fetch_emails(service, query: str, max_results: int = 200) -> list[dict]:
    """Gmailからメールを取得する"""
    result = service.users().messages().list(
        userId='me', q=query, maxResults=max_results).execute()
    messages = result.get('messages', [])

    emails = []
    for m in messages:
        try:
            msg = service.users().messages().get(
                userId='me', id=m['id'], format='full').execute()
            payload = msg['payload']
            headers = {h['name'].lower(): h['value']
                       for h in payload.get('headers', [])}
            emails.append({
                'id':      m['id'],
                'subject': headers.get('subject', ''),
                'from':    headers.get('from', ''),
                'date':    headers.get('date', ''),
                'body':    get_email_body(payload),
            })
        except Exception as e:
            print(f"  メール取得エラー (id={m['id']}): {e}")

    print(f"  {len(emails)}件のメールを取得")
    return emails


# ══════════════════════════════════════════════════════════
#  「フィールド名: 値」形式メールの構造化パーサー
# ══════════════════════════════════════════════════════════

def _get_field(text: str, *field_names: str, default: str = '') -> str:
    """
    「フィールド名: 値」形式のテキストから値を取得する。
    複数のfield_namesを順番に試し、最初にマッチしたものを返す。
    空の場合はdefaultを返す。
    """
    for name in field_names:
        pattern = rf'^{re.escape(name)}[ \t]*[：:][ \t]*(.*)'
        m = re.search(pattern, text, re.MULTILINE)
        if m:
            value = m.group(1).strip()
            if value:
                return value
    return default


def _get_last_field(text: str, field_name: str, default: str = '') -> str:
    """
    同名フィールドが複数存在する場合に最後のマッチを返す（例: 所在地 が2か所ある）。
    """
    pattern = rf'^{re.escape(field_name)}[ \t]*[：:][ \t]*(.*)'
    matches = re.findall(pattern, text, re.MULTILINE)
    for v in reversed(matches):
        v = v.strip()
        if v:
            return v
    return default


def parse_hearing_email(email: dict) -> dict:
    """
    部屋探し依頼通知メール1件を解析して構造化データを返す。

    返却辞書のキー:
        email_id, subject, date
        shinkoku_id      : 進捗ID
        case_id          : 案件ID
        group            : グループ
        assignee         : 担当者名
        resident_name    : 入居者名（氏名）
        employee_no      : 社員番号
        employee_type    : 社員区分
        company_name     : 企業名
        work_address     : 就業先住所（2番目の所在地）
        work_start_date  : 就業開始日
        nearest_station  : 最寄駅
        move_in_date     : 入居希望日
        occupancy_type   : 入居形態
        commute_method   : 通勤方法
        housing_condition: 社宅条件その他
        rent_limit       : 依頼上限賃料（数値 or None）
        moving_required  : 引越（必要/不要）
        rental_furniture : レンタル家具
        current_address  : 現住所（1番目の所在地）
        remarks          : その他備考
    """
    body = email['body']

    # ── 進捗ID（詳細情報セクションの「進捗ID:」を使う）──
    # 冒頭の「進捗ID: 74377」と詳細内の「進捗ID: 74377」の両方にある
    shinkoku_id = _get_field(body, '進捗ID', 'ID', '進捗No')

    # ── 案件ID ──
    case_id = _get_field(body, '案件ID')

    # ── グループ・担当者 ──
    group    = _get_field(body, 'グループ')
    assignee = _get_field(body, '担当者名')

    # ── 入居者情報 ──
    resident_name = _get_field(body, '氏名', '入居者名')
    employee_no   = _get_field(body, '社員番号')
    employee_type = _get_field(body, '社員区分')
    current_addr  = _get_field(body, '所在地')  # 1番目の所在地 = 現住所

    # ── 企業・就業先情報 ──
    company_name   = _get_field(body, '企業名')
    # 所在地が2つある → 最後の1つが就業先住所
    work_address   = _get_last_field(body, '所在地')
    work_start_date = _get_field(body, '就業開始日', '就業予定日')
    nearest_station = _get_field(body, '最寄駅', '最寄り駅', '最寄駅備考')

    # ── 入居条件 ──
    move_in_date      = _get_field(body, '入居希望日')
    occupancy_type    = _get_field(body, '入居形態')
    commute_method    = _get_field(body, '通勤方法')
    housing_condition = _get_field(body, '社宅条件その他', '社宅条件')
    moving_required   = _get_field(body, '引越', '引越し')
    rental_furniture  = _get_field(body, 'レンタル家具')
    remarks           = _get_field(body, 'その他備考', 'その他', '備考')

    # ── 依頼上限賃料（数値化） ──
    rent_raw = _get_field(body, '依頼上限賃料', '上限賃料', '家賃上限')
    rent_limit = None
    if rent_raw:
        m = re.search(r'[\d,]+', rent_raw)
        if m:
            try:
                rent_limit = int(m.group(0).replace(',', ''))
            except ValueError:
                pass

    # work_addressとcurrent_addrが同一の場合は就業先を取り直す
    # (メール内に所在地が1つしかない場合)
    if work_address == current_addr:
        # 企業情報セクション以降にある所在地を抽出
        company_section = ''
        m_company = re.search(r'企業名\s*[：:]\s*.+', body)
        if m_company:
            company_section = body[m_company.start():]
        if company_section:
            m2 = re.search(r'^所在地\s*[：:]\s*(.*)', company_section, re.MULTILINE)
            if m2 and m2.group(1).strip():
                work_address = m2.group(1).strip()

    # 郵便番号を住所から除去（検索用に整形）
    def clean_address(addr: str) -> str:
        return re.sub(r'^〒[\d\-]+\s*', '', addr).strip()

    return {
        'email_id':         email['id'],
        'subject':          email['subject'],
        'date':             email['date'],
        'shinkoku_id':      shinkoku_id,
        'case_id':          case_id,
        'group':            group,
        'assignee':         assignee,
        'resident_name':    resident_name,
        'employee_no':      employee_no,
        'employee_type':    employee_type,
        'company_name':     company_name,
        'work_address':     clean_address(work_address),
        'work_address_raw': work_address,
        'current_address':  clean_address(current_addr),
        'work_start_date':  work_start_date,
        'nearest_station':  nearest_station,
        'move_in_date':     move_in_date,
        'occupancy_type':   occupancy_type,
        'commute_method':   commute_method,
        'housing_condition': housing_condition,
        'rent_limit':       rent_limit,
        'moving_required':  moving_required,
        'rental_furniture': rental_furniture,
        'remarks':          remarks,
    }


# ══════════════════════════════════════════════════════════
#  メイン: Gmail から全件取得
# ══════════════════════════════════════════════════════════

def fetch_all_hearing_data(
    query: str = 'subject:部屋探し依頼',
    max_results: int = 200,
) -> list[dict]:
    """
    Gmail から全ヒアリングメールを取得・解析して返す。

    Parameters
    ----------
    query       : Gmail 検索クエリ（件名「部屋探し依頼」を想定）
    max_results : 最大取得件数

    Returns
    -------
    list of dict: parse_hearing_email() の戻り値リスト
    """
    print("── Gmail からヒアリングメール取得中 ──")
    service = get_gmail_service()
    emails  = fetch_emails(service, query=query, max_results=max_results)

    results = []
    for email in emails:
        data = parse_hearing_email(email)
        if not data['shinkoku_id']:
            print(f"  スキップ（進捗ID未検出）: {email['subject'][:50]}")
            continue
        results.append(data)

    # 同一進捗IDは最新メールを優先（リストは新着順）
    seen = set()
    deduped = []
    for item in results:
        sid = item['shinkoku_id']
        if sid in seen:
            continue
        seen.add(sid)
        deduped.append(item)

    print(f"  解析完了: {len(deduped)}件（重複除去後）")
    return deduped


def build_shinkoku_map(hearing_data: list[dict]) -> dict[str, dict]:
    """進捗ID → 就業先情報の辞書を返す"""
    return {
        str(d['shinkoku_id']).strip(): {
            'case_id':          d.get('case_id', ''),       # 案件ID（フォルダ・ファイル名に使用）
            'work_address':     d.get('work_address', ''),
            'work_address_raw': d.get('work_address_raw', ''),
            'current_address':  d.get('current_address', ''),  # 現住所（個人の所在地）
            'nearest_station':  d.get('nearest_station', ''),
            'work_start_date':  d.get('work_start_date', ''),
            'company_name':     d.get('company_name', ''),
            'move_in_date':     d.get('move_in_date', ''),
            'occupancy_type':   d.get('occupancy_type', ''),
            'commute_method':   d.get('commute_method', ''),
            'housing_condition': d.get('housing_condition', ''),
            'rent_limit':       d.get('rent_limit'),
            'moving_required':  d.get('moving_required', ''),
            'resident_name':    d.get('resident_name', ''),
            'remarks':          d.get('remarks', ''),
        }
        for d in hearing_data
        if d.get('shinkoku_id')
    }


# ══════════════════════════════════════════════════════════
#  テキスト入力モード（Gmailを使わない場合）
# ══════════════════════════════════════════════════════════

def parse_email_text(text: str) -> dict:
    """
    メール本文テキスト（文字列）を直接渡してパースする。
    Gmail APIを使わずにテキストをコピペして処理したい場合に使用。

    Parameters
    ----------
    text : メール本文全体の文字列

    Returns
    -------
    dict: parse_hearing_email() と同形式の辞書
    """
    pseudo_email = {
        'id':      'manual_input',
        'subject': '',
        'from':    '',
        'date':    '',
        'body':    text,
    }
    return parse_hearing_email(pseudo_email)


def parse_email_texts(texts: list[str]) -> list[dict]:
    """
    複数のメール本文テキストをまとめてパースする。
    テキストファイルに保存したメール群を一括処理する場合に使用。
    """
    results = []
    for i, text in enumerate(texts):
        data = parse_email_text(text)
        if data.get('shinkoku_id'):
            results.append(data)
        else:
            print(f"  スキップ（進捗ID未検出）: テキスト{i+1}件目")
    return results


def load_pasted_email_file(file_path) -> list[dict]:
    """
    「メール貼り付け.txt」を読み込んでメール本文を解析する。

    複数のメールを1ファイルにまとめる場合は
    「========」（= を8個以上）で区切る。
    「#」で始まる行はコメントとして無視される。

    Parameters
    ----------
    file_path : Path or str

    Returns
    -------
    list of dict: parse_hearing_email() と同形式の辞書リスト
    """
    from pathlib import Path as _Path
    path = _Path(file_path)
    text = path.read_text(encoding='utf-8', errors='replace')

    # # または ＃ で始まるコメント行を除去
    lines = text.split('\n')
    clean_lines = [
        l for l in lines
        if not l.strip().startswith('#') and not l.strip().startswith('＃')
    ]
    clean_text = '\n'.join(clean_lines)

    # 区切り文字（= または - が8個以上の行）でメールを分割
    parts = re.split(r'\n={8,}\n|\n-{8,}\n', clean_text)

    results = []
    for i, part in enumerate(parts, 1):
        part = part.strip()
        if not part:
            continue
        data = parse_email_text(part)
        if data.get('shinkoku_id'):
            results.append(data)
            print(f"  解析済み: 進捗ID={data['shinkoku_id']}  "
                  f"企業={data.get('company_name', '')}  "
                  f"就業地={data.get('work_address', '')[:30]}")
        else:
            print(f"  スキップ（進捗ID未検出）: {i}件目")

    # 同一進捗IDは後に書かれたものを優先
    seen: dict[str, dict] = {}
    for item in results:
        seen[str(item['shinkoku_id']).strip()] = item
    deduped = list(seen.values())

    print(f"  貼り付けファイル解析完了: {len(deduped)}件")
    return deduped


# ══════════════════════════════════════════════════════════
#  単体テスト（サンプルメールで動作確認）
# ══════════════════════════════════════════════════════════

SAMPLE_EMAIL = """000000 入居者名様についての新規依頼（部屋探し依頼）が登録されました。

進捗ID: 74377
グループ: 関東第二営業部 つくばG
担当者名: 法人営業様
入居者名: 入居者名
社員番号: 000000

進捗情報をご確認ください。

★進捗ページへ

※このメールはシステムより自動送信されています。

------------------------------------------------------------
進捗詳細情報

案件ID: 161291
グループ: 関東第二営業部 つくばG
事務拠点:
進捗ID: 74377
案件種別: 部屋探し依頼
承認パターン: 【社宅依頼】新規
社宅.com担当:
登録日時: 2026年6月8日（月）10:29:50
担当者名: 法人営業様
担当連絡先: 000-0000-0000
メールアドレス: eigyou@test.com
社員番号: 000000
紐付け社員ID:
氏名: 入居者名
フリガナ: ニュウキョシャメイ
生年月日: 2002年12月6日（金）
入社年月日:
所属:
社員区分: 技術社員（エリア限定社員）
入居人数:
入居者情報備考:
住居区分: 当社社宅以外
所在地: 〒274-0825 千葉県 船橋市前原西1-7-14グランドメゾン東船橋301
社用携帯:
個人携帯: 000-0000-0000
その他の電話番号:
連絡希望時間・備考:
PCメールアドレス: nyuukyosya@test.com
携帯メールアドレス:
メールアドレス:
依頼上限賃料:
入居希望日: 2026年6月27日（土）
入居形態:
同居人:
通勤方法: 自転車 バス
社宅条件その他: 家具付き
駐車場: 不要
契約名義: 会社名義
契約条件備考:
企業名: マグ・イゾベール株式会社
所在地: 〒315-8518 茨城県 かすみがうら市上稲吉2046番地１号
就業開始日: 2026年7月1日（水）
入社前研修:
最寄駅:
最寄駅備考:
引越: 必要
レンタル家具: 不要
その他備考: 就業先付近で物件を探してください。
"""

if __name__ == '__main__':
    print("=== サンプルメールでパーステスト ===")
    result = parse_email_text(SAMPLE_EMAIL)
    for k, v in result.items():
        if k not in ('email_id',):
            print(f"  {k:20}: {v}")

    print("\n=== Gmail API テスト（credentials.json が必要）===")
    try:
        data = fetch_all_hearing_data(query='subject:部屋探し依頼', max_results=5)
        for d in data:
            print(f"  進捗ID={d['shinkoku_id']:8}  企業={d['company_name']}  "
                  f"就業地={d['work_address'][:30]}")
    except FileNotFoundError as e:
        print(f"  スキップ: {e}")
