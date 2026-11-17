import json
import re
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone

TELEGRAM_BOT_TOKEN = "8801188196:AAGZHlsM9t_bhNRLVXO8kzM1_Ik6kbBI-Eg"
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
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def tg_api(method_name, payload=None, timeout=25):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method_name}"
    try:
        return http_json(url, method="POST" if payload else "GET", payload=payload, timeout=timeout)
    except Exception as e:
        print(f"[TG ERROR] {method_name}: {e}")
        return {"ok": False}


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
    text = re.sub(r"^/add\s+", "", text, flags=re.I)
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


def handle_slash_command(cmd_text, user_data, thread_id=None):
    cmd = cmd_text.strip().lower().split()[0]
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
            "💰 <b>របាយការណ៍សមតុល្យគ្រប់កាបូប (24/7 Cloud)</b>\n"
            f"• 💵 Cash: <b>${bals['cash']:.2f}</b>\n"
            f"• 🏦 ABA: <b>${bals['aba']:.2f}</b>\n"
            f"• 📲 Wing/ACLEDA: <b>${bals['wing_acleda']:.2f}</b>\n"
            f"💎 <b>សរុបរួម: ${tot:.2f} ({round(tot*rate):,} ៛)</b>"
        )
    elif cmd == "/today":
        inc = sum(float(t.get("amountUSD", 0)) for t in txs if t.get("date") == today_str and t.get("type") == "income")
        exp = sum(float(t.get("amountUSD", 0)) for t in txs if t.get("date") == today_str and t.get("type") != "income")
        reply = (
            f"📅 <b>របាយការណ៍ថ្ងៃនេះ ({today_str})</b>\n"
            f"• 🟢 ចំណូល: <b>+${inc:.2f}</b>\n"
            f"• 🔴 ចំណាយ: <b>-${exp:.2f}</b>\n"
            f"• ✨ សល់សុទ្ធ: <b>${(inc - exp):.2f}</b>"
        )
    elif cmd == "/month":
        inc = sum(float(t.get("amountUSD", 0)) for t in txs if str(t.get("date", "")).startswith(month_prefix) and t.get("type") == "income")
        exp = sum(float(t.get("amountUSD", 0)) for t in txs if str(t.get("date", "")).startswith(month_prefix) and t.get("type") != "income")
        reply = (
            f"📊 <b>របាយការណ៍ប្រចាំខែ ({month_prefix})</b>\n"
            f"• 🟢 ចំណូលខែនេះ: <b>+${inc:.2f}</b>\n"
            f"• 🔴 ចំណាយខែនេះ: <b>-${exp:.2f}</b>\n"
            f"• 💎 សល់សុទ្ធ: <b>${(inc - exp):.2f}</b>"
        )
    elif cmd == "/debt":
        unpaid = [d for d in debts if d.get("status") != "paid"]
        lent = sum(float(d.get("amountUSD", 0)) for d in unpaid if d.get("type") == "lent")
        borr = sum(float(d.get("amountUSD", 0)) for d in unpaid if d.get("type") != "lent")
        reply = f"🤝 <b>បញ្ជីបំណុលមិនទាន់ទូទាត់</b>\n• 🟢 គេជំពាក់យើង: <b>${lent:.2f}</b>\n• 🔴 យើងជំពាក់គេ: <b>${borr:.2f}</b>"
    else:
        reply = "🤖 ពាក្យបញ្ជា៖ <code>/balance</code>, <code>/today</code>, <code>/month</code>, <code>/debt</code>"

    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": reply, "parse_mode": "HTML"}
    if thread_id:
        payload["message_thread_id"] = int(thread_id)
    tg_api("sendMessage", payload)


def main():
    print("=== FinSync Pro 24/7 Telegram & Firebase Background Worker Started ===")
    last_offset = 0
    last_hb = 0

    while True:
        try:
            now_ts = time.time()
            if now_ts - last_hb >= 12:
                patch_firebase_fields({"botWorkerLastHeartbeat": int(now_ts * 1000)})
                last_hb = now_ts

            allowed = urllib.parse.quote(json.dumps(["message", "channel_post", "callback_query"]))
            url = (
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
                f"?offset={last_offset}&limit=25&timeout=15&allowed_updates={allowed}"
            )
            data = http_json(url, timeout=22)
            if not data.get("ok"):
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
                if str(msg.get("chat", {}).get("id", "")) != str(TELEGRAM_CHAT_ID):
                    continue
                if msg.get("from") and str(msg["from"].get("id", "")) == "8801188196":
                    continue

                thread_id = msg.get("message_thread_id")
                msg_text = (msg.get("text") or msg.get("caption") or "").strip()

                if re.match(r"^/(balance|today|month|debt|help)\b", msg_text, re.I):
                    handle_slash_command(msg_text, user_data, thread_id)
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
                                "chat_id": TELEGRAM_CHAT_ID,
                                "text": format_tx_card(parsed),
                                "parse_mode": "HTML",
                                "reply_markup": build_tx_inline_keyboard(parsed["id"]),
                            }
                            if thread_id:
                                send_p["message_thread_id"] = int(thread_id)
                            tg_api("sendMessage", send_p)
                    else:
                        # Queue photo in Firebase so index.html scans OCR immediately when opened
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
                            "chat_id": TELEGRAM_CHAT_ID,
                            "text": "🖼️ ✅ <b>Bot 24/7 បានទទួលរូបវិក្កយបត្រទុកក្នុង Cloud រួចរាល់!</b>\n<i>(នឹងស្កេន OCR បញ្ចូលតួលេខស្វ័យប្រវត្តិពេលបើក System ឬវាយចំនួនទឹកប្រាក់ភ្ជាប់រូបដើម្បីកត់ភ្លាមៗ)</i>",
                            "parse_mode": "HTML",
                        }
                        if thread_id:
                            ack_p["message_thread_id"] = int(thread_id)
                        tg_api("sendMessage", ack_p)
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
                            "chat_id": TELEGRAM_CHAT_ID,
                            "text": format_tx_card(parsed),
                            "parse_mode": "HTML",
                            "reply_markup": build_tx_inline_keyboard(parsed["id"]),
                        }
                        if thread_id:
                            send_p["message_thread_id"] = int(thread_id)
                        tg_api("sendMessage", send_p)

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
