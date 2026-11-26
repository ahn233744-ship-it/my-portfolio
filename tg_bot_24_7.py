import json
import os
import re
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone

TELEGRAM_BOT_TOKEN = "8801188196:AAEaoqqmzMeRuIAWr5bpICHBVNaQ9YLjmwE"
TELEGRAM_CHAT_ID = "-1003527836779"
FIREBASE_PROJECT_ID = "himsenghorn"
FIREBASE_API_KEY = "AIzaSyDgjmb6s-dvTrN0aQXBWWX4ThAvhIF1EAM"
FIREBASE_USER_DOC = "himsenghorn"

FIRESTORE_DOC_URL = (
    f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}"
    f"/databases/(default)/documents/userData/{FIREBASE_USER_DOC}?key={FIREBASE_API_KEY}"
)


def http_json(url, method="GET", payload=None, timeout=25):
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as he:
        try:
            return json.loads(he.read().decode("utf-8"))
        except Exception:
            return {"ok": False, "error_code": he.code, "description": str(he)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def tg_api(method_name, payload=None, timeout=25):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method_name}"
    try:
        return http_json(url, method="POST" if payload else "GET", payload=payload, timeout=timeout)
    except Exception as e:
        print(f"[TG ERROR] {method_name}: {e}")
        return {"ok": False}


def purge_conflicting_webhook():
    """Purges any external webhook (such as Campaign Mudra or third-party bots) blocking getUpdates."""
    try:
        res = tg_api("deleteWebhook", {"drop_pending_updates": False})
        print(f"[TG WEBHOOK PURGED] Successfully detached external webhook: {res}")
        return bool(res and res.get("ok"))
    except Exception as e:
        print(f"[TG PURGE ERROR] {e}")
        return False


def fs_to_py(val):
    if not isinstance(val, dict):
        return val
    if "stringValue" in val:
        return val["stringValue"]
    if "integerValue" in val:
        return int(val["integerValue"])
    if "doubleValue" in val:
        return float(val["doubleValue"])
    if "booleanValue" in val:
        return bool(val["booleanValue"])
    if "nullValue" in val:
        return None
    if "arrayValue" in val:
        return [fs_to_py(x) for x in val["arrayValue"].get("values", [])]
    if "mapValue" in val:
        return {k: fs_to_py(v) for k, v in val["mapValue"].get("fields", {}).items()}
    return val


def py_to_fs(val):
    if val is None:
        return {"nullValue": None}
    if isinstance(val, bool):
        return {"booleanValue": val}
    if isinstance(val, int):
        return {"integerValue": str(val)}
    if isinstance(val, float):
        return {"doubleValue": val}
    if isinstance(val, str):
        return {"stringValue": val}
    if isinstance(val, list):
        return {"arrayValue": {"values": [py_to_fs(x) for x in val]}}
    if isinstance(val, dict):
        return {"mapValue": {"fields": {str(k): py_to_fs(v) for k, v in val.items()}}}
    return {"stringValue": str(val)}


def get_firebase_userdata():
    try:
        doc = http_json(FIRESTORE_DOC_URL, method="GET", timeout=15)
        fields = doc.get("fields", {})
        return {k: fs_to_py(v) for k, v in fields.items()}
    except Exception as e:
        print(f"[FS GET ERROR] {e}")
        return {}


def patch_firebase_fields(updates_dict):
    if not updates_dict:
        return False
    try:
        mask_params = "&".join(
            f"updateMask.fieldPaths={urllib.parse.quote(k)}" for k in updates_dict.keys()
        )
        url = f"{FIRESTORE_DOC_URL}&{mask_params}"
        payload = {"fields": {k: py_to_fs(v) for k, v in updates_dict.items()}}
        http_json(url, method="PATCH", payload=payload, timeout=15)
        return True
    except Exception as e:
        print(f"[FS PATCH ERROR] {e}")
        return False


def convert_khmer_digits(text):
    kh = "០១២៣៤៥៦៧៨៩"
    out = []
    for ch in str(text or ""):
        idx = kh.find(ch)
        out.append(str(idx) if idx != -1 else ch)
    return "".join(out)


def is_own_bot_alert(text):
    t = (text or "").strip()
    if not t:
        return True
    prefixes = ("💰", "🔔", "✅", "🍕", "🤝", "📌", "📊", "✏️", "🐷", "🏦 ✅", "🚨", "🤖")
    if any(t.startswith(p) for p in prefixes):
        return True
    if "FinSync Pro" in t or "កត់ត្រាដោយ:" in t:
        return True
    return False


def build_tx_inline_keyboard(entity_id):
    return {
        "inline_keyboard": [
            [
                {"text": "🔄 ប្ដូរ ចំណូល/ចំណាយ", "callback_data": f"flip_tx:{entity_id}"},
                {"text": "💳 ប្ដូរកាបូប", "callback_data": f"wallet_tx:{entity_id}"},
            ],
            [
                {"text": "🗑️ លុបចេញពី System & TG", "callback_data": f"del_tx:{entity_id}"}
            ],
        ]
    }


def wallet_label(w):
    return {
        "cash": "សាច់ប្រាក់សុទ្ធ (Cash)",
        "aba": "ABA Bank",
        "wing_acleda": "Wing / ACLEDA",
    }.get(w, w or "Cash")


def format_tx_card(tx):
    w_lbl = wallet_label(tx.get("wallet", "cash"))
    if tx.get("currency") == "KHR":
        amt = f"{int(tx.get('amountKHR', 0)):,} ៛ (${float(tx.get('amountUSD', 0)):.2f})"
    else:
        amt = f"${float(tx.get('amountUSD', 0)):.2f} ({int(tx.get('amountKHR', 0)):,} ៛)"
    t_str = f" ({tx['txTime']})" if tx.get("txTime") else ""
    return (
        "🏦 ✅ <b>បានបញ្ចូលប្រតិបត្តិការចូលប្រព័ន្ធ FinSync Pro (24/7 Cloud) រួចរាល់!</b>\n"
        f"• ប្រភេទ: <b>{'🟢 ចំណូល (Income)' if tx.get('type') == 'income' else '🔴 ចំណាយ (Expense)'}</b>\n"
        f"• ចំនួន: <b>{amt}</b>\n"
        f"• កាបូបធនាគារ: <b>{w_lbl}</b>\n"
        f"• កាលបរិច្ឆេទផ្ទេរ: <b>{tx.get('date', '')}{t_str}</b>\n"
        f"• បរិយាយ: <b>{tx.get('note', '')}</b>"
    )


def parse_text_transaction(raw_text, msg_unix_date=None, exchange_rate=4100):
    text = convert_khmer_digits(str(raw_text or "").strip())
    # Clean bot mentions and bot tags (e.g. @SV10_Bot, SV10_Bot, /add)
    text = re.sub(r"@[A-Za-z0-9_]+", " ", text)
    text = re.sub(r"\b[A-Za-z0-9_]*bot\b", " ", text, flags=re.I)
    text = re.sub(r"^/add\s+", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    if not text or is_own_bot_alert(text):
        return None

    wallet_id = "cash"
    bank_badge = ""
    if re.search(r"\b(aba|aba\s*pay|bakong)\b|អេប៊ីអេ|បាគង", text, re.I):
        wallet_id = "aba"
        bank_badge = "🏦 ABA"
    elif re.search(r"\b(acleda|toanchet|wing|truemoney)\b|អេស៊ីលីដា|វីង", text, re.I):
        wallet_id = "wing_acleda"
        bank_badge = "📲 Wing" if re.search(r"wing|វីង", text, re.I) else "🏦 ACLEDA"

    is_inc = bool(re.search(r"(\b(received|credited|incoming|deposit|salary|income)\b|ទទួលបាន|បានទទួល|ចូលគណនី|ផ្ទេរចូល|ចំណូល|ប្រាក់ខែ|បើកប្រាក់|^\+)", text, re.I))
    is_exp = bool(re.search(r"(\b(paid|transferred|debited|sent to|withdrawal|payment)\b|បង់ប្រាក់|បានបង់|ផ្ទេរប្រាក់|ដកប្រាក់|កាត់ប្រាក់|ចំណាយ|ទិញ|^-)", text, re.I))
    tx_type = "income" if (is_inc and not is_exp) else "expense"

    clean = re.sub(r"\(\s*\d[\d\s\-]{5,}\s*\)", " ", text)
    clean = re.sub(r"\b\d{1,2}[/\-]\d{1,2}(?:[/\-]\d{2,4})?\b", " ", clean)
    clean = re.sub(r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?\b", " ", clean, flags=re.I)

    usd_m = re.search(r"(?:USD|US\$|\$)\s*([\d,]+(?:\.\d{1,2})?)|([\d,]+(?:\.\d{1,2})?)\s*(?:USD|US\$|\$|ដុល្លារ)", clean, re.I)
    khr_m = re.search(r"(?:KHR|៛)\s*([\d,]+(?:\.\d+)?)|([\d,]+(?:\.\d+)?)\s*(?:KHR|៛|រៀល)", clean, re.I)
    k_m = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:k|ពាន់)\b", clean, re.I)

    amount_val = 0.0
    is_khr = False
    if usd_m:
        amount_val = float((usd_m.group(1) or usd_m.group(2)).replace(",", ""))
        is_khr = False
    elif khr_m:
        amount_val = float((khr_m.group(1) or khr_m.group(2)).replace(",", ""))
        is_khr = True
    elif k_m:
        amount_val = float(k_m.group(1)) * 1000.0
        is_khr = True
    else:
        gen_m = re.search(r"([\d,]+(?:\.\d+)?)", clean)
        if not gen_m:
            return None
        amount_val = float(gen_m.group(1).replace(",", ""))
        is_khr = amount_val >= 100

    if amount_val <= 0:
        return None

    amount_usd = round(amount_val / exchange_rate, 2) if is_khr else round(amount_val, 2)
    amount_khr = round(amount_val) if is_khr else round(amount_val * exchange_rate)

    note_clean = re.sub(r"(?:USD|US\$|\$|KHR|៛|រៀល|ដុល្លារ)\s*[\d,]+(?:\.\d+)?|[\d,]+(?:\.\d+)?\s*(?:USD|US\$|\$|KHR|៛|រៀល|ដុល្លារ|k|ពាន់)?", "", clean, flags=re.I)
    note_clean = re.sub(r"\s+", " ", note_clean).strip() or ("ចំណូលតាម Telegram" if tx_type == "income" else "ចំណាយតាម Telegram")
    final_note = f"[{bank_badge}] {note_clean}" if bank_badge else f"{note_clean} (Telegram)"

    dt = datetime.fromtimestamp(msg_unix_date) if msg_unix_date else datetime.now()
    date_str = dt.strftime("%Y-%m-%d")
    time_lbl = dt.strftime("%I:%M %p")

    return {
        "id": f"tx_tg24_{int(time.time()*1000)}",
        "type": tx_type,
        "amountUSD": amount_usd,
        "amountKHR": amount_khr,
        "inputCurrency": "KHR" if is_khr else "USD",
        "originalAmount": amount_khr if is_khr else amount_usd,
        "currency": "KHR" if is_khr else "USD",
        "category": "other_income" if tx_type == "income" else "food",
        "wallet": wallet_id,
        "tag": "#ផ្ទាល់ខ្លួន",
        "note": final_note,
        "date": date_str,
        "txTime": time_lbl,
        "createdAt": dt.isoformat(),
    }



def build_quick_reply_keyboard():
    return {
        "keyboard": [
            [{"text": "🍔 ម្ហូប 5000៛"}, {"text": "☕ កាហ្វេ $1.50"}],
            [{"text": "⛽ សាំង 10000៛"}, {"text": "💰 /balance"}],
            [{"text": "📊 /today"}, {"text": "📈 /month"}, {"text": "📁 /export"}],
            [{"text": "💾 /backup"}, {"text": "🌙 /eod"}, {"text": "🧠 /advice"}]
        ],
        "resize_keyboard": True,
        "is_persistent": True
    }


def tg_send_document(filename, file_bytes, caption="", chat_id=TELEGRAM_CHAT_ID, thread_id=None):
    boundary = f"----WebKitFormBoundary{int(time.time()*1000)}"
    crlf = b"\r\n"
    b_boundary = f"--{boundary}".encode("utf-8")
    body = bytearray()
    
    # chat_id
    body.extend(b_boundary + crlf)
    body.extend(b'Content-Disposition: form-data; name="chat_id"' + crlf + crlf)
    body.extend(str(chat_id).encode("utf-8") + crlf)
    
    if thread_id:
        body.extend(b_boundary + crlf)
        body.extend(b'Content-Disposition: form-data; name="message_thread_id"' + crlf + crlf)
        body.extend(str(thread_id).encode("utf-8") + crlf)
        
    if caption:
        body.extend(b_boundary + crlf)
        body.extend(b'Content-Disposition: form-data; name="caption"' + crlf + crlf)
        body.extend(str(caption).encode("utf-8") + crlf)
        body.extend(b_boundary + crlf)
        body.extend(b'Content-Disposition: form-data; name="parse_mode"' + crlf + crlf)
        body.extend(b"HTML" + crlf)
        
    # document
    body.extend(b_boundary + crlf)
    body.extend(f'Content-Disposition: form-data; name="document"; filename="{filename}"'.encode("utf-8") + crlf)
    body.extend(b"Content-Type: application/vnd.ms-excel" + crlf + crlf)
    body.extend(file_bytes)
    body.extend(crlf)
    body.extend(f"--{boundary}--".encode("utf-8") + crlf)
    
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument",
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[TG ERROR] sendDocument: {e}")
        return {"ok": False, "error": str(e)}


def handle_slash_command(cmd_text, user_data, thread_id=None):
    # Extract clean command word even if preceded by emoji (e.g. '💰 /balance' or '/balance@bot')
    m = re.search(r"/([a-zA-Z0-9_]+)", cmd_text)
    cmd = ("/" + m.group(1).lower()) if m else cmd_text.strip().lower().split()[0]
    txs = user_data.get("transactions", []) or []
    debts = user_data.get("debts", []) or []
    rate = float(user_data.get("exchangeRate", 4100) or 4100)
    today_str = datetime.now().strftime("%Y-%m-%d")
    month_prefix = today_str[:7]

    if cmd == "/balance":
        bals = {"cash": 0.0, "aba": 0.0, "wing_acleda": 0.0}
        for t in txs:
            w = t.get("wallet", "cash")
            if w not in bals:
                bals[w] = 0.0
            amt = float(t.get("amountUSD", 0) or 0)
            bals[w] += amt if t.get("type") == "income" else -amt
        tot = sum(bals.values())
        reply = (
            f"""💰 <b>របាយការណ៍សមតុល្យគ្រប់កាបូប (24/7 Cloud)</b>\n"""
            f"""• 💵 Cash: <b>${bals['cash']:.2f}</b>\n"""
            f"""• 🏦 ABA: <b>${bals['aba']:.2f}</b>\n"""
            f"""• 📲 Wing/ACLEDA: <b>${bals['wing_acleda']:.2f}</b>\n"""
            f"""💎 <b>សរុបរួម: ${tot:.2f} ({round(tot*rate):,} ៛)</b>"""
        ).replace('\\n', '\n')
    elif cmd == "/today":
        inc = sum(float(t.get("amountUSD", 0)) for t in txs if t.get("date") == today_str and t.get("type") == "income")
        exp = sum(float(t.get("amountUSD", 0)) for t in txs if t.get("date") == today_str and t.get("type") != "income")
        reply = (
            f"""📅 <b>របាយការណ៍ថ្ងៃនេះ ({today_str})</b>\n"""
            f"""• 🟢 ចំណូល: <b>+${inc:.2f}</b>\n"""
            f"""• 🔴 ចំណាយ: <b>-${exp:.2f}</b>\n"""
            f"""• ✨ សល់សុទ្ធ: <b>${(inc - exp):.2f}</b>"""
        ).replace('\\n', '\n')
    elif cmd == "/month":
        inc = sum(float(t.get("amountUSD", 0)) for t in txs if str(t.get("date", "")).startswith(month_prefix) and t.get("type") == "income")
        exp = sum(float(t.get("amountUSD", 0)) for t in txs if str(t.get("date", "")).startswith(month_prefix) and t.get("type") != "income")
        reply = (
            f"""📊 <b>របាយការណ៍ប្រចាំខែ ({month_prefix})</b>\n"""
            f"""• 🟢 ចំណូលខែនេះ: <b>+${inc:.2f}</b>\n"""
            f"""• 🔴 ចំណាយខែនេះ: <b>-${exp:.2f}</b>\n"""
            f"""• 💎 សល់សុទ្ធ: <b>${(inc - exp):.2f}</b>"""
        ).replace('\\n', '\n')
    elif cmd == "/debt":
        unpaid = [d for d in debts if d.get("status") != "paid"]
        lent = sum(float(d.get("amountUSD", 0)) for d in unpaid if d.get("type") == "lent")
        borr = sum(float(d.get("amountUSD", 0)) for d in unpaid if d.get("type") != "lent")
        reply = f"""🤝 <b>បញ្ជីបំណុលមិនទាន់ទូទាត់</b>\n• 🟢 គេជំពាក់យើង: <b>${lent:.2f}</b>\n• 🔴 យើងជំពាក់គេ: <b>${borr:.2f}</b>""".replace('\\n', '\n')
    elif cmd in ("/keyboard", "/menu", "/k"):
        reply = (
            """⌨️ <b>ក្ដារចុច 1-Tap Quick-Expense ត្រូវបានភ្ជាប់!</b>\n\n"""
            """លោកអ្នកអាចចុចលើប៊ូតុងខាងក្រោមលើអេក្រង់ Telegram ដើម្បីកត់ត្រាចំណាយរហ័ស 1-Tap ដោយមិនបាច់វាយអក្សរឡើយ៖\n\n"""
            """• 🍔 <b>ម្ហូប 5000៛</b>\n"""
            """• ☕ <b>កាហ្វេ $1.50</b>\n"""
            """• ⛽ <b>សាំង 10000៛</b>\n"""
            """• 💰 <b>/balance</b>\n"""
            """• 📊 <b>/today</b> • 📈 <b>/month</b> • 📁 <b>/export</b>"""
        ).replace('\\n', '\n')
    elif cmd in ("/start", "/help"):
        reply = (
            """🤖 <b>ស្វាគមន៍មកកាន់ FinSync Pro Bot 24/7!</b>\n\n"""
            """• កត់ត្រាចំណូល/ចំណាយ: វាយអក្សរធម្មតា ឬចុចប៊ូតុង 1-Tap ខាងក្រោម\n"""
            """• <code>/balance</code>: ពិនិត្យសមតុល្យលុយគ្រប់កាបូប\n"""
            """• <code>/today</code>: របាយការណ៍ចំណូលចំណាយថ្ងៃនេះ\n"""
            """• <code>/month</code>: របាយការណ៍ប្រចាំខែ\n"""
            """• <code>/debt</code>: បញ្ជីបំណុល\n"""
            """• <code>/export</code>: ទាញយកឯកសារ Excel (.xls) ផ្ទាល់\n"""
            """• <code>/keyboard</code>: បើកក្ដារចុច 1-Tap Quick Keyboard"""
        ).replace('\\n', '\n')
    elif cmd in ("/export", "/statement", "/excel"):
        today_date = datetime.now().strftime("%Y-%m-%d")
        fn = f"FinSync_Statement_{today_date}.xls"
        
        total_inc = sum(float(t.get("amountUSD", 0) or 0) for t in txs if t.get("type") == "income")
        total_exp = sum(float(t.get("amountUSD", 0) or 0) for t in txs if t.get("type") != "income")
        net_usd = total_inc - total_exp
        
        rows_xml = []
        for idx, t in enumerate(txs):
            is_inc = t.get("type") == "income"
            type_lbl = "ចំណូល (Income)" if is_inc else "ចំណាយ (Expense)"
            amt_usd = f"{'+' if is_inc else '-'}${float(t.get('amountUSD', 0) or 0):.2f}"
            amt_khr = f"{int(t.get('amountKHR', 0) or 0):,} ៛"
            cat = str(t.get("category", "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            w = str(t.get("wallet", "cash"))
            note = str(t.get("note", "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            date_val = str(t.get("date", ""))
            time_val = str(t.get("txTime", ""))
            
            rows_xml.append(
                f'<Row>'
                f'<Cell><Data ss:Type="Number">{idx+1}</Data></Cell>'
                f'<Cell><Data ss:Type="String">{date_val}</Data></Cell>'
                f'<Cell><Data ss:Type="String">{time_val}</Data></Cell>'
                f'<Cell><Data ss:Type="String">{type_lbl}</Data></Cell>'
                f'<Cell><Data ss:Type="String">{amt_usd}</Data></Cell>'
                f'<Cell><Data ss:Type="String">{amt_khr}</Data></Cell>'
                f'<Cell><Data ss:Type="String">{cat}</Data></Cell>'
                f'<Cell><Data ss:Type="String">{w}</Data></Cell>'
                f'<Cell><Data ss:Type="String">{note}</Data></Cell>'
                f'</Row>'
            )
            
        xml_content = (
            '<?xml version="1.0"?>\n'
            '<?mso-application progid="Excel.Sheet"?>\n'
            '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"\n'
            ' xmlns:o="urn:schemas-microsoft-com:office:office"\n'
            ' xmlns:x="urn:schemas-microsoft-com:office:excel"\n'
            ' xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">\n'
            ' <Worksheet ss:Name="FinSync Statement">\n'
            '  <Table>\n'
            '   <Row>\n'
            '    <Cell><Data ss:Type="String">ល.រ</Data></Cell>\n'
            '    <Cell><Data ss:Type="String">កាលបរិច្ឆេទ</Data></Cell>\n'
            '    <Cell><Data ss:Type="String">ម៉ោង</Data></Cell>\n'
            '    <Cell><Data ss:Type="String">ប្រភេទ</Data></Cell>\n'
            '    <Cell><Data ss:Type="String">ចំនួន ($)</Data></Cell>\n'
            '    <Cell><Data ss:Type="String">ចំនួន (៛)</Data></Cell>\n'
            '    <Cell><Data ss:Type="String">ជំពូក</Data></Cell>\n'
            '    <Cell><Data ss:Type="String">កាបូប</Data></Cell>\n'
            '    <Cell><Data ss:Type="String">កំណត់សម្គាល់</Data></Cell>\n'
            '   </Row>\n'
            + "\n".join(rows_xml) +
            '\n  </Table>\n'
            ' </Worksheet>\n'
            '</Workbook>'
        ).replace('\\n', '\n')
        
        cap = (
            f"""📊 <b>របាយការណ៍ហិរញ្ញវត្ថុផ្លូវការ FinSync Pro (.xls)</b>\n"""
            f"""📅 កាលបរិច្ឆេទ: <b>{today_date}</b>\n"""
            f"""📝 ចំនួនប្រតិបត្តិការ: <b>{len(txs)} កំណត់ត្រា</b>\n"""
            f"""• 🟢 ចំណូលសរុប: <b>+${total_inc:.2f}</b>\n"""
            f"""• 🔴 ចំណាយសរុប: <b>-${total_exp:.2f}</b>\n"""
            f"""💎 <b>សមតុល្យសុទ្ធ: ${net_usd:.2f} ({round(net_usd*rate):,} ៛)</b>"""
        ).replace('\\n', '\n')
        tg_send_document(fn, xml_content.encode("utf-8"), caption=cap, chat_id=TELEGRAM_CHAT_ID, thread_id=thread_id)
        reply = "📁 <b>បានផ្ញើឯកសារ Excel Statement (.xls) ទៅកាន់ Telegram រួចរាល់!</b>"
    elif cmd in ("/backup", "/bk", "/snapshot"):
        today_date = datetime.now().strftime("%Y-%m-%d")
        time_str = datetime.now().strftime("%I:%M %p")
        fn = f"FinSync_Backup_Manual_{today_date}_{int(time.time())}.json"
        bk_payload = {
            "version": "2.1",
            "exportedAt": datetime.now().isoformat(),
            "date": today_date,
            "time": time_str,
            "user": FIREBASE_USER_DOC,
            "exchangeRate": rate,
            "monthlyBudget": float(user_data.get("monthlyBudget", 300) or 300),
            "transactions": txs,
            "debts": debts,
            "savingsGoals": user_data.get("savingsGoals", []),
            "recurringBills": user_data.get("recurringBills", []),
            "tasks": user_data.get("tasks", [])
        }
        cap_bk = (
            f"""💾 <b>ឯកសារ Backup ទិន្នន័យផ្លូវការ FinSync Pro (.json)</b>\n"""
            f"""📅 កាលបរិច្ឆេទ: <b>{today_date} ({time_str})</b>\n"""
            f"""📝 ចំនួនប្រតិបត្តិការ: <b>{len(txs)} កំណត់ត្រា</b>\n"""
            f"""🤝 បំណុល: <b>{len(debts)}</b> | 📋 កិច្ចការ: <b>{len(user_data.get('tasks', []))}</b>\n"""
            f"""💎 <b>ប្រព័ន្ធ: Backup ដោយដៃតាម Telegram (24/7 Cloud)</b>\n"""
            f"""💡 <i>(ដើម្បី Restore ទិន្នន័យ គ្រាន់តែ Forward ឬផ្ញើ File .json នេះចូល Group វិញ!)</i>"""
        ).replace('\\n', '\n')
        tg_send_document(fn, json.dumps(bk_payload, ensure_ascii=False, indent=2).encode("utf-8"), caption=cap_bk, chat_id=TELEGRAM_CHAT_ID, thread_id=thread_id)
        reply = "💾 <b>បានបង្កើត និងផ្ញើឯកសារ Backup (.json) ទៅកាន់ Telegram រួចរាល់!</b>"
    elif cmd in ("/restore", "/rst"):
        reply = (
            """📥 <b>របៀប Restore ទិន្នន័យពី Telegram៖</b>\n\n"""
            """លោកអ្នកគ្រាន់តែផ្ញើ ឬ Forward ឯកសារ <code>FinSync_Backup_*.json</code> ចូលក្នុង Group នេះ ឬ Reply លើ File Backup ដោយវាយ <code>/restore</code> នោះប្រព័ន្ធនឹងស្តារទិន្នន័យទាំងអស់ចូល Firebase Cloud & FinSync Pro ស្វ័យប្រវត្តភ្លាមៗ!"""
        ).replace('\\n', '\n')
    elif cmd in ("/eod", "/close", "/closing"):
        today_txs = [t for t in txs if str(t.get("date", "")) == today_str]
        inc_today = sum(float(t.get("amountUSD", 0) or 0) for t in today_txs if t.get("type") == "income")
        exp_today = sum(float(t.get("amountUSD", 0) or 0) for t in today_txs if t.get("type") != "income")
        net_today = inc_today - exp_today
        pos_txs = [t for t in today_txs if t.get("tag") == "#BarcodePOS" or "POS" in str(t.get("note", ""))]
        
        bals = {"cash": 0.0, "aba": 0.0, "wing_acleda": 0.0}
        for t in txs:
            w = t.get("wallet", "cash")
            if w in bals:
                amt = float(t.get("amountUSD", 0) or 0)
                bals[w] += amt if t.get("type") == "income" else -amt
                
        reply = (
            f"""🌙 📊 <b>របាយការណ៍បិទបញ្ជីប្រចាំថ្ងៃ (EOD Closing Report — 21:00)</b>\n"""
            f"""📅 កាលបរិច្ឆេទ: <b>{today_str}</b>\n"""
            f"""━━━━━━━━━━━━━━━━━━━━\n"""
            f"""• 🟢 ចំណូលសរុបថ្ងៃនេះ: <b>+${inc_today:.2f}</b>\n"""
            f"""• 🔴 ចំណាយសរុបថ្ងៃនេះ: <b>-${exp_today:.2f}</b>\n"""
            f"""• 💎 <b>សល់សុទ្ធថ្ងៃនេះ: {'+' if net_today >= 0 else ''}${net_today:.2f} ({round(net_today*rate):,} ៛)</b>\n"""
            f"""━━━━━━━━━━━━━━━━━━━━\n"""
            f"""• 🏪 លក់ទំនិញ POS: <b>{len(pos_txs)} ប្រតិបត្តិការ</b>\n"""
            f"""• 💵 សាច់ប្រាក់ក្នុងថតតុ (Cash): <b>${bals['cash']:.2f}</b>\n"""
            f"""• 🏦 ធនាគារ ABA: <b>${bals['aba']:.2f}</b>\n"""
            f"""• 📲 ធនាគារ Wing / ACLEDA: <b>${bals['wing_acleda']:.2f}</b>\n"""
            f"""━━━━━━━━━━━━━━━━━━━━\n"""
            f"""✨ <b>ស្ថានភាព: បានបិទបញ្ជីជោគជ័យ! ប្រព័ន្ធដំណើរការ Cloud 24/7</b>"""
        ).replace('\\n', '\n')
    elif cmd in ("/advice", "/ai", "/forecast"):
        now_dt = datetime.now()
        last_30_txs = [t for t in txs if t.get("type") != "income"]
        exp_30 = sum(float(t.get("amountUSD", 0) or 0) for t in last_30_txs)
        daily_burn = (exp_30 / 30.0) if exp_30 > 0 else 10.0
        
        tot_liquid = sum((float(t.get("amountUSD", 0) or 0) if t.get("type") == "income" else -float(t.get("amountUSD", 0) or 0)) for t in txs)
        runway_days = int(tot_liquid / daily_burn) if (daily_burn > 0 and tot_liquid > 0) else 0
        health = "🟢 ល្អប្រសើរ (Healthy)" if runway_days > 60 else ("🟡 មធ្យម (Moderate)" if runway_days > 20 else "🔴 ប្រុងប្រយ័ត្ន (Warning)")
        
        reply = (
            f"""🧠 💡 <b>Gemini AI Financial Advisor Pro (ការវិភាគ & ព្យាករណ៍)</b>\n"""
            f"""• ពិន្ទុសុខភាពហិរញ្ញវត្ថុ: <b>{health}</b>\n"""
            f"""• ល្បឿនចំណាយមធ្យម: <b>~${daily_burn:.2f}/ថ្ងៃ</b>\n"""
            f"""• ថ្ងៃទប់ទល់សាច់ប្រាក់ (Runway): <b>{runway_days} ថ្ងៃ</b>\n"""
            f"""• ព្យាករណ៍ ៣០ ថ្ងៃបន្ទាប់: <b>~${max(0, tot_liquid - (daily_burn * 30)):.2f}</b>\n"""
            f"""━━━━━━━━━━━━━━━━━━━━\n"""
            f"""🎯 <b>អនុសាសន៍ឆ្លាតវៃ:</b>\n"""
            f"""1. បង្កើនការលក់ទំនិញ POS ណាដែលមាន Margin លើសពី 30%\n"""
            f"""2. កាត់បន្ថយចំណាយបន្ទាប់បន្សំ 15% អាចសន្សំបាន ~${(exp_30*0.15):.2f}/ខែ\n"""
            f"""3. តាមដានការសងបំណុលទាន់កាលកំណត់ដើម្បីរក្សាលំហូរសាច់ប្រាក់!"""
        ).replace('\\n', '\n')
    elif cmd in ("/khqr", "/qr"):
        reply = (
            f"""🇰🇭 💳 <b>Bakong KHQR Payment (ស្កេនទូទាត់ប្រាក់)</b>\n"""
            f"""• គណនីទទួល: <b>HIM SENGHORN</b> (<code>himsenghorn@aba</code>)\n"""
            f"""• ធនាគារ: <b>ABA Bank / Bakong Network</b>\n"""
            f"""• ទីក្រុង: <b>Phnom Penh, Cambodia</b>\n\n"""
            f"""📱 <i>លោកអ្នកអាចបង្កើត dynamic KHQR តាមចំនួនលុយជាក់លាក់បានក្នុង FinSync App ➔ POS Barcode!</i>"""
        ).replace('\\n', '\n')
    else:
        reply = "🤖 ពាក្យបញ្ជា៖ <code>/balance</code>, <code>/today</code>, <code>/month</code>, <code>/eod</code>, <code>/debt</code>, <code>/export</code>, <code>/backup</code>, <code>/advice</code>, <code>/khqr</code>, <code>/keyboard</code>"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": reply,
        "parse_mode": "HTML",
        "reply_markup": build_quick_reply_keyboard()
    }
    if thread_id:
        payload["message_thread_id"] = int(thread_id)
    tg_api("sendMessage", payload)
def main():
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    print("=== FinSync Pro 24/7 Telegram & Firebase Background Worker Started ===")
    print(f"-> Bot Token: {TELEGRAM_BOT_TOKEN[:15]}...")
    print(f"-> Authorized Group: {TELEGRAM_CHAT_ID} (Also accepts private DMs)")
    purge_conflicting_webhook()
    os.makedirs(r"d:\system\backups", exist_ok=True)
    last_offset = -25
    last_hb = 0
    last_sched_check = 0

    while True:
        try:
            now_ts = time.time()
            if now_ts - last_hb >= 12:
                patch_firebase_fields({"botWorkerLastHeartbeat": int(now_ts * 1000)})
                last_hb = now_ts

            # Automated Scheduled Reports (07:00 Morning Summary & 21:00 Evening Closeout)
            if now_ts - last_sched_check >= 55:
                last_sched_check = now_ts
                try:
                    ud_sched = get_firebase_userdata()
                    sched_cfg = ud_sched.get("scheduledReportsConfig") or {}
                    if sched_cfg.get("enabled", True):
                        now_dt = datetime.now()
                        today_key = now_dt.strftime("%Y-%m-%d")
                        cur_hm = now_dt.strftime("%H:%M")
                        m_time = str(sched_cfg.get("morningTime") or "07:00")
                        e_time = str(sched_cfg.get("eveningTime") or "21:00")
                        txs_s = ud_sched.get("transactions", []) or []
                        debts_s = ud_sched.get("debts", []) or []

                        if cur_hm == m_time and sched_cfg.get("lastMorningSent") != today_key:
                            bals = {"cash": 0.0, "aba": 0.0, "wing_acleda": 0.0}
                            for t in txs_s:
                                w = t.get("wallet", "cash")
                                if w not in bals:
                                    bals[w] = 0.0
                                amt_u = float(t.get("amountUSD", 0) or 0)
                                bals[w] += amt_u if t.get("type") == "income" else -amt_u
                            unpaid_lent = sum(float(d.get("amountUSD", 0) or 0) for d in debts_s if d.get("status") != "paid" and d.get("type") == "lent")
                            msg_m = (
                                f"🌅 <b>សួស្ដីពេលព្រឹក! របាយការណ៍សង្ខេបប្រចាំថ្ងៃ ({today_key})</b>\n"
                                f"• 💵 Cash: <b>${bals['cash']:.2f}</b>\n"
                                f"• 🏦 ABA: <b>${bals['aba']:.2f}</b>\n"
                                f"• 📲 Wing/ACLEDA: <b>${bals['wing_acleda']:.2f}</b>\n"
                                f"• 💎 សមតុល្យសរុប: <b>${sum(bals.values()):.2f}</b>\n"
                                f"• 🤝 បំណុលត្រូវទារសរុប: <b>${unpaid_lent:.2f}</b>"
                            )
                            tg_api("sendMessage", {"chat_id": TELEGRAM_CHAT_ID, "text": msg_m, "parse_mode": "HTML"})
                            sched_cfg["lastMorningSent"] = today_key
                            patch_firebase_fields({"scheduledReportsConfig": sched_cfg})
                            print(f"[SCHEDULER] Sent Morning Summary ({today_key})")

                        if cur_hm == e_time and sched_cfg.get("lastEveningSent") != today_key:
                            today_txs = [t for t in txs_s if str(t.get("date", "")).startswith(today_key)]
                            inc_d = sum(float(t.get("amountUSD", 0) or 0) for t in today_txs if t.get("type") == "income")
                            exp_d = sum(float(t.get("amountUSD", 0) or 0) for t in today_txs if t.get("type") == "expense")
                            msg_e = (
                                f"🌙 <b>របាយការណ៍បិទបញ្ជីយប់ស្វ័យប្រវត្តិ ({today_key})</b>\n"
                                f"• 🟢 ចំណូលថ្ងៃនេះ: <b>+${inc_d:.2f}</b>\n"
                                f"• 🔴 ចំណាយថ្ងៃនេះ: <b>-${exp_d:.2f}</b>\n"
                                f"• 💎 សល់សុទ្ធថ្ងៃនេះ: <b>${(inc_d - exp_d):.2f}</b>\n"
                                f"• 🧾 ចំនួនប្រតិបត្តិការ: <b>{len(today_txs)}</b>"
                            )
                            tg_api("sendMessage", {"chat_id": TELEGRAM_CHAT_ID, "text": msg_e, "parse_mode": "HTML"})
                            sched_cfg["lastEveningSent"] = today_key
                            patch_firebase_fields({"scheduledReportsConfig": sched_cfg})
                            print(f"[SCHEDULER] Sent Evening Closeout ({today_key})")

                        # Automated Midnight 00:00 (12:00 AM) Full Backup Snapshot
                        # Auto EOD 21:00 Closing Report
                            if cur_hm == "21:00" and sched_cfg.get("lastEodSent") != today_key:
                                try:
                                    today_txs_e = [t for t in txs_s if str(t.get("date", "")) == today_key]
                                    inc_e = sum(float(t.get("amountUSD", 0) or 0) for t in today_txs_e if t.get("type") == "income")
                                    exp_e = sum(float(t.get("amountUSD", 0) or 0) for t in today_txs_e if t.get("type") != "income")
                                    net_e = inc_e - exp_e
                                    pos_e = [t for t in today_txs_e if t.get("tag") == "#BarcodePOS" or "POS" in str(t.get("note", ""))]
                                    bals_e = {"cash": 0.0, "aba": 0.0, "wing_acleda": 0.0}
                                    for t in txs_s:
                                        w = t.get("wallet", "cash")
                                        if w in bals_e:
                                            bals_e[w] += float(t.get("amountUSD", 0) or 0) if t.get("type") == "income" else -float(t.get("amountUSD", 0) or 0)
                                    
                                    eod_card = (
                                        f"🌙 📊 <b>របាយការណ៍បិទបញ្ជីប្រចាំថ្ងៃស្វ័យប្រវត្តិ (EOD Auto-Closing — 21:00)</b>\n"
                                        f"📅 កាលបរិច្ឆេទ: <b>{today_key}</b>\n"
                                        f"━━━━━━━━━━━━━━━━━━━━\n"
                                        f"• 🟢 ចំណូលសរុបថ្ងៃនេះ: <b>+${inc_e:.2f}</b>\n"
                                        f"• 🔴 ចំណាយសរុបថ្ងៃនេះ: <b>-${exp_e:.2f}</b>\n"
                                        f"• 💎 <b>សល់សុទ្ធថ្ងៃនេះ: {'+' if net_e >= 0 else ''}${net_e:.2f} ({round(net_e*rate):,} ៛)</b>\n"
                                        f"━━━━━━━━━━━━━━━━━━━━\n"
                                        f"• 🏪 លក់ទំនិញ POS: <b>{len(pos_e)} ប្រតិបត្តិការ</b>\n"
                                        f"• 💵 សាច់ប្រាក់ថតតុ: <b>${bals_e['cash']:.2f}</b>\n"
                                        f"• 🏦 ABA Bank: <b>${bals_e['aba']:.2f}</b>\n"
                                        f"• 📲 Wing / ACLEDA: <b>${bals_e['wing_acleda']:.2f}</b>\n"
                                        f"━━━━━━━━━━━━━━━━━━━━\n"
                                        f"✨ <b>ស្ថានភាព: បានបិទបញ្ជីជោគជ័យ! ប្រព័ន្ធដំណើរការ Cloud 24/7</b>"
                                    )
                                    tg_api("sendMessage", {"chat_id": TELEGRAM_CHAT_ID, "text": eod_card, "parse_mode": "HTML"})
                                    sched_cfg["lastEodSent"] = today_key
                                    patch_firebase_fields({"scheduledReportsConfig": sched_cfg})
                                    print(f"[SCHEDULER] Sent 21:00 EOD Auto-Closing Report for {today_key}")
                                except Exception as eode:
                                    print(f"[EOD REPORT ERROR] {eode}")

                            if cur_hm == "00:00" and sched_cfg.get("lastMidnightBackupSent") != today_key:
                                try:
                                    bk_payload = {
                                        "version": "2.1",
                                        "exportedAt": now_dt.isoformat(),
                                        "date": today_key,
                                        "user": FIREBASE_USER_DOC,
                                        "exchangeRate": ud_sched.get("exchangeRate", 4100),
                                        "monthlyBudget": ud_sched.get("monthlyBudget", 300),
                                        "transactions": txs_s,
                                        "debts": debts_s,
                                        "savingsGoals": ud_sched.get("savingsGoals", []),
                                        "recurringBills": ud_sched.get("recurringBills", []),
                                        "tasks": ud_sched.get("tasks", [])
                                    }
                                    bk_path = f"d:\\system\\backups\\FinSync_AutoBackup_{today_key}.json"
                                    try:
                                        with open(bk_path, "w", encoding="utf-8") as bf:
                                            json.dump(bk_payload, bf, ensure_ascii=False, indent=2)
                                        print(f"[BACKUP] Saved local file: {bk_path}")
                                    except Exception as be:
                                        print(f"[BACKUP LOCAL SAVE ERROR] {be}")

                                    hist_backups = ud_sched.get("autoMidnightBackups", []) or []
                                    new_entry = {
                                        "id": f"bk_{today_key}",
                                        "date": today_key,
                                        "time": "00:00",
                                        "timestamp": now_dt.isoformat(),
                                        "label": f"🌙 Backup ស្វ័យប្រវត្តិម៉ោង ១២ យប់ ({today_key})",
                                        "txCount": len(txs_s),
                                        "debtCount": len(debts_s),
                                        "taskCount": len(ud_sched.get("tasks", []) or []),
                                        "payload": bk_payload
                                    }
                                    hist_backups = [b for b in hist_backups if b.get("date") != today_key]
                                    hist_backups.insert(0, new_entry)
                                    sched_cfg["lastMidnightBackupSent"] = today_key
                                    patch_firebase_fields({
                                        "scheduledReportsConfig": sched_cfg,
                                        "autoMidnightBackups": hist_backups[:30]
                                    })

                                    msg_b = (
                                        f"🌙 💾 <b>ប្រព័ន្ធបាន Backup ទិន្នន័យស្វ័យប្រវត្តិម៉ោង ១២ យប់ (00:00) រួចរាល់!</b>\n"
                                        f"• កាលបរិច្ឆេទ: <b>{today_key}</b>\n"
                                        f"• ប្រតិបត្តិការ: <b>{len(txs_s)} កំណត់ត្រា</b> | បំណុល: <b>{len(debts_s)}</b>\n"
                                        f"💎 <b>ស្ថានភាព: បានរក្សាទុកក្នុង Cloud & ផ្ញើឯកសារ Backup .json ជូនរួចរាល់!</b>\n"
                                        f"💡 <i>(លោកអ្នកអាចទាញយកទុក ឬផ្ញើ File នេះមកវិញដើម្បី Restore បានគ្រប់ពេល)</i>"
                                    )
                                    tg_send_document(
                                        f"FinSync_AutoBackup_{today_key}.json",
                                        json.dumps(bk_payload, ensure_ascii=False, indent=2).encode("utf-8"),
                                        caption=msg_b,
                                        chat_id=TELEGRAM_CHAT_ID
                                    )
                                    print(f"[SCHEDULER] Completed Midnight Backup ({today_key})")
                                except Exception as bke:
                                    print(f"[MIDNIGHT BACKUP ERROR] {bke}")
                except Exception as sched_err:
                    print(f"[SCHEDULER ERROR] {sched_err}")

            allowed = urllib.parse.quote(json.dumps(["message", "channel_post", "callback_query"]))
            url = (
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
                f"?offset={last_offset}&limit=25&timeout=15&allowed_updates={allowed}"
            )
            data = http_json(url, timeout=22)
            if not data.get("ok"):
                if data.get("error_code") == 409 or "webhook" in str(data.get("description", "")).lower():
                    print("[TG CONFLICT] Active external webhook detected (e.g. Campaign Mudra)! Auto-purging...")
                    purge_conflicting_webhook()
                time.sleep(2)
                continue

            results = data.get("result", [])
            if not results:
                continue

            user_data = get_firebase_userdata()
            txs = user_data.get("transactions", []) or []
            rate = float(user_data.get("exchangeRate", 4100) or 4100)
            txs_changed = False

            for item in results:
                last_offset = max(last_offset, item["update_id"] + 1)

                # 1. Handle Inline Button Clicks (24/7)
                if "callback_query" in item:
                    cb = item["callback_query"]
                    cb_data = str(cb.get("data", ""))
                    if ":" in cb_data:
                        action, entity_id = cb_data.split(":", 1)
                        msg_id = cb.get("message", {}).get("message_id")
                        tx_idx = next((i for i, t in enumerate(txs) if t.get("id") == entity_id), None)

                        if action == "del_tx":
                            tg_api("answerCallbackQuery", {"callback_query_id": cb["id"], "text": "🗑️ បានលុបចេញពី System & Telegram!"})
                            if tx_idx is not None:
                                txs.pop(tx_idx)
                                txs_changed = True
                            if msg_id:
                                tg_api("deleteMessage", {"chat_id": TELEGRAM_CHAT_ID, "message_id": int(msg_id)})
                        elif tx_idx is not None:
                            tx = txs[tx_idx]
                            if action == "flip_tx":
                                tx["type"] = "expense" if tx.get("type") == "income" else "income"
                                txs_changed = True
                                tg_api("answerCallbackQuery", {"callback_query_id": cb["id"], "text": f"✅ ប្ដូរទៅជា {tx['type']}"})
                            elif action == "wallet_tx":
                                order = ["cash", "aba", "wing_acleda"]
                                cur = tx.get("wallet", "cash")
                                tx["wallet"] = order[(order.index(cur) + 1) % len(order)] if cur in order else "cash"
                                txs_changed = True
                                tg_api("answerCallbackQuery", {"callback_query_id": cb["id"], "text": f"💳 ប្ដូរទៅ {wallet_label(tx['wallet'])}"})

                            if msg_id:
                                tg_api("editMessageText", {
                                    "chat_id": TELEGRAM_CHAT_ID,
                                    "message_id": int(msg_id),
                                    "text": format_tx_card(tx),
                                    "parse_mode": "HTML",
                                    "reply_markup": build_tx_inline_keyboard(tx["id"]),
                                })
                        else:
                            tg_api("answerCallbackQuery", {"callback_query_id": cb["id"], "text": "⚠️ រកមិនឃើញប្រតិបត្តិការទេ"})
                    continue

                # 2. Handle Messages
                msg = item.get("message") or item.get("channel_post")
                if not msg:
                    continue

                chat_obj = msg.get("chat", {})
                chat_id = str(chat_obj.get("id", ""))
                chat_type = chat_obj.get("type", "")
                is_authorized_chat = (chat_id == str(TELEGRAM_CHAT_ID)) or (chat_type == "private")

                from_obj = msg.get("from", {})
                from_id = str(from_obj.get("id", ""))
                from_name = from_obj.get("first_name", "") or from_obj.get("username", "")

                msg_text = (msg.get("text") or msg.get("caption") or "").strip()
                thread_id = msg.get("message_thread_id")

                print(f"[TG UPDATE] msg_id={msg.get('message_id')} chat={chat_id} from={from_name}({from_id}) text='{msg_text}'")

                if not is_authorized_chat:
                    print(f"  -> Ignored: Chat {chat_id} not authorized (Group: {TELEGRAM_CHAT_ID})")
                    continue
                if from_id == "8801188196":
                    continue

                target_chat_id = chat_id or TELEGRAM_CHAT_ID

                if re.search(r"/(balance|today|month|debt|help|start|keyboard|menu|k|export|statement|excel|backup|bk|snapshot|restore|rst|eod|close|closing|advice|ai|forecast|khqr|qr)\b", msg_text, re.I):
                    handle_slash_command(msg_text, user_data, thread_id)
                    continue

                # Handle Document upload (.json Backup Restore)
                doc_obj = msg.get("document") or (msg.get("reply_to_message", {}).get("document"))
                if doc_obj:
                    f_name = doc_obj.get("file_name", "")
                    f_id = doc_obj.get("file_id")
                    if f_name.lower().endswith(".json") or "backup" in f_name.lower() or "/restore" in msg_text.lower():
                        print(f"[RESTORE VIA TELEGRAM] Document received: {f_name} (id={f_id})")
                        f_info = tg_api("getFile", {"file_id": f_id})
                        if f_info.get("ok"):
                            f_path = f_info.get("result", {}).get("file_path")
                            dl_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{f_path}"
                            try:
                                req_dl = urllib.request.Request(dl_url)
                                with urllib.request.urlopen(req_dl, timeout=30) as dl_resp:
                                    raw_json = dl_resp.read().decode("utf-8")
                                bk_data = json.loads(raw_json)
                                res_txs = bk_data.get("transactions")
                                if isinstance(res_txs, list):
                                    patch_p = {
                                        "transactions": res_txs,
                                        "lastRestoredAt": datetime.now().isoformat()
                                    }
                                    if "debts" in bk_data and isinstance(bk_data["debts"], list):
                                        patch_p["debts"] = bk_data["debts"]
                                    if "tasks" in bk_data and isinstance(bk_data["tasks"], list):
                                        patch_p["tasks"] = bk_data["tasks"]
                                    if "savingsGoals" in bk_data:
                                        patch_p["savingsGoals"] = bk_data["savingsGoals"]
                                    if "recurringBills" in bk_data:
                                        patch_p["recurringBills"] = bk_data["recurringBills"]
                                    if "exchangeRate" in bk_data:
                                        patch_p["exchangeRate"] = float(bk_data["exchangeRate"])
                                    
                                    patch_firebase_fields(patch_p)
                                    txs = res_txs
                                    user_data["transactions"] = res_txs
                                    if "debts" in patch_p:
                                        debts = patch_p["debts"]
                                        user_data["debts"] = debts
                                    
                                    bk_dt = bk_data.get("date", "Unknown")
                                    ok_msg = (
                                        f"✅ <b>បាន Restore ទិន្នន័យពី Telegram ជោគជ័យ ១០០%!</b>\n"
                                        f"📁 ឯកសារ: <code>{f_name}</code> (កាលបរិច្ឆេទ: <b>{bk_dt}</b>)\n"
                                        f"• 📝 ប្រតិបត្តិការបានស្តារ: <b>{len(res_txs)} កំណត់ត្រា</b>\n"
                                        f"• 🤝 បំណុល: <b>{len(patch_p.get('debts', []))}</b> | 📋 កិច្ចការ: <b>{len(patch_p.get('tasks', []))}</b>\n"
                                        f"💎 <b>ទិន្នន័យត្រូវបាន Sync ចូល Firebase Cloud & FinSync Pro គ្រប់ឧបករណ៍រួចរាល់!</b>"
                                    )
                                    p_rep = {"chat_id": target_chat_id, "text": ok_msg, "parse_mode": "HTML"}
                                    if thread_id and chat_type != "private":
                                        p_rep["message_thread_id"] = int(thread_id)
                                    tg_api("sendMessage", p_rep)
                                    continue
                                else:
                                    p_rep = {"chat_id": target_chat_id, "text": "⚠️ ឯកសារ .json មិនមែនជាទម្រង់ Backup របស់ FinSync Pro ទេ (រកមិនឃើញ transactions)", "parse_mode": "HTML"}
                                    if thread_id and chat_type != "private":
                                        p_rep["message_thread_id"] = int(thread_id)
                                    tg_api("sendMessage", p_rep)
                                    continue
                            except Exception as ex:
                                print(f"[RESTORE ERROR] {ex}")
                                p_rep = {"chat_id": target_chat_id, "text": f"❌ បរាជ័យក្នុងការ Restore ពី Telegram៖ {ex}", "parse_mode": "HTML"}
                                if thread_id and chat_type != "private":
                                    p_rep["message_thread_id"] = int(thread_id)
                                tg_api("sendMessage", p_rep)
                                continue

                # Handle Voice Note / Audio messages
                has_voice = bool(msg.get("voice")) or bool(msg.get("audio"))
                if has_voice:
                    if msg_text:
                        parsed = parse_text_transaction(msg_text, msg.get("date"), rate)
                        if parsed:
                            parsed["tgMessageId"] = msg.get("message_id")
                            txs.insert(0, parsed)
                            txs_changed = True
                            send_p = {
                                "chat_id": target_chat_id,
                                "text": format_tx_card(parsed),
                                "parse_mode": "HTML",
                                "reply_markup": build_tx_inline_keyboard(parsed["id"]),
                            }
                            if thread_id and chat_type != "private":
                                send_p["message_thread_id"] = int(thread_id)
                            tg_api("sendMessage", send_p)
                    else:
                        v_obj = msg.get("voice") or msg.get("audio") or {}
                        file_id = v_obj.get("file_id", "")
                        pending_v = user_data.get("pendingTgVoices", []) or []
                        pending_v.append({
                            "file_id": file_id,
                            "message_id": msg.get("message_id"),
                            "message_thread_id": thread_id,
                            "date": msg.get("date"),
                            "duration": v_obj.get("duration", 0),
                            "sender": from_name,
                        })
                        patch_firebase_fields({"pendingTgVoices": pending_v[-20:]})
                        ack_v = {
                            "chat_id": target_chat_id,
                            "text": "🎙️ ✅ <b>Bot 24/7 បានទទួលសារសំឡេងទុកក្នុង Cloud រួចរាល់!</b>\n<i>(សូមបើក FinSync Pro ➔ Mega 10 Suite ➔ សារសំឡេង ដើម្បីស្ដាប់/កត់ត្រា ឬវាយអក្សរខ្លីភ្ជាប់សំឡេង)</i>",
                            "parse_mode": "HTML",
                        }
                        if thread_id and chat_type != "private":
                            ack_v["message_thread_id"] = int(thread_id)
                        tg_api("sendMessage", ack_v)
                        print(f"  -> [FS QUEUED VOICE NOTE] file_id={file_id}")
                    continue

                # If photo arrives while browser is closed: queue photo file_id for OCR or parse caption if provided
                has_photo = bool(msg.get("photo")) or (msg.get("document", {}).get("mime_type", "").startswith("image/"))
                if has_photo:
                    if msg_text:
                        parsed = parse_text_transaction(msg_text, msg.get("date"), rate)
                        if parsed:
                            parsed["tgMessageId"] = msg.get("message_id")
                            txs.insert(0, parsed)
                            txs_changed = True
                            send_p = {
                                "chat_id": target_chat_id,
                                "text": format_tx_card(parsed),
                                "parse_mode": "HTML",
                                "reply_markup": build_tx_inline_keyboard(parsed["id"]),
                            }
                            if thread_id and chat_type != "private":
                                send_p["message_thread_id"] = int(thread_id)
                            tg_api("sendMessage", send_p)
                            print(f"  -> [FS RECORDED PHOTO+TEXT] {parsed['note']} | {parsed['amountKHR']} KHR (${parsed['amountUSD']})")
                    else:
                        photos = msg.get("photo") or []
                        file_id = photos[-1]["file_id"] if photos else msg["document"]["file_id"]
                        pending = user_data.get("pendingTgPhotos", []) or []
                        pending.append({
                            "file_id": file_id,
                            "message_id": msg.get("message_id"),
                            "message_thread_id": thread_id,
                            "date": msg.get("date"),
                        })
                        patch_firebase_fields({"pendingTgPhotos": pending[-30:]})
                        ack_p = {
                            "chat_id": target_chat_id,
                            "text": "🖼️ ✅ <b>Bot 24/7 បានទទួលរូបវិក្កយបត្រទុកក្នុង Cloud រួចរាល់!</b>\n<i>(នឹងស្កេន OCR បញ្ចូលតួលេខស្វ័យប្រវត្តិពេលបើក System ឬវាយចំនួនទឹកប្រាក់ភ្ជាប់រូបដើម្បីកត់ភ្លាមៗ)</i>",
                            "parse_mode": "HTML",
                        }
                        if thread_id and chat_type != "private":
                            ack_p["message_thread_id"] = int(thread_id)
                        tg_api("sendMessage", ack_p)
                        print(f"  -> [FS QUEUED PHOTO OCR] file_id={file_id}")
                    continue

                # Text transaction (including Khmer digits e.g. បាយ ២០០០៛)
                if msg_text and not msg_text.startswith("/start"):
                    if any(int(t.get("tgMessageId") or 0) == int(msg.get("message_id", 0)) for t in txs):
                        continue
                    parsed = parse_text_transaction(msg_text, msg.get("date"), rate)
                    if parsed:
                        parsed["tgMessageId"] = msg.get("message_id")
                        txs.insert(0, parsed)
                        txs_changed = True
                        send_p = {
                            "chat_id": target_chat_id,
                            "text": format_tx_card(parsed),
                            "parse_mode": "HTML",
                            "reply_markup": build_tx_inline_keyboard(parsed["id"]),
                        }
                        if thread_id and chat_type != "private":
                            send_p["message_thread_id"] = int(thread_id)
                        res_send = tg_api("sendMessage", send_p)
                        print(f"  -> [FS RECORDED TX] {parsed['note']} | {parsed['amountKHR']} KHR (${parsed['amountUSD']}) -> Sent reply: {bool(res_send and res_send.get('ok'))}")

            if txs_changed:
                patch_firebase_fields({
                    "transactions": txs,
                    "updatedAt": datetime.now(timezone.utc).isoformat(),
                })

        except Exception as loop_err:
            print(f"[LOOP ERROR] {loop_err}")
            time.sleep(3)


if __name__ == "__main__":
    main()
