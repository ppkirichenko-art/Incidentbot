"""
Telegram-бот классификации инцидентов — Силовые Машины
Использует только встроенный urllib — никаких зависимостей!
Работает на Python 3.8+
"""

import os
import json
import time
import urllib.request
import urllib.parse

# ── Токен ─────────────────────────────────────────────────────────────────────
TOKEN = os.environ.get("BOT_TOKEN", "")
if not TOKEN:
    print("Переменная BOT_TOKEN не найдена. Введите токен:")
    TOKEN = input(">>> ").strip()

API = f"https://api.telegram.org/bot{TOKEN}"

# ── Состояния пользователей ────────────────────────────────────────────────────
user_state = {}   # chat_id -> {"step": ..., "data": {...}}

# ── Справочники ────────────────────────────────────────────────────────────────
CLIENT_TYPES = {
    "guarantee": "🔵 Гарантия / Вх. контроль / Монтаж / ПНР",
    "key":       "🟡 Ключевой клиент",
    "other":     "⚪ Прочие клиенты",
}
EQUIPMENT_TYPES = {
    "aux":     "🔩 Вспомогательное оборудование (без вскрытия)",
    "flow":    "⚙️ Проточная часть (с вскрытием)",
    "complex": "🏭 Комплекс",
}
SEVERITY_TYPES = {
    "question":    "💬 Эксплуатационный вопрос",
    "minor":       "🟡 Неисправность (без останова)",
    "major":       "🟠 Серьёзная потеря функциональности (без останова)",
    "stop":        "🔴 Останов / срыв сроков",
    "accident":    "‼️ Авария",
    "catastrophe": "🆘 Техногенная катастрофа / блэкаут",
}
SCENARIOS = {
    "K1": ("K1", "Удалённая консультация",              "3 рабочих дня",   "Руководитель подразделения → ЗГД", "💬"),
    "K2": ("K2", "Срочная удалённая консультация",      "1 рабочий день",  "Руководитель подразделения → ЗГД", "📞"),
    "K3": ("K3", "Консультация с привлечением КБ",      "3 рабочих дня",   "ЗГД по сбыту",                    "🔬"),
    "R1": ("Р1", "Командирование специалистов",         "5 рабочих дней",  "ЗГД по сбыту",                    "👨‍🔧"),
    "R2": ("Р2", "Поиск запчастей",                     "5 рабочих дней",  "ЗГД по сбыту",                    "🔍"),
    "R3": ("Р3", "Командирование ремонтной бригады",    "10 рабочих дней", "ЗГД по сбыту",                    "🛠️"),
    "R4": ("Р4", "Срочное изготовление / ремонт в цехах СМ", "5 рабочих дней", "ЗГД по сбыту",               "🏗️"),
    "R5": ("Р5", "Штаб с участием ГД",                 "⚡ Немедленно",    "ГД — формирование штаба",          "🚨"),
    "R6": ("Р6", "Штаб СМ на объекте эксплуатации",   "⚡ Немедленно",    "ГД — кризисный штаб на объекте",   "🆘"),
}
MATRIX = {
    ("guarantee","aux","question"):    (["K2"],False), ("guarantee","flow","question"):    (["K2"],False), ("guarantee","complex","question"):    (["K2"],False),
    ("guarantee","aux","minor"):       (["K3"],False), ("guarantee","flow","minor"):       (["K3"],False), ("guarantee","complex","minor"):       (["K3"],False),
    ("guarantee","aux","major"):       (["K3"],False), ("guarantee","flow","major"):       (["K3"],False), ("guarantee","complex","major"):       (["K3"],False),
    ("guarantee","aux","stop"):        (["K3","R1"],False), ("guarantee","flow","stop"):   (["R1","R2"],False), ("guarantee","complex","stop"):   (["R1","R2"],False),
    ("guarantee","aux","accident"):    (["R3"],False), ("guarantee","flow","accident"):    (["R3"],False), ("guarantee","complex","accident"):    (["R3","R4"],False),
    ("guarantee","aux","catastrophe"): (["R4","R5"],False), ("guarantee","flow","catastrophe"): (["R5","R6"],False), ("guarantee","complex","catastrophe"): (["R5","R6"],False),
    ("key","aux","question"):    (["K1"],False), ("key","flow","question"):    (["K1"],False), ("key","complex","question"):    (["K1"],False),
    ("key","aux","minor"):       (["K2"],False), ("key","flow","minor"):       (["K2"],False), ("key","complex","minor"):       (["K2"],False),
    ("key","aux","major"):       (["K2","R1"],True), ("key","flow","major"):   (["K2","R1"],True), ("key","complex","major"):   (["K2","R1"],True),
    ("key","aux","stop"):        (["K2"],False), ("key","flow","stop"):        (["K3","R1"],False), ("key","complex","stop"):   (["K3","R1"],False),
    ("key","aux","accident"):    (["R2"],False), ("key","flow","accident"):    (["R3"],True), ("key","complex","accident"):     (["R4","R5"],True),
    ("key","aux","catastrophe"): (["R4","R5"],True), ("key","flow","catastrophe"): (["R5","R6"],False), ("key","complex","catastrophe"): (["R5","R6"],False),
    ("other","aux","question"):    (["K1"],False), ("other","flow","question"):    (["K1"],False), ("other","complex","question"):    (["K1"],False),
    ("other","aux","minor"):       (["K1"],False), ("other","flow","minor"):       (["K1"],False), ("other","complex","minor"):       (["K1"],False),
    ("other","aux","major"):       (["K2"],True), ("other","flow","major"):        (["K2"],True), ("other","complex","major"):        (["K2"],True),
    ("other","aux","stop"):        (["K1"],False), ("other","flow","stop"):        (["K2"],True), ("other","complex","stop"):         (["K2"],True),
    ("other","aux","accident"):    (["K3"],True), ("other","flow","accident"):     (["R2"],False), ("other","complex","accident"):    (["R1","R2"],True),
    ("other","aux","catastrophe"): (["R3","R4"],True), ("other","flow","catastrophe"): (["R3","R4"],True), ("other","complex","catastrophe"): (["R4","R5","R6"],True),
}
POWER_UPGRADE = {"K3":"R1","R1":"R2","R2":"R3","R3":"R4","R4":"R5","R5":"R6"}

# ── HTTP-хелперы ───────────────────────────────────────────────────────────────
def api_call(method, **params):
    url = f"{API}/{method}"
    data = json.dumps(params).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"API error {method}: {e}")
        return {}

def send(chat_id, text, buttons=None):
    params = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if buttons:
        params["reply_markup"] = {"inline_keyboard": buttons}
    api_call("sendMessage", **params)

def edit(chat_id, msg_id, text, buttons=None):
    params = {"chat_id": chat_id, "message_id": msg_id, "text": text, "parse_mode": "Markdown"}
    if buttons:
        params["reply_markup"] = {"inline_keyboard": buttons}
    api_call("editMessageText", **params)

def answer_cb(cb_id):
    api_call("answerCallbackQuery", callback_query_id=cb_id)

def kb(options, prefix):
    return [[{"text": label, "callback_data": f"{prefix}:{key}"}] for key, label in options.items()]

# ── Логика бота ────────────────────────────────────────────────────────────────
def build_result(d):
    sc_list, paid = MATRIX.get((d["client"], d["equip"], d["sev"]), (["R5"], False))
    note = ""
    if d.get("casualties"):
        sc_list, paid, note = ["R5","R6"], False, "⚠️ *Пострадавшие — автоматически максимальный уровень*\n\n"
    elif d.get("high_power"):
        sc_list = list(dict.fromkeys(POWER_UPGRADE.get(s, s) for s in sc_list))
        note = "⚡ *Мощность >500 МВт — уровень повышен*\n\n"

    lines = [
        "📋 *РЕЗУЛЬТАТ КЛАССИФИКАЦИИ*",
        "─" * 30,
        f"👥 {CLIENT_TYPES[d['client']]}",
        f"🔧 {EQUIPMENT_TYPES[d['equip']]}",
        f"📊 {SEVERITY_TYPES[d['sev']]}",
        "─" * 30, "", note,
        f"🎯 *Сценари{'и' if len(sc_list)>1 else 'й'} реагирования:*\n",
    ]
    for sc in sc_list:
        code, name, deadline, esc, emoji = SCENARIOS[sc]
        lines += [f"{emoji} *{code} — {name}*", f"   ⏱ Срок: {deadline}", f"   📊 Эскалация: {esc}", ""]
    if paid:
        lines.append("💰 _Услуга оказывается на платной основе ($)_")
    lines += ["─" * 30, "_/start — новая классификация_"]
    return "\n".join(lines)

def step_client(chat_id, msg_id=None):
    text = "🤖 *Классификатор инцидентов СМ*\n\n*Шаг 1 / 3* — Тип клиента:"
    buttons = kb(CLIENT_TYPES, "cl")
    if msg_id:
        edit(chat_id, msg_id, text, buttons)
    else:
        send(chat_id, text, buttons)
    user_state[chat_id] = {"step": "client"}

def handle_start(chat_id):
    step_client(chat_id)

def handle_cb(chat_id, msg_id, cb_id, data):
    answer_cb(cb_id)
    st = user_state.get(chat_id, {})
    step = st.get("step")

    if data.startswith("cl:"):
        val = data[3:]
        user_state[chat_id] = {"step": "equip", "data": {"client": val}}
        edit(chat_id, msg_id,
             f"✅ {CLIENT_TYPES[val]}\n\n*Шаг 2 / 3* — Тип оборудования:",
             kb(EQUIPMENT_TYPES, "eq"))

    elif data.startswith("eq:") and step == "equip":
        val = data[3:]
        st["data"]["equip"] = val
        st["step"] = "sev"
        edit(chat_id, msg_id,
             f"✅ {EQUIPMENT_TYPES[val]}\n\n*Шаг 3 / 3* — Тяжесть инцидента:",
             kb(SEVERITY_TYPES, "sv"))

    elif data.startswith("sv:") and step == "sev":
        val = data[3:]
        st["data"]["sev"] = val
        if val in ("stop", "accident", "catastrophe"):
            st["step"] = "power"
            edit(chat_id, msg_id,
                 f"✅ {SEVERITY_TYPES[val]}\n\n⚡ *Уточнение* — Мощность блока >500 МВт (гидро >300 МВт)?",
                 [[{"text":"✅ Да, >500 МВт","callback_data":"pw:yes"},
                   {"text":"❌ Нет",         "callback_data":"pw:no"}]])
        elif val != "question":
            st["step"] = "casualties"
            edit(chat_id, msg_id,
                 f"✅ {SEVERITY_TYPES[val]}\n\n🚑 *Уточнение* — Есть пострадавшие или угроза жизни людей?",
                 [[{"text":"⚠️ Да, есть пострадавшие","callback_data":"cs:yes"},
                   {"text":"✅ Нет пострадавших",      "callback_data":"cs:no"}]])
        else:
            st["data"].update({"high_power": False, "casualties": False})
            edit(chat_id, msg_id, build_result(st["data"]))
            user_state.pop(chat_id, None)

    elif data.startswith("pw:") and step == "power":
        st["data"]["high_power"] = (data[3:] == "yes")
        st["step"] = "casualties"
        edit(chat_id, msg_id,
             "🚑 *Уточнение* — Есть пострадавшие или угроза жизни людей?",
             [[{"text":"⚠️ Да, есть пострадавшие","callback_data":"cs:yes"},
               {"text":"✅ Нет пострадавших",      "callback_data":"cs:no"}]])

    elif data.startswith("cs:") and step == "casualties":
        st["data"]["casualties"] = (data[3:] == "yes")
        edit(chat_id, msg_id, build_result(st["data"]))
        user_state.pop(chat_id, None)

# ── Polling ────────────────────────────────────────────────────────────────────
def main():
    print("🤖 Бот запущен. Ctrl+C для остановки.")
    offset = 0
    while True:
        try:
            resp = api_call("getUpdates", offset=offset, timeout=25, allowed_updates=["message","callback_query"])
            for upd in resp.get("result", []):
                offset = upd["update_id"] + 1
                if "message" in upd:
                    msg = upd["message"]
                    chat_id = msg["chat"]["id"]
                    text = msg.get("text", "")
                    if text in ("/start", "/help"):
                        handle_start(chat_id)
                elif "callback_query" in upd:
                    cb = upd["callback_query"]
                    chat_id = cb["message"]["chat"]["id"]
                    msg_id = cb["message"]["message_id"]
                    handle_cb(chat_id, msg_id, cb["id"], cb["data"])
        except KeyboardInterrupt:
            print("Остановлено.")
            break
        except Exception as e:
            print(f"Ошибка: {e}")
            time.sleep(3)

if __name__ == "__main__":
    main()
