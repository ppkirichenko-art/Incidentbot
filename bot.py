
"""
Telegram-бот классификации инцидентов — Силовые Машины
v3.0 — Полная логика по Decision Table (Приложение 1) + ТЗ
Без внешних зависимостей, только stdlib Python 3.8+
"""

import os, json, time, urllib.request, urllib.error

TOKEN = os.environ.get("BOT_TOKEN", "")
if not TOKEN:
    raise SystemExit("❌ Переменная BOT_TOKEN не задана. Добавьте её в Railway → Variables.")

API = f"https://api.telegram.org/bot{TOKEN}"

# ═══════════════════════════════════════════════════════════════════
# СПРАВОЧНИКИ СЦЕНАРИЕВ
# ═══════════════════════════════════════════════════════════════════

SCENARIOS = {
    "K1": {
        "code": "K1", "emoji": "💬",
        "name": "Удалённая консультация",
        "deadline": "3 рабочих дня",
        "escalation": "ГД-2",
        "dept": "Управление исполнения: консультация",
    },
    "K2": {
        "code": "K2", "emoji": "📞",
        "name": "Срочная удалённая консультация",
        "deadline": "1 рабочий день",
        "escalation": "ГД-2 + Управление исполнения",
        "dept": "Упр.исполнения: И | КБ: Кон | Шеф-инженеры: Кон",
    },
    "K3": {
        "code": "K3", "emoji": "🔬",
        "name": "Консультация с привлечением КБ",
        "deadline": "3 рабочих дня",
        "escalation": "ГД-2 + Управление исполнения",
        "dept": "Упр.исполнения: И | КБ: Кон/С | Качество: Р",
    },
    "R1": {
        "code": "Р1", "emoji": "👨‍🔧",
        "name": "Командирование специалистов",
        "deadline": "5 рабочих дней",
        "escalation": "ГД-2 + ГД-1 + Управление исполнения",
        "dept": "Упр.исполнения: С | КБ: Ком/С | Шеф-инженеры: Ком | ДЮВ: И",
    },
    "R2": {
        "code": "Р2", "emoji": "🔍",
        "name": "Поиск и поставка ЗИП",
        "deadline": "5 рабочих дней",
        "escalation": "ГД-1 + Управление исполнения",
        "dept": "Упр.исполнения: С | КБ: Кон/С | Качество: Р | ДЮВ: И",
    },
    "R3": {
        "code": "Р3", "emoji": "🛠️",
        "name": "Командирование ремонтной бригады",
        "deadline": "10 рабочих дней",
        "escalation": "ГД-2 + ГД-1 + Управление исполнения",
        "dept": "Упр.исполнения: С | КБ: Ком/С | Производство: Ком | ДЮВ: И",
    },
    "R4": {
        "code": "Р4", "emoji": "🏗️",
        "name": "Срочное изготовление / ремонт в цехах СМ",
        "deadline": "5 рабочих дней*",
        "escalation": "ГД-1 + Управление исполнения",
        "dept": "Упр.исполнения: С | Производство: Р | ДЮВ: И",
    },
    "R5": {
        "code": "Р5", "emoji": "🚨",
        "name": "Штаб с участием ГД",
        "deadline": "⚡ Немедленно",
        "escalation": "ГД — формирование штаба СМ",
        "dept": "Все подразделения | УКБК: обязательно | ДЮВ: И",
    },
    "R6": {
        "code": "Р6", "emoji": "🆘",
        "name": "Штаб СМ на объекте эксплуатации",
        "deadline": "⚡ Немедленно",
        "escalation": "ГД — кризисный штаб на объекте",
        "dept": "Все подразделения | GR + УКБК | ДЮВ: И",
    },
}

# ═══════════════════════════════════════════════════════════════════
# КЛАССИФИКАЦИЯ (Decision Table — Лист1 (3))
# ═══════════════════════════════════════════════════════════════════

def classify(d):
    """
    Входные данные (dict d):
      working    : bool  — оборудование работает?
      func_loss  : str   — "none"/"minor"/"major" (если working=True)
      stype      : str   — "stop"/"accident" (если working=False)
      scale      : str   — "aux"/"flow"/"complex"/"catastrophe" (если accident)
      gt14       : bool  — срок устранения > 14 дней (если stop)
      guarantee  : bool  — гарантийный случай?
      key_client : bool  — ключевой клиент?

    Возвращает: (список_кодов, платно, примечание)
    """
    guarantee  = d.get("guarantee", False)
    key_client = d.get("key_client", False)
    paid = False
    note = ""

    if d.get("working"):
        fl = d.get("func_loss", "none")
        if fl == "none":
            sc = ["K2"] if (guarantee or key_client) else ["K1"]
        elif fl == "minor":
            if guarantee:
                sc = ["K3"]
            elif key_client:
                sc = ["K2"]
            else:
                sc = ["K1"]
        else:  # major
            if guarantee:
                sc = ["K3"]
            elif key_client:
                sc, paid = ["K2", "R1"], True
            else:
                sc, paid = ["K2"], True

    else:  # not working
        stype = d.get("stype")
        gt14  = d.get("gt14", False)
        scale = d.get("scale", "aux")

        if stype == "stop":
            # Останов / срыв сроков
            if guarantee:
                sc = ["R1", "R2", "R3"] if gt14 else ["R1", "R2"]
            elif key_client:
                sc = ["K3", "R1"] if gt14 else ["K3"]
            else:
                sc, paid = (["K2", "K3"], True) if gt14 else (["K2"], True)

        else:  # accident
            if scale == "aux":
                # Вспомогательное: гарантия и ключевой → Р2; иначе → Р3
                sc = ["R2"] if (guarantee or key_client) else ["R3"]

            elif scale == "flow":
                # Проточная часть
                if guarantee:
                    sc, paid = ["R1", "R2"], True
                elif key_client:
                    sc, paid = ["R3"], True
                else:
                    sc = ["R3", "R4"]

            elif scale == "complex":
                # Комплекс
                if guarantee:
                    sc, paid = ["R3", "R4"], True
                elif key_client:
                    sc, paid = ["R4", "R5"], True
                else:
                    sc = ["R4", "R5", "R6"]

            else:  # catastrophe
                if guarantee:
                    sc = ["R5", "R6"]
                elif key_client:
                    sc, paid = ["R4", "R5", "R6"], True
                else:
                    sc, paid = ["R3", "R4", "R5", "R6"], True
                note = (
                    "🆘 *КАТАСТРОФА — НЕМЕДЛЕННЫЕ ДЕЙСТВИЯ:*\n"
                    "• Уведомить УКБК и GR\n"
                    "• Сформировать кризисный штаб\n"
                    "• Все комментарии — только через УКБК"
                )

    return sc, paid, note


# ═══════════════════════════════════════════════════════════════════
# API-ХЕЛПЕРЫ
# ═══════════════════════════════════════════════════════════════════

def api(method, **params):
    url  = f"{API}/{method}"
    body = json.dumps(params).encode()
    req  = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"[{method}] HTTP {e.code}: {e.read()[:200]}")
        return {}
    except Exception as e:
        print(f"[{method}] Error: {e}")
        return {}

def send(cid, text, buttons=None):
    p = {"chat_id": cid, "text": text, "parse_mode": "Markdown"}
    if buttons:
        p["reply_markup"] = {"inline_keyboard": buttons}
    return api("sendMessage", **p)

def edit(cid, mid, text, buttons=None):
    p = {"chat_id": cid, "message_id": mid, "text": text, "parse_mode": "Markdown"}
    if buttons:
        p["reply_markup"] = {"inline_keyboard": buttons}
    api("editMessageText", **p)

def answer_cb(cbid):
    api("answerCallbackQuery", callback_query_id=cbid)

def btn(label, data):
    return {"text": label, "callback_data": data}

def kb(*rows):
    """kb([("Да","y"),("Нет","n")], [("Другое","o")]) → inline keyboard"""
    return [[btn(lbl, dat) for lbl, dat in row] for row in rows]


# ═══════════════════════════════════════════════════════════════════
# СОСТОЯНИЯ ПОЛЬЗОВАТЕЛЕЙ
# ═══════════════════════════════════════════════════════════════════

states = {}  # cid -> {"step": str, "data": dict, ...}

# Поля для сбора текстовой информации об инциденте
INCIDENT_FIELDS = [
    ("customer",     "🏢 *Заказчик*\nВведите полное название организации-заказчика:"),
    ("station",      "🏭 *Станция / Объект*\nВведите название станции или объекта:"),
    ("equip_type",   "⚙️ *Тип оборудования*\nНапример: «Турбина ГТ-110М», «Генератор ТВФ-120»:"),
    ("equip_num",    "🔢 *Станционный номер*\nВведите станционный номер оборудования:"),
    ("description",  "📝 *Описание инцидента*\nЧто произошло? Когда? Видимые повреждения?\n_Опишите подробно:_"),
    ("contact",      "👤 *Контактные данные РП СМ*\nУкажите ФИО и номер телефона руководителя проекта:"),
]

LEAD_FIELDS = [
    ("customer",     "🏢 *Заказчик*\nВведите название организации:"),
    ("station",      "🏭 *Станция / Объект*\nВведите название объекта:"),
    ("equip_type",   "⚙️ *Тип оборудования*\nКакое оборудование осматривалось?"),
    ("description",  "📝 *Описание проблемы*\nЧто выявлено? При каких обстоятельствах?\n_Опишите подробно:_"),
    ("scope",        "📊 *Возможный объём работ*\nОпишите предварительный объём необходимых работ:"),
    ("contact",      "👤 *Контактные данные*\nФИО и телефон сотрудника, фиксирующего проблему:"),
]


# ═══════════════════════════════════════════════════════════════════
# ФОРМИРОВАНИЕ ИТОГОВОГО СООБЩЕНИЯ
# ═══════════════════════════════════════════════════════════════════

def scenario_card(code):
    s = SCENARIOS.get(code)
    if not s:
        return f"• {code}"
    return (
        f"{s['emoji']} *{s['code']} — {s['name']}*\n"
        f"   ⏱ Срок реакции: _{s['deadline']}_\n"
        f"   📊 Эскалация: {s['escalation']}\n"
        f"   🏢 Подразделения: _{s['dept']}_"
    )

def label_working(d):
    return "✅ Работает" if d.get("working") else "❌ Не работает"

def label_func_loss(d):
    return {"none": "Нет потери", "minor": "Незначительная", "major": "Существенная"}.get(d.get("func_loss", ""), "")

def label_stype(d):
    return {"stop": "Останов / срыв сроков", "accident": "Авария"}.get(d.get("stype", ""), "")

def label_scale(d):
    return {
        "aux": "Вспомогательное оборудование",
        "flow": "Проточная часть",
        "complex": "Комплекс",
        "catastrophe": "Катастрофа"
    }.get(d.get("scale", ""), "")

def build_incident_result(d):
    sc_list, paid, cat_note = classify(d)

    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "📋 *КАРТОЧКА ИНЦИДЕНТА*",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n",
    ]

    # Данные об инциденте
    if d.get("customer"):
        lines.append(f"🏢 *Заказчик:* {d['customer']}")
    if d.get("station"):
        lines.append(f"🏭 *Станция:* {d['station']}")
    if d.get("equip_type"):
        lines.append(f"⚙️ *Оборудование:* {d['equip_type']}")
    if d.get("equip_num"):
        lines.append(f"🔢 *Ст. номер:* {d['equip_num']}")
    if d.get("contact"):
        lines.append(f"👤 *РП СМ:* {d['contact']}")
    if d.get("description"):
        lines.append(f"\n📝 _{d['description']}_")
    lines.append("")

    # Классификация
    lines.append("*Классификация:*")
    lines.append(f"  {label_working(d)}")
    if d.get("working"):
        fl = label_func_loss(d)
        if fl:
            lines.append(f"  Потеря функциональности: {fl}")
    else:
        st = label_stype(d)
        sc = label_scale(d)
        if st:
            lines.append(f"  Тип: {st}")
        if sc:
            lines.append(f"  Масштаб: {sc}")
        if d.get("gt14"):
            lines.append("  Срок устранения: более 14 рабочих дней")
    lines.append(f"  Гарантия: {'✅ Да' if d.get('guarantee') else '❌ Нет'}")
    if not d.get("guarantee"):
        lines.append(f"  Ключевой клиент: {'⭐ Да' if d.get('key_client') else '➖ Нет'}")

    lines.append("")
    if cat_note:
        lines.append(f"{cat_note}\n")

    # Сценарии
    lines.append(f"🎯 *{'Сценарии' if len(sc_list) > 1 else 'Сценарий'} реагирования:*\n")
    for sc in sc_list:
        lines.append(scenario_card(sc))
        lines.append("")

    if paid:
        lines.append("💰 _Услуги оказываются на платной основе ($)_\n")

    n_files = len(d.get("files", []))
    if n_files:
        lines.append(f"📎 Прикреплено файлов: {n_files}")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("_Владелец инцидента: назначить немедленно_")
    lines.append("_/start — новое обращение_")

    return "\n".join(lines)

def build_lead_result(d):
    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "💡 *ТЕХНИЧЕСКАЯ ПРОБЛЕМА / ЛИД*",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n",
    ]
    if d.get("customer"):    lines.append(f"🏢 *Заказчик:* {d['customer']}")
    if d.get("station"):     lines.append(f"🏭 *Объект:* {d['station']}")
    if d.get("equip_type"):  lines.append(f"⚙️ *Оборудование:* {d['equip_type']}")
    if d.get("contact"):     lines.append(f"👤 *Контакт:* {d['contact']}")
    if d.get("description"): lines.append(f"\n📝 *Проблема:*\n_{d['description']}_")
    if d.get("scope"):       lines.append(f"\n📊 *Объём работ:*\n_{d['scope']}_")
    n_files = len(d.get("files", []))
    if n_files:              lines.append(f"\n📎 Прикреплено файлов: {n_files}")
    lines.append("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("_Передано в работу. /start — новое обращение_")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# ШАГИ ДИАЛОГА — ИНЦИДЕНТ
# ═══════════════════════════════════════════════════════════════════

def step_welcome(cid):
    states[cid] = {"step": "type", "data": {}}
    send(cid,
        "🤖 *Классификатор инцидентов — Силовые Машины*\n\n"
        "Я помогу зафиксировать обращение, классифицировать инцидент "
        "и определить сценарий реагирования.\n\n"
        "Выберите тип обращения:",
        kb(
            [("🚨 Инцидент", "type:incident")],
            [("💡 Техническая проблема / потенциальный лид", "type:lead")],
        )
    )

def step_working(cid, mid):
    edit(cid, mid,
        "📍 *Шаг 1 из 4* — Статус оборудования\n\n"
        "Оборудование сейчас работает?",
        kb(
            [("✅ Да, работает", "w:yes")],
            [("❌ Нет, не работает / останов", "w:no")],
        )
    )
    states[cid]["step"] = "working"

def step_func_loss(cid, mid):
    edit(cid, mid,
        "📍 *Шаг 2 из 4* — Потеря функциональности\n\n"
        "Есть ли влияние на работу оборудования?",
        kb(
            [("➖ Нет потери — вопрос/консультация", "fl:none")],
            [("🟡 Незначительная потеря", "fl:minor")],
            [("🔴 Существенная потеря функциональности", "fl:major")],
        )
    )
    states[cid]["step"] = "func_loss"

def step_stype(cid, mid):
    edit(cid, mid,
        "📍 *Шаг 2 из 4* — Квалификация события\n\n"
        "Уточните характер останова:",
        kb(
            [("🔴 Останов / срыв сроков ввода или ремонта", "st:stop")],
            [("‼️ Авария", "st:accident")],
        )
    )
    states[cid]["step"] = "stype"

def step_days(cid, mid):
    edit(cid, mid,
        "📍 *Шаг 3 из 4* — Срок устранения\n\n"
        "Каков ожидаемый срок устранения?",
        kb(
            [("📅 До 14 рабочих дней", "days:lt14")],
            [("📅 Более 14 рабочих дней", "days:gt14")],
        )
    )
    states[cid]["step"] = "days"

def step_scale(cid, mid):
    edit(cid, mid,
        "📍 *Шаг 3 из 4* — Масштаб аварии\n\n"
        "Выберите тип пострадавшего оборудования:",
        kb(
            [("🔩 Вспомогательное оборудование", "sc:aux")],
            [("⚙️ Проточная часть (с вскрытием)", "sc:flow")],
            [("🏭 Комплекс оборудования", "sc:complex")],
            [("🆘 Катастрофа (взрыв, пожар, обрушение, блэкаут)", "sc:catastrophe")],
        )
    )
    states[cid]["step"] = "scale"

def step_guarantee(cid, mid):
    edit(cid, mid,
        "📍 *Шаг 4 из 4* — Гарантия\n\n"
        "Оборудование находится на гарантии СМ\n"
        "или это гарантийный случай?",
        kb(
            [("✅ Да, гарантийный случай", "g:yes")],
            [("❌ Нет, не гарантия", "g:no")],
        )
    )
    states[cid]["step"] = "guarantee"

def step_key_client(cid, mid):
    edit(cid, mid,
        "📍 *Шаг 4 из 4* — Статус клиента\n\n"
        "Заказчик является ключевым клиентом СМ?",
        kb(
            [("⭐ Да, ключевой клиент", "kc:yes")],
            [("➖ Нет", "kc:no")],
        )
    )
    states[cid]["step"] = "key_client"


# ═══════════════════════════════════════════════════════════════════
# СБОР ДОПОЛНИТЕЛЬНОЙ ИНФОРМАЦИИ
# ═══════════════════════════════════════════════════════════════════

def start_info(cid, fields):
    """Начинаем сбор текстовых полей"""
    st = states[cid]
    st["step"]     = "info"
    st["fields"]   = fields
    st["info_idx"] = 0
    st["data"].setdefault("files", [])
    _send_next_field(cid)

def _send_next_field(cid):
    st = states[cid]
    idx    = st["info_idx"]
    fields = st["fields"]
    if idx >= len(fields):
        _ask_files(cid)
        return
    field_key, question = fields[idx]
    st["collecting"] = field_key
    send(cid, question)

def _ask_files(cid):
    states[cid]["step"] = "files"
    states[cid]["collecting"] = None
    send(cid,
        "📎 *Файлы и фотографии*\n\n"
        "Прикрепите файлы (фото повреждений, протоколы, акты).\n"
        "Отправляйте по одному.\n\n"
        "Когда всё прикреплено — нажмите «Готово»:",
        kb([("✅ Готово — показать результат", "done:result")])
    )

def _finish(cid, mid=None):
    st  = states[cid]
    d   = st["data"]
    is_lead = d.get("_type") == "lead"
    text = build_lead_result(d) if is_lead else build_incident_result(d)
    if mid:
        edit(cid, mid, text)
    else:
        send(cid, text)
    states.pop(cid, None)


# ═══════════════════════════════════════════════════════════════════
# ОБРАБОТЧИКИ СОБЫТИЙ
# ═══════════════════════════════════════════════════════════════════

def on_callback(cid, mid, cbid, data):
    answer_cb(cbid)
    st = states.get(cid, {})

    if data == "type:incident":
        states[cid] = {"step": "working", "data": {}}
        step_working(cid, mid)

    elif data == "type:lead":
        states[cid] = {"step": "info", "data": {"_type": "lead"},
                       "fields": LEAD_FIELDS, "info_idx": 0, "collecting": None}
        states[cid]["data"].setdefault("files", [])
        send(cid,
            "💡 *Техническая проблема / потенциальный лид*\n\n"
            "Заполните информацию. Я задам несколько вопросов.\n"
        )
        _send_next_field(cid)

    elif data.startswith("w:"):
        st["data"]["working"] = (data[2:] == "yes")
        if st["data"]["working"]:
            step_func_loss(cid, mid)
        else:
            step_stype(cid, mid)

    elif data.startswith("fl:"):
        st["data"]["func_loss"] = data[3:]
        step_guarantee(cid, mid)

    elif data.startswith("st:"):
        st["data"]["stype"] = data[3:]
        if data[3:] == "stop":
            step_days(cid, mid)
        else:
            step_scale(cid, mid)

    elif data.startswith("days:"):
        st["data"]["gt14"] = (data[5:] == "gt14")
        step_guarantee(cid, mid)

    elif data.startswith("sc:"):
        st["data"]["scale"] = data[3:]
        step_guarantee(cid, mid)

    elif data.startswith("g:"):
        st["data"]["guarantee"] = (data[2:] == "yes")
        if st["data"]["guarantee"]:
            start_info(cid, INCIDENT_FIELDS)
        else:
            step_key_client(cid, mid)

    elif data.startswith("kc:"):
        st["data"]["key_client"] = (data[3:] == "yes")
        start_info(cid, INCIDENT_FIELDS)

    elif data == "done:result":
        _finish(cid, mid)


def on_text(cid, text):
    st = states.get(cid)
    if not st:
        send(cid, "Нажмите /start чтобы начать.")
        return

    collecting = st.get("collecting")
    step = st.get("step")

    if step == "info" and collecting:
        st["data"][collecting] = text
        st["collecting"] = None
        st["info_idx"] = st.get("info_idx", 0) + 1
        _send_next_field(cid)
    elif step == "files":
        # Текст во время ожидания файлов — игнорируем, напоминаем
        send(cid,
            "📎 Прикрепите файл или нажмите «Готово»:",
            kb([("✅ Готово — показать результат", "done:result")])
        )


def on_file(cid, file_id, ftype):
    st = states.get(cid)
    if not st:
        return
    if st.get("step") == "files":
        st["data"].setdefault("files", []).append({"id": file_id, "type": ftype})
        count = len(st["data"]["files"])
        send(cid,
            f"✅ Файл {count} получен.\nПрикрепите ещё или нажмите «Готово»:",
            kb([("✅ Готово — показать результат", "done:result")])
        )


# ═══════════════════════════════════════════════════════════════════
# MAIN LOOP
# ═══════════════════════════════════════════════════════════════════

def main():
    print("🤖 Бот v3.0 запущен. Ctrl+C для остановки.")
    offset = 0
    while True:
        try:
            resp = api("getUpdates", offset=offset, timeout=25,
                       allowed_updates=["message", "callback_query"])
            for upd in resp.get("result", []):
                offset = upd["update_id"] + 1

                if "callback_query" in upd:
                    cb  = upd["callback_query"]
                    cid = cb["message"]["chat"]["id"]
                    mid = cb["message"]["message_id"]
                    on_callback(cid, mid, cb["id"], cb["data"])

                elif "message" in upd:
                    msg  = upd["message"]
                    cid  = msg["chat"]["id"]
                    text = msg.get("text", "")

                    if text in ("/start", "/help", "/new"):
                        step_welcome(cid)
                    elif text.startswith("/"):
                        pass
                    elif "document" in msg:
                        on_file(cid, msg["document"]["file_id"], "document")
                    elif "photo" in msg:
                        on_file(cid, msg["photo"][-1]["file_id"], "photo")
                    elif text:
                        on_text(cid, text)

        except KeyboardInterrupt:
            print("\nОстановлено.")
            break
        except Exception as e:
            print(f"Polling error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
