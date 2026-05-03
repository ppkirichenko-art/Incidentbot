"""
Telegram-бот классификации инцидентов — Силовые Машины
Логика: Матрица классификации инцидентов (Слайд 3)

Установка: pip install python-telegram-bot==20.7
Запуск:    python bot.py   (токен можно вписать прямо в консоль)
"""

import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── Состояния диалога ──────────────────────────────────────────────────────────
S_CLIENT_TYPE   = 0
S_EQUIPMENT     = 1
S_SEVERITY      = 2
S_POWER         = 3   # мощность блока >500 МВт?
S_CASUALTIES    = 4   # есть пострадавшие?
S_DONE          = 5

# ── Справочники ────────────────────────────────────────────────────────────────
CLIENT_TYPES = {
    "guarantee": "🔵 Гарантия / Вх. контроль / Монтаж / ПНР\n(исполнение обязательств)",
    "key":       "🟡 Ключевой клиент\n(поддержание лояльности)",
    "other":     "⚪ Прочие клиенты\n(налаживание сотрудничества)",
}

EQUIPMENT_TYPES = {
    "aux":      "🔩 Вспомогательное оборудование\n(без вскрытия)",
    "flow":     "⚙️ Проточная часть\n(с вскрытием)",
    "complex":  "🏭 Комплекс",
}

SEVERITY_TYPES = {
    "question":    "💬 Эксплуатационный вопрос",
    "minor":       "🟡 Неисправность\n(незначительное влияние, без останова)",
    "major":       "🟠 Серьёзная потеря функциональности\n(без останова)",
    "stop":        "🔴 Останов / срыв сроков ввода или ремонта",
    "accident":    "‼️ Авария",
    "catastrophe": "🆘 Техногенная катастрофа\n(взрыв, обрушение, пожар, блэкаут)",
}

# ── Сценарии реагирования ──────────────────────────────────────────────────────
SCENARIOS = {
    "K1": {
        "code": "K1",
        "name": "Удалённая консультация",
        "deadline": "3 рабочих дня",
        "description": "Консультация по запросу. Решение принимается на уровне руководителя подразделения.",
        "escalation": "Руководитель подразделения → ЗГД (при необходимости)",
        "emoji": "💬",
    },
    "K2": {
        "code": "K2",
        "name": "Срочная удалённая консультация",
        "deadline": "1 рабочий день",
        "description": "Оперативная консультация по удалённым каналам связи.",
        "escalation": "Руководитель подразделения → ЗГД (при необходимости)",
        "emoji": "📞",
    },
    "K3": {
        "code": "K3",
        "name": "Консультация с привлечением КБ",
        "deadline": "3 рабочих дня",
        "description": "Привлечение дополнительных специалистов КБ, выполнение расчётов, разработка рекомендаций.",
        "escalation": "ЗГД по сбыту",
        "emoji": "🔬",
    },
    "R1": {
        "code": "Р1",
        "name": "Командирование специалистов",
        "deadline": "5 рабочих дней (или по договору)",
        "description": "Командирование специалистов для осмотра, обследования или участия в расследовании.",
        "escalation": "ЗГД по сбыту",
        "emoji": "👨‍🔧",
    },
    "R2": {
        "code": "Р2",
        "name": "Поиск запчастей",
        "deadline": "5 рабочих дней",
        "description": "Поиск запчастей на складах или у партнёров (внешняя кооперация).",
        "escalation": "ЗГД по сбыту",
        "emoji": "🔍",
    },
    "R3": {
        "code": "Р3",
        "name": "Командирование ремонтной бригады",
        "deadline": "10 рабочих дней",
        "description": "Командирование бригады для выполнения ремонта оборудования на станции. Включает Р1 и Р2.",
        "escalation": "ЗГД по сбыту",
        "emoji": "🛠️",
    },
    "R4": {
        "code": "Р4",
        "name": "Срочное изготовление / ремонт в цехах СМ",
        "deadline": "5 рабочих дней",
        "description": "Срочное размещение изготовления деталей или ремонт оборудования в цехах СМ. Включает Р1 и Р2.",
        "escalation": "ЗГД по сбыту",
        "emoji": "🏗️",
    },
    "R5": {
        "code": "Р5",
        "name": "Штаб с участием ГД",
        "deadline": "⚡ Немедленно",
        "description": "Формирование штаба с участием ГД для контроля и ускорения решения ситуации. Информировать УКБК.",
        "escalation": "ГД — формирование штаба СМ",
        "emoji": "🚨",
    },
    "R6": {
        "code": "Р6",
        "name": "Штаб СМ на объекте эксплуатации",
        "deadline": "⚡ Немедленно",
        "description": "Формирование штаба СМ и включение СМ в штаб инцидента на объекте. GR + УКБК + юристы.",
        "escalation": "ГД — кризисный штаб на объекте",
        "emoji": "🆘",
    },
}

# ── Матрица классификации (слайд 3) ───────────────────────────────────────────
# Ключ: (client_type, equipment, severity) → список сценариев
# $ — платное оказание услуг (помечаем в результате)
# *** — повышение уровня если мощность >500 МВт (логика отдельно)

MATRIX = {
    # ── ГАРАНТИЯ / ПНР ─────────────────────────────────────────────────────
    ("guarantee", "aux",     "question"):    (["K2"],       False),
    ("guarantee", "flow",    "question"):    (["K2"],       False),
    ("guarantee", "complex", "question"):    (["K2"],       False),
    ("guarantee", "aux",     "minor"):       (["K3"],       False),
    ("guarantee", "flow",    "minor"):       (["K3"],       False),
    ("guarantee", "complex", "minor"):       (["K3"],       False),
    ("guarantee", "aux",     "major"):       (["K3"],       False),
    ("guarantee", "flow",    "major"):       (["K3"],       False),
    ("guarantee", "complex", "major"):       (["K3"],       False),
    ("guarantee", "aux",     "stop"):        (["K3", "R1"], False),  # K3/Р1***
    ("guarantee", "flow",    "stop"):        (["R1", "R2"], False),
    ("guarantee", "complex", "stop"):        (["R1", "R2"], False),
    ("guarantee", "aux",     "accident"):    (["R3"],       False),
    ("guarantee", "flow",    "accident"):    (["R3"],       False),
    ("guarantee", "complex", "accident"):    (["R3", "R4"], False),
    ("guarantee", "aux",     "catastrophe"): (["R4", "R5"], False),
    ("guarantee", "flow",    "catastrophe"): (["R5", "R6"], False),
    ("guarantee", "complex", "catastrophe"): (["R5", "R6"], False),

    # ── КЛЮЧЕВОЙ КЛИЕНТ ────────────────────────────────────────────────────
    ("key", "aux",     "question"):    (["K1"],       False),
    ("key", "flow",    "question"):    (["K1"],       False),
    ("key", "complex", "question"):    (["K1"],       False),
    ("key", "aux",     "minor"):       (["K2"],       False),
    ("key", "flow",    "minor"):       (["K2"],       False),
    ("key", "complex", "minor"):       (["K2"],       False),
    ("key", "aux",     "major"):       (["K2", "R1"], True),   # $
    ("key", "flow",    "major"):       (["K2", "R1"], True),
    ("key", "complex", "major"):       (["K2", "R1"], True),
    ("key", "aux",     "stop"):        (["K2"],       False),
    ("key", "flow",    "stop"):        (["K3", "R1"], False),
    ("key", "complex", "stop"):        (["K3", "R1"], False),
    ("key", "aux",     "accident"):    (["R2"],       False),
    ("key", "flow",    "accident"):    (["R3"],       True),   # $
    ("key", "complex", "accident"):    (["R4", "R5"], True),   # $
    ("key", "aux",     "catastrophe"): (["R4", "R5"], True),   # $
    ("key", "flow",    "catastrophe"): (["R5", "R6"], False),
    ("key", "complex", "catastrophe"): (["R5", "R6"], False),

    # ── ПРОЧИЕ КЛИЕНТЫ ────────────────────────────────────────────────────
    ("other", "aux",     "question"):    (["K1"],       False),
    ("other", "flow",    "question"):    (["K1"],       False),
    ("other", "complex", "question"):    (["K1"],       False),
    ("other", "aux",     "minor"):       (["K1"],       False),
    ("other", "flow",    "minor"):       (["K1"],       False),
    ("other", "complex", "minor"):       (["K1"],       False),
    ("other", "aux",     "major"):       (["K2"],       True),  # $
    ("other", "flow",    "major"):       (["K2"],       True),
    ("other", "complex", "major"):       (["K2"],       True),
    ("other", "aux",     "stop"):        (["K1"],       False),
    ("other", "flow",    "stop"):        (["K2"],       True),  # $
    ("other", "complex", "stop"):        (["K2"],       True),
    ("other", "aux",     "accident"):    (["K3"],       True),  # $
    ("other", "flow",    "accident"):    (["R2"],       False),
    ("other", "complex", "accident"):    (["R1", "R2"], True),  # $
    ("other", "aux",     "catastrophe"): (["R3", "R4"], True),  # $
    ("other", "flow",    "catastrophe"): (["R3", "R4"], True),
    ("other", "complex", "catastrophe"): (["R4", "R5", "R6"], True),
}

# Сценарии, при которых мощность >500 МВт повышает уровень
POWER_UPGRADE_SCENARIOS = {
    "K3": "R1", "R1": "R2", "R2": "R3",
    "R3": "R4", "R4": "R5", "R5": "R6",
}

# ── Хелперы ────────────────────────────────────────────────────────────────────
def make_keyboard(options: dict, prefix: str) -> InlineKeyboardMarkup:
    """Строит inline-клавиатуру из словаря {callback_data: label}."""
    buttons = [
        [InlineKeyboardButton(label, callback_data=f"{prefix}:{key}")]
        for key, label in options.items()
    ]
    return InlineKeyboardMarkup(buttons)

def scenario_card(code: str) -> str:
    s = SCENARIOS.get(code)
    if not s:
        return f"• {code}"
    return (
        f"{s['emoji']} *{s['code']} — {s['name']}*\n"
        f"   ⏱ Срок реакции: {s['deadline']}\n"
        f"   📋 {s['description']}\n"
        f"   📊 Эскалация: {s['escalation']}"
    )

def build_result(data: dict) -> str:
    client  = data["client_type"]
    equip   = data["equipment"]
    sev     = data["severity"]
    power   = data.get("high_power", False)
    casual  = data.get("casualties", False)

    key = (client, equip, sev)
    scenarios_list, is_paid = MATRIX.get(key, (["R5"], False))

    # Автоматическое повышение при пострадавших
    if casual:
        scenarios_list = ["R5", "R6"]
        is_paid = False
        note = "⚠️ *Зафиксированы пострадавшие — автоматически присвоен максимальный уровень.*\n\n"
    else:
        note = ""

    # Повышение при мощности >500 МВт
    if power and not casual:
        upgraded = []
        for sc in scenarios_list:
            upgraded.append(POWER_UPGRADE_SCENARIOS.get(sc, sc))
        scenarios_list = list(dict.fromkeys(upgraded))  # убираем дубли
        note += "⚡ *Мощность блока >500 МВт — уровень повышен на одну ступень.*\n\n"

    # Формируем карточку
    client_label = CLIENT_TYPES[client].split("\n")[0].strip()
    equip_label  = EQUIPMENT_TYPES[equip].split("\n")[0].strip()
    sev_label    = SEVERITY_TYPES[sev]
    paid_note    = "\n💰 _Услуга оказывается на платной основе ($)_" if is_paid else ""

    header = (
        f"📋 *РЕЗУЛЬТАТ КЛАССИФИКАЦИИ*\n"
        f"{'─' * 32}\n"
        f"👥 Клиент: {client_label}\n"
        f"🔧 Оборудование: {equip_label}\n"
        f"📊 Тяжесть: {sev_label}\n"
        f"{'─' * 32}\n\n"
        f"{note}"
        f"🎯 *Сценарий{'и' if len(scenarios_list) > 1 else ''} реагирования:*\n\n"
    )

    body = "\n\n".join(scenario_card(sc) for sc in scenarios_list)
    footer = (
        f"\n{paid_note}\n\n"
        f"{'─' * 32}\n"
        f"_Нажмите /start для новой классификации_"
    )

    return header + body + footer

# ── Обработчики ────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    text = (
        "👋 *Классификатор инцидентов СМ*\n\n"
        "Я задам несколько вопросов и определю сценарий реагирования "
        "по матрице классификации инцидентов.\n\n"
        "*Шаг 1 из 3* — Выберите тип клиента:"
    )
    keyboard = make_keyboard(CLIENT_TYPES, "client")
    await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")
    return S_CLIENT_TYPE

async def handle_client_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    value = query.data.split(":")[1]
    context.user_data["client_type"] = value
    label = CLIENT_TYPES[value].split("\n")[0].strip()
    await query.edit_message_text(
        f"✅ Клиент: *{label}*\n\n"
        f"*Шаг 2 из 3* — Выберите тип оборудования:",
        reply_markup=make_keyboard(EQUIPMENT_TYPES, "equip"),
        parse_mode="Markdown"
    )
    return S_EQUIPMENT

async def handle_equipment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    value = query.data.split(":")[1]
    context.user_data["equipment"] = value
    label = EQUIPMENT_TYPES[value].split("\n")[0].strip()
    await query.edit_message_text(
        f"✅ Оборудование: *{label}*\n\n"
        f"*Шаг 3 из 3* — Оцените тяжесть инцидента:",
        reply_markup=make_keyboard(SEVERITY_TYPES, "sev"),
        parse_mode="Markdown"
    )
    return S_SEVERITY

async def handle_severity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    value = query.data.split(":")[1]
    context.user_data["severity"] = value

    # Уточняющий вопрос про мощность (только при аварии или останове)
    if value in ("accident", "catastrophe", "stop"):
        await query.edit_message_text(
            f"✅ Тяжесть: *{SEVERITY_TYPES[value]}*\n\n"
            f"⚡ *Уточнение* — Мощность энергоблока превышает 500 МВт "
            f"(для гидро — 300 МВт)?\n\n"
            f"_При ответе «Да» уровень реагирования автоматически повышается на одну ступень_",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Да, >500 МВт", callback_data="power:yes")],
                [InlineKeyboardButton("❌ Нет",          callback_data="power:no")],
            ]),
            parse_mode="Markdown"
        )
        return S_POWER
    else:
        context.user_data["high_power"] = False
        # Спросим про пострадавших всегда кроме вопроса
        if value != "question":
            await query.edit_message_text(
                f"✅ Тяжесть: *{SEVERITY_TYPES[value]}*\n\n"
                f"🚑 *Уточнение* — Есть ли пострадавшие или угроза жизни людей?\n\n"
                f"_При наличии пострадавших автоматически присваивается уровень Р5–Р6_",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⚠️ Да, есть пострадавшие", callback_data="cas:yes")],
                    [InlineKeyboardButton("✅ Нет пострадавших",       callback_data="cas:no")],
                ]),
                parse_mode="Markdown"
            )
            return S_CASUALTIES
        else:
            context.user_data["casualties"] = False
            result = build_result(context.user_data)
            await query.edit_message_text(result, parse_mode="Markdown")
            return ConversationHandler.END

async def handle_power(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    value = query.data.split(":")[1]
    context.user_data["high_power"] = (value == "yes")

    await query.edit_message_text(
        f"{'⚡ Мощность >500 МВт — уровень будет повышен.' if value == 'yes' else '✅ Мощность ≤500 МВт.'}\n\n"
        f"🚑 *Уточнение* — Есть ли пострадавшие или угроза жизни людей?\n\n"
        f"_При наличии пострадавших автоматически присваивается уровень Р5–Р6_",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⚠️ Да, есть пострадавшие", callback_data="cas:yes")],
            [InlineKeyboardButton("✅ Нет пострадавших",       callback_data="cas:no")],
        ]),
        parse_mode="Markdown"
    )
    return S_CASUALTIES

async def handle_casualties(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    value = query.data.split(":")[1]
    context.user_data["casualties"] = (value == "yes")
    result = build_result(context.user_data)
    await query.edit_message_text(result, parse_mode="Markdown")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ Классификация отменена. Нажмите /start чтобы начать заново.")
    return ConversationHandler.END

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📖 *Справка*\n\n"
        "/start — начать классификацию инцидента\n"
        "/cancel — отменить текущую классификацию\n"
        "/help — показать эту справку\n\n"
        "Бот задаёт 3–5 вопросов и определяет сценарий реагирования "
        "по корпоративной матрице классификации инцидентов (Слайд 3).",
        parse_mode="Markdown"
    )

# ── Точка входа ────────────────────────────────────────────────────────────────
def main() -> None:
    token = os.environ.get("BOT_TOKEN")
    if not token:
        print("=" * 55)
        print("  🤖 Бот классификации инцидентов — Силовые Машины")
        print("=" * 55)
        print("  Переменная BOT_TOKEN не найдена.")
        print("  Вставьте токен от @BotFather и нажмите Enter:\n")
        token = input("  Токен >>> ").strip()
    if not token:
        print("❌ Токен не введён. Запустите бота снова.")
        return

    app = Application.builder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            S_CLIENT_TYPE: [CallbackQueryHandler(handle_client_type, pattern="^client:")],
            S_EQUIPMENT:   [CallbackQueryHandler(handle_equipment,   pattern="^equip:")],
            S_SEVERITY:    [CallbackQueryHandler(handle_severity,    pattern="^sev:")],
            S_POWER:       [CallbackQueryHandler(handle_power,       pattern="^power:")],
            S_CASUALTIES:  [CallbackQueryHandler(handle_casualties,  pattern="^cas:")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("help", help_cmd))

    print("🤖 Бот запущен. Ctrl+C для остановки.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
