/**
 * FinSync Pro — 24/7 Cloud Telegram Webhook Worker (Cloudflare Workers Free Tier)
 * Runs 100% in the Cloud even when your PC & browser are completely turned off!
 *
 * Setup:
 * 1. Go to https://dash.cloudflare.com -> Workers & Pages -> Create Worker
 * 2. Paste this entire file and click "Deploy"
 * 3. Copy your Worker URL (e.g., https://finsync-tg-bot.yourname.workers.dev)
 * 4. Open FinSync Pro -> Mega 10 Super-Suite -> Cloud Webhook -> Paste URL -> Click "Set Webhook"
 */

const TELEGRAM_BOT_TOKEN = "8801188196:AAEaoqqmzMeRuIAWr5bpICHBVNaQ9YLjmwE";
const TELEGRAM_CHAT_ID = "-1003527836779";
const FIREBASE_PROJECT_ID = "himsenghorn";
const FIREBASE_API_KEY = "AIzaSyDgjmb6s-dvTrN0aQXBWWX4ThAvhIF1EAM";
const FIREBASE_USER_DOC = "himsenghorn";

const FIRESTORE_DOC_URL = `https://firestore.googleapis.com/v1/projects/${FIREBASE_PROJECT_ID}/databases/(default)/documents/userData/${FIREBASE_USER_DOC}?key=${FIREBASE_API_KEY}`;

function convertKhmerDigits(text) {
  const kh = "០១២៣៤៥៦៧៨៩";
  return String(text || "").replace(/[០-៩]/g, (ch) => String(kh.indexOf(ch)));
}

function fsToJs(val) {
  if (!val || typeof val !== "object") return val;
  if ("stringValue" in val) return val.stringValue;
  if ("integerValue" in val) return parseInt(val.integerValue, 10);
  if ("doubleValue" in val) return parseFloat(val.doubleValue);
  if ("booleanValue" in val) return Boolean(val.booleanValue);
  if ("nullValue" in val) return null;
  if ("arrayValue" in val) return (val.arrayValue.values || []).map(fsToJs);
  if ("mapValue" in val) {
    const out = {};
    const fields = val.mapValue.fields || {};
    for (const k of Object.keys(fields)) out[k] = fsToJs(fields[k]);
    return out;
  }
  return val;
}

function jsToFs(val) {
  if (val === null || val === undefined) return { nullValue: null };
  if (typeof val === "boolean") return { booleanValue: val };
  if (typeof val === "number") {
    return Number.isInteger(val) ? { integerValue: String(val) } : { doubleValue: val };
  }
  if (typeof val === "string") return { stringValue: val };
  if (Array.isArray(val)) return { arrayValue: { values: val.map(jsToFs) } };
  if (typeof val === "object") {
    const fields = {};
    for (const k of Object.keys(val)) {
      if (val[k] !== undefined) fields[String(k)] = jsToFs(val[k]);
    }
    return { mapValue: { fields } };
  }
  return { stringValue: String(val) };
}

async function getFirebaseUserData() {
  const res = await fetch(FIRESTORE_DOC_URL);
  if (!res.ok) return {};
  const doc = await res.json();
  const out = {};
  const fields = doc.fields || {};
  for (const k of Object.keys(fields)) out[k] = fsToJs(fields[k]);
  return out;
}

async function patchFirebaseFields(updates) {
  const keys = Object.keys(updates);
  if (!keys.length) return false;
  const mask = keys.map((k) => `updateMask.fieldPaths=${encodeURIComponent(k)}`).join("&");
  const fields = {};
  for (const k of keys) fields[k] = jsToFs(updates[k]);
  const res = await fetch(`${FIRESTORE_DOC_URL}&${mask}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fields }),
  });
  return res.ok;
}

async function tgApi(method, payload) {
  const res = await fetch(`https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/${method}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}

function walletLabel(w) {
  return { cash: "សាច់ប្រាក់សុទ្ធ (Cash)", aba: "ABA Bank", wing_acleda: "Wing / ACLEDA" }[w] || w || "Cash";
}

function parseTextTransaction(rawText, msgUnixDate, exchangeRate = 4100) {
  let cleaned = String(rawText || "").trim();
  cleaned = cleaned.replace(/@[A-Za-z0-9_]+/g, " ").replace(/\b[A-Za-z0-9_]*bot\b/gi, " ").replace(/^\/add\s+/i, " ");
  const text = convertKhmerDigits(cleaned).replace(/\s+/g, " ").trim();
  if (!text || /^(💰|🔔|✅|🍕|🤝|📌|📊|✏️|🐷|🏦 ✅|🚨|🤖)/.test(text) || text.includes("FinSync Pro")) {
    return null;
  }

  let wallet = "cash";
  let badge = "";
  if (/\b(aba|aba\s*pay|bakong)\b|អេប៊ីអេ|បាគង/i.test(text)) {
    wallet = "aba";
    badge = "🏦 ABA";
  } else if (/\b(acleda|toanchet|wing|truemoney)\b|អេស៊ីលីដា|វីង/i.test(text)) {
    wallet = "wing_acleda";
    badge = /wing|វីង/i.test(text) ? "📲 Wing" : "🏦 ACLEDA";
  }

  const isInc = /(\b(received|credited|incoming|deposit|salary|income)\b|ទទួលបាន|បានទទួល|ចូលគណនី|ផ្ទេរចូល|ចំណូល|ប្រាក់ខែ|បើកប្រាក់|^\+)/i.test(text);
  const isExp = /(\b(paid|transferred|debited|sent to|withdrawal|payment)\b|បង់ប្រាក់|បានបង់|ផ្ទេរប្រាក់|ដកប្រាក់|កាត់ប្រាក់|ចំណាយ|ទិញ|^-)/i.test(text);
  const txType = isInc && !isExp ? "income" : "expense";

  const clean = text
    .replace(/\(\s*\d[\d\s\-]{5,}\s*\)/g, " ")
    .replace(/\b\d{1,2}[/\-]\d{1,2}(?:[/\-]\d{2,4})?\b/g, " ")
    .replace(/\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?\b/gi, " ");

  const usdM = clean.match(/(?:USD|US\$|\$)\s*([\d,]+(?:\.\d{1,2})?)|([\d,]+(?:\.\d{1,2})?)\s*(?:USD|US\$|\$|ដុល្លារ)/i);
  const khrM = clean.match(/(?:KHR|៛)\s*([\d,]+(?:\.\d+)?)|([\d,]+(?:\.\d+)?)\s*(?:KHR|៛|រៀល)/i);
  const kM = clean.match(/\b(\d+(?:\.\d+)?)\s*(?:k|ពាន់)\b/i);

  let amountVal = 0;
  let isKhr = false;
  if (usdM) {
    amountVal = parseFloat((usdM[1] || usdM[2]).replace(/,/g, ""));
  } else if (khrM) {
    amountVal = parseFloat((khrM[1] || khrM[2]).replace(/,/g, ""));
    isKhr = true;
  } else if (kM) {
    amountVal = parseFloat(kM[1]) * 1000;
    isKhr = true;
  } else {
    const genM = clean.match(/([\d,]+(?:\.\d+)?)/);
    if (!genM) return null;
    amountVal = parseFloat(genM[1].replace(/,/g, ""));
    isKhr = amountVal >= 100;
  }
  if (!amountVal || amountVal <= 0) return null;

  const amountUSD = isKhr ? Number((amountVal / exchangeRate).toFixed(2)) : Number(amountVal.toFixed(2));
  const amountKHR = isKhr ? Math.round(amountVal) : Math.round(amountVal * exchangeRate);
  const noteClean = clean
    .replace(/(?:USD|US\$|\$|KHR|៛|រៀល|ដុល្លារ)\s*[\d,]+(?:\.\d+)?|[\d,]+(?:\.\d+)?\s*(?:USD|US\$|\$|KHR|៛|រៀល|ដុល្លារ|k|ពាន់)?/gi, "")
    .replace(/\s+/g, " ")
    .trim() || (txType === "income" ? "ចំណូលតាម Telegram" : "ចំណាយតាម Telegram");

  // Cambodia UTC+7
  const dt = new Date((msgUnixDate ? msgUnixDate * 1000 : Date.now()) + 7 * 3600 * 1000);
  const dateStr = dt.toISOString().slice(0, 10);
  const hh = dt.getUTCHours();
  const mm = String(dt.getUTCMinutes()).padStart(2, "0");
  const ampm = hh >= 12 ? "PM" : "AM";
  const h12 = String(hh % 12 || 12).padStart(2, "0");

  return {
    id: `tx_cloud_${Date.now()}`,
    type: txType,
    amountUSD,
    amountKHR,
    inputCurrency: isKhr ? "KHR" : "USD",
    originalAmount: isKhr ? amountKHR : amountUSD,
    currency: isKhr ? "KHR" : "USD",
    category: txType === "income" ? "other_income" : "food",
    wallet,
    tag: "#Cloud247",
    note: badge ? `[${badge}] ${noteClean}` : `${noteClean} (Cloud Bot)`,
    date: dateStr,
    txTime: `${h12}:${mm} ${ampm}`,
    createdAt: new Date().toISOString(),
  };
}

function buildTxKeyboard(id) {
  return {
    inline_keyboard: [
      [
        { text: "🔄 ប្ដូរ ចំណូល/ចំណាយ", callback_data: `flip_tx:${id}` },
        { text: "💳 ប្ដូរកាបូប", callback_data: `wallet_tx:${id}` },
      ],
      [{ text: "🗑️ លុបចេញពី System & TG", callback_data: `del_tx:${id}` }],
    ],
  };
}

function formatTxCard(tx) {
  const amt =
    tx.currency === "KHR"
      ? `${Number(tx.amountKHR).toLocaleString()} ៛ ($${Number(tx.amountUSD).toFixed(2)})`
      : `$${Number(tx.amountUSD).toFixed(2)} (${Number(tx.amountKHR).toLocaleString()} ៛)`;
  return (
    `☁️ ✅ <b>បានកត់ត្រាចូល FinSync Pro (Cloud 24/7) រួចរាល់!</b>\n` +
    `• ប្រភេទ: <b>${tx.type === "income" ? "🟢 ចំណូល (Income)" : "🔴 ចំណាយ (Expense)"}</b>\n` +
    `• ចំនួន: <b>${amt}</b>\n` +
    `• កាបូប: <b>${walletLabel(tx.wallet)}</b>\n` +
    `• កាលបរិច្ឆេទ: <b>${tx.date} (${tx.txTime || ""})</b>\n` +
    `• បរិយាយ: <b>${tx.note}</b>`
  );
}

export default {
  async fetch(request) {
    if (request.method === "GET") {
      return new Response(JSON.stringify({ ok: true, service: "FinSync Pro 24/7 Cloud Webhook", status: "active" }), {
        headers: { "Content-Type": "application/json" },
      });
    }
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    try {
      const update = await request.json();
      const userData = await getFirebaseUserData();
      const txs = Array.isArray(userData.transactions) ? userData.transactions : [];
      const rate = parseFloat(userData.exchangeRate || 4100) || 4100;

      // 1. Handle Inline Button Callbacks
      if (update.callback_query) {
        const cb = update.callback_query;
        const [action, entityId] = String(cb.data || "").split(":");
        const msgId = cb.message?.message_id;
        const chatId = cb.message?.chat?.id || TELEGRAM_CHAT_ID;
        const idx = txs.findIndex((t) => t.id === entityId);

        if (action === "del_tx") {
          await tgApi("answerCallbackQuery", { callback_query_id: cb.id, text: "🗑️ បានលុបចេញពី System & TG!" });
          if (idx !== -1) {
            txs.splice(idx, 1);
            await patchFirebaseFields({ transactions: txs, updatedAt: new Date().toISOString() });
          }
          if (msgId) await tgApi("deleteMessage", { chat_id: chatId, message_id: msgId });
        } else if (idx !== -1) {
          const tx = txs[idx];
          if (action === "flip_tx") {
            tx.type = tx.type === "income" ? "expense" : "income";
            await tgApi("answerCallbackQuery", { callback_query_id: cb.id, text: `✅ ប្ដូរទៅជា ${tx.type}` });
          } else if (action === "wallet_tx") {
            const order = ["cash", "aba", "wing_acleda"];
            tx.wallet = order[(order.indexOf(tx.wallet) + 1) % order.length];
            await tgApi("answerCallbackQuery", { callback_query_id: cb.id, text: `✅ កាបូប៖ ${walletLabel(tx.wallet)}` });
          }
          await patchFirebaseFields({ transactions: txs, updatedAt: new Date().toISOString() });
          if (msgId) {
            await tgApi("editMessageText", {
              chat_id: chatId,
              message_id: msgId,
              text: formatTxCard(tx),
              parse_mode: "HTML",
              reply_markup: buildTxKeyboard(tx.id),
            });
          }
        }
        return new Response("OK");
      }

      // 2. Handle Incoming Messages
      const msg = update.message || update.channel_post;
      if (!msg) return new Response("OK");
      const chatId = String(msg.chat?.id || "");
      const chatType = msg.chat?.type || "";
      if (chatId !== TELEGRAM_CHAT_ID && chatType !== "private") return new Response("OK");
      if (String(msg.from?.id || "") === "8801188196") return new Response("OK");

      const threadId = chatType === "private" ? undefined : msg.message_thread_id;
      const text = (msg.text || msg.caption || "").trim();

      // Slash Commands
      if (/^\/(balance|today|month)\b/i.test(text)) {
        const cmd = text.toLowerCase().split(/\s+/)[0];
        let reply = "";
        if (cmd === "/balance") {
          const bals = { cash: 0, aba: 0, wing_acleda: 0 };
          for (const t of txs) {
            const w = bals[t.wallet] !== undefined ? t.wallet : "cash";
            bals[w] += t.type === "income" ? Number(t.amountUSD || 0) : -Number(t.amountUSD || 0);
          }
          const tot = bals.cash + bals.aba + bals.wing_acleda;
          reply = `💰 <b>សមតុល្យសរុប (Cloud 24/7)</b>\n• 💵 Cash: <b>$${bals.cash.toFixed(2)}</b>\n• 🏦 ABA: <b>$${bals.aba.toFixed(2)}</b>\n• 📲 Wing/ACLEDA: <b>$${bals.wing_acleda.toFixed(2)}</b>\n━━━━━━━━━━\n💎 សរុប: <b>$${tot.toFixed(2)}</b>`;
        } else {
          const today = new Date(Date.now() + 7 * 3600 * 1000).toISOString().slice(0, 10);
          const prefix = cmd === "/month" ? today.slice(0, 7) : today;
          const filtered = txs.filter((t) => String(t.date || "").startsWith(prefix));
          const inc = filtered.filter((t) => t.type === "income").reduce((s, t) => s + Number(t.amountUSD || 0), 0);
          const exp = filtered.filter((t) => t.type === "expense").reduce((s, t) => s + Number(t.amountUSD || 0), 0);
          reply = `📊 <b>របាយការណ៍ (${prefix})</b>\n• 🟢 ចំណូល: <b>+$${inc.toFixed(2)}</b>\n• 🔴 ចំណាយ: <b>-$${exp.toFixed(2)}</b>\n• 💎 សល់: <b>$${(inc - exp).toFixed(2)}</b>`;
        }
        const p = { chat_id: chatId, text: reply, parse_mode: "HTML" };
        if (threadId) p.message_thread_id = threadId;
        await tgApi("sendMessage", p);
        return new Response("OK");
      }

      // Voice Note Handling
      if (msg.voice || msg.audio) {
        const fileId = (msg.voice || msg.audio).file_id;
        const pendingVoices = Array.isArray(userData.pendingTgVoices) ? userData.pendingTgVoices : [];
        pendingVoices.push({ file_id: fileId, message_id: msg.message_id, date: msg.date, duration: (msg.voice || msg.audio).duration || 0 });
        await patchFirebaseFields({ pendingTgVoices: pendingVoices.slice(-20) });
        const p = {
          chat_id: chatId,
          text: "🎙️ ✅ <b>Cloud 24/7 បានទទួលសារសំឡេងរួចរាល់!</b>\n<i>(សូមបើក FinSync Pro ➔ Mega 10 Suite ➔ សារសំឡេង ដើម្បីស្ដាប់ និងកត់ត្រា ឬវាយអក្សរខ្លីភ្ជាប់សំឡេង)</i>",
          parse_mode: "HTML",
        };
        if (threadId) p.message_thread_id = threadId;
        await tgApi("sendMessage", p);
        return new Response("OK");
      }

      // Photo Queuing
      if (msg.photo && !text) {
        const fileId = msg.photo[msg.photo.length - 1].file_id;
        const pendingPhotos = Array.isArray(userData.pendingTgPhotos) ? userData.pendingTgPhotos : [];
        pendingPhotos.push({ file_id: fileId, message_id: msg.message_id, message_thread_id: threadId || null, date: msg.date });
        await patchFirebaseFields({ pendingTgPhotos: pendingPhotos.slice(-30) });
        const p = {
          chat_id: chatId,
          text: "🖼️ ✅ <b>Cloud 24/7 បានរក្សាទុករូបវិក្កយបត្រក្នុង Firebase រួចរាល់!</b>\n<i>(នឹងស្កេន OCR បញ្ចូលតួលេខស្វ័យប្រវត្តិពេលបើក System)</i>",
          parse_mode: "HTML",
        };
        if (threadId) p.message_thread_id = threadId;
        await tgApi("sendMessage", p);
        return new Response("OK");
      }

      // Text Transaction
      if (text && !text.startsWith("/start")) {
        const parsed = parseTextTransaction(text, msg.date, rate);
        if (parsed) {
          parsed.tgMessageId = msg.message_id;
          txs.unshift(parsed);
          await patchFirebaseFields({ transactions: txs, updatedAt: new Date().toISOString() });
          const p = {
            chat_id: chatId,
            text: formatTxCard(parsed),
            parse_mode: "HTML",
            reply_markup: buildTxKeyboard(parsed.id),
          };
          if (threadId) p.message_thread_id = threadId;
          await tgApi("sendMessage", p);
        }
      }

      return new Response("OK");
    } catch (err) {
      return new Response(`Error: ${err.message}`, { status: 200 });
    }
  },
};
