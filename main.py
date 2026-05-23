import os
import json
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.helpers import escape_markdown
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

CRYPTO_WALLET = "UQAoV0EYNaUlcThP1WSPEN8DJU92NUUtXkQxHvaHKseEt3CK"
CRYPTO_NETWORK = "TON"
STARS_USERNAME = "@scammz"
RUB_CARD = "2200 0118 5837 0175"
SUPPORT_NICK = "@scammz"

#Сюда подписку,которую ты купишь
VPN_SUBSCRIPTION_URL = ""

#а сюда картинки серверов,которвеы в этой подписке буду
SERVERS = [
    {"flag": "🇩🇪"},
]

TRIAL_USERS_FILE = "trial_users.json"
TICKETS_FILE = "tickets.json"

# Количество пользователей на одной странице
ITEMS_PER_PAGE = 10

logging.basicConfig(level=logging.INFO)

user_data = {}
user_subscriptions = {}
payment_requests = {}
tickets = {}

SUBSCRIPTIONS_FILE = "subscriptions.json"
REQUESTS_FILE = "payment_requests.json"
REFERRALS_FILE = "referrals.json"

PRICES = {
    "base": {"1 месяц": 150, "3 месяца": 350, "6 месяцев": 600, "12 месяцев": 1000},
    "family": {"1 месяц": 350, "3 месяца": 750, "6 месяцев": 1200, "12 месяцев": 2000}
}

PLAN_NAMES = {
    "base": "Базовый 🪙",
    "family": "Семейный 🫂"
}

PLAN_DESCRIPTIONS = {
    "base": "до 3 устройств",
    "family": "до 6 устройств"
}

def load_tickets():
    global tickets
    try:
        with open(TICKETS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            tickets = {int(k): v for k, v in data.get("tickets", {}).items()}
    except (FileNotFoundError, json.JSONDecodeError):
        tickets = {}

def save_tickets():
    data = {
        "tickets": tickets
    }
    with open(TICKETS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_next_ticket_id():
    if not tickets:
        return 1
    existing_ids = set(tickets.keys())
    new_id = 1
    while new_id in existing_ids:
        new_id += 1
    return new_id

def load_trial_users():
    try:
        with open(TRIAL_USERS_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

def save_trial_users(trial_set):
    with open(TRIAL_USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(list(trial_set), f, ensure_ascii=False, indent=2)

def load_subscriptions():
    try:
        with open(SUBSCRIPTIONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for uid, sub in data.items():
                sub["start_date"] = datetime.fromisoformat(sub["start_date"])
                sub["end_date"] = datetime.fromisoformat(sub["end_date"])
            return {int(k): v for k, v in data.items()}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_subscriptions():
    data = {}
    for uid, sub in user_subscriptions.items():
        data[str(uid)] = {
            "tariff": sub["tariff"],
            "price": sub["price"],
            "plan": sub.get("plan", "base"),
            "start_date": sub["start_date"].isoformat(),
            "end_date": sub["end_date"].isoformat()
        }
    with open(SUBSCRIPTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def save_subscription(user_id, plan, period, price, add_days=True):
    now = datetime.now()
    days_map = {"1 день": 1, "1 месяц": 30, "3 месяца": 90, "6 месяцев": 180, "12 месяцев": 365}
    days = days_map.get(period, 30)
    end = now + timedelta(days=days)
    if add_days and user_id in user_subscriptions:
        old_end = user_subscriptions[user_id]["end_date"]
        if old_end > now:
            end = old_end + timedelta(days=days)
    user_subscriptions[user_id] = {
        "tariff": f"{PLAN_NAMES[plan]} • {period}",
        "price": price,
        "plan": plan,
        "start_date": now,
        "end_date": end
    }
    save_subscriptions()

def delete_subscription(user_id):
    if user_id in user_subscriptions:
        del user_subscriptions[user_id]
        save_subscriptions()
    remove_user_requests(user_id)

def clean_expired_subscriptions():
    now = datetime.now()
    expired = []
    for user_id, sub in user_subscriptions.items():
        if sub["end_date"] < now:
            expired.append(user_id)
    for user_id in expired:
        del user_subscriptions[user_id]
    if expired:
        save_subscriptions()
        print(f"🗑️ Удалено {len(expired)} истекших подписок")

def load_requests():
    global payment_requests
    try:
        with open(REQUESTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            payment_requests = {int(k): v for k, v in data.get("requests", {}).items()}
    except (FileNotFoundError, json.JSONDecodeError):
        payment_requests = {}

def save_requests():
    data = {
        "requests": payment_requests
    }
    with open(REQUESTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_next_request_id():
    if not payment_requests:
        return 1
    existing_ids = set(payment_requests.keys())
    new_id = 1
    while new_id in existing_ids:
        new_id += 1
    return new_id

def remove_user_requests(user_id):
    global payment_requests
    to_delete = [rid for rid, req in payment_requests.items() if req["user_id"] == user_id]
    for rid in to_delete:
        del payment_requests[rid]
    if to_delete:
        save_requests()

def load_referrals():
    try:
        with open(REFERRALS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_referrals(data):
    with open(REFERRALS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

async def check_expiring_soon(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    for user_id, sub in user_subscriptions.items():
        days_left = (sub["end_date"] - now).days
        if days_left == 3:
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"⚠️ *Внимание!* ⚠️\n\n"
                         f"📋 *Ваша подписка «{sub['tariff']}»*\n"
                         f"📅 *Истекает через 3 дня!*\n\n"
                         f"🔄 *Пожалуйста, продлите подписку*, чтобы продолжить пользоваться VPN.\n\n"
                         f"💎 Нажми /start и выбери «Продлить» в личном кабинете.\n\n"
                         f"✨ Спасибо, что с нами! ✨",
                    parse_mode="Markdown"
                )
            except:
                pass

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    clean_expired_subscriptions()
    user_id = update.effective_user.id
    text = "🎉 *OvionVPN* — твой доступ в свободный интернет! 🌐✨\n\n🔄 Стабильность\n🌍 Смена локаций\n📱💻 Для телефонов, компьютеров и планшетов\n\nПопробуй наш VPN совершенно бесплатно 👇"
    keyboard = [
        [InlineKeyboardButton("📱 Android", callback_data="android")],
        [InlineKeyboardButton("🍎 iOS", callback_data="ios")],
        [InlineKeyboardButton("🖥️ Windows", callback_data="windows")],
        [
            InlineKeyboardButton("ℹ️ О VPN", callback_data="faq"),
            InlineKeyboardButton("🆘 Поддержка", callback_data="support")
        ]
    ]
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("🛠️ Админ панель", callback_data="admin_panel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    if from_callback and update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)

async def support_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
🆘 *Поддержка* 🆘

✏️ *Выберите ваш тип обращения*

📌 Сообщение будет отправлено администратору.
⏰ Ответ придёт в ближайшее время.

✨ Спасибо, что с нами! ✨
"""
    keyboard = [
        [
            InlineKeyboardButton("📢 Жалоба", callback_data="ticket_complaint"),
            InlineKeyboardButton("❓ Вопрос", callback_data="ticket_question")
        ],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)

async def ticket_complaint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ticket_id = get_next_ticket_id()
    
    context.user_data["awaiting_ticket"] = ticket_id
    context.user_data["ticket_type"] = "complaint"
    
    text = """
📢 *Жалоба* 📢

✏️ *Напишите вашу жалобу в чат*

📌 Сообщение будет отправлено администратору.
⏰ Ответ придёт в ближайшее время.

✨ Спасибо, что с нами! ✨
"""
    await update.callback_query.edit_message_text(text, parse_mode="Markdown")

async def ticket_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ticket_id = get_next_ticket_id()
    
    context.user_data["awaiting_ticket"] = ticket_id
    context.user_data["ticket_type"] = "question"
    
    text = """
❓ *Вопрос* ❓

✏️ *Напишите ваш вопрос в чат*

📌 Сообщение будет отправлено администратору.
⏰ Ответ придёт в ближайшее время.

✨ Спасибо, что с нами! ✨
"""
    await update.callback_query.edit_message_text(text, parse_mode="Markdown")

async def handle_ticket_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ticket_id = context.user_data.get("awaiting_ticket")
    ticket_type = context.user_data.get("ticket_type")
    
    if not ticket_id:
        return
    
    user_id = update.effective_user.id
    message_text = update.message.text
    username_raw = update.effective_user.username or "нет_username"
    first_name_raw = update.effective_user.first_name or "Пользователь"
    
    # Экранируем для Markdown
    first_name = escape_markdown(first_name_raw)
    username = escape_markdown(username_raw)
    message_escaped = escape_markdown(message_text)
    
    tickets[ticket_id] = {
        "user_id": user_id,
        "username": username_raw,
        "first_name": first_name_raw,
        "type": ticket_type,
        "text": message_text,
        "date": datetime.now().isoformat(),
        "status": "pending"
    }
    save_tickets()
    
    if ticket_type == "complaint":
        await update.message.reply_text(
            "✅ *Ваша жалоба отправлена!*\n\n🕐 Администратор рассмотрит её в ближайшее время.\n\n✨ Спасибо, что с нами!",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "✅ *Ваш вопрос отправлен!*\n\n🕐 Администратор ответит в ближайшее время.\n\n✨ Спасибо, что с нами!",
            parse_mode="Markdown"
        )
    
    type_icon = "📢 Жалоба" if ticket_type == "complaint" else "❓ Вопрос"
    
    keyboard = [[InlineKeyboardButton("📋 Перейти к обращениям", callback_data="admin_tickets")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"📨 *Новое обращение #{ticket_id}*\n\n"
             f"📌 *Тип:* {type_icon}\n"
             f"👤 *Пользователь:* {first_name} (@{username}) ID: `{user_id}`\n"
             f"📝 *Текст:* {message_escaped}\n\n"
             f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    
    context.user_data.pop("awaiting_ticket", None)
    context.user_data.pop("ticket_type", None)

async def admin_tickets_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    pending = {tid: t for tid, t in tickets.items() if t["status"] == "pending"}
    
    if not pending:
        await update.callback_query.edit_message_text("📭 *Нет новых обращений*", parse_mode="Markdown")
        return
    
    # Преобразуем в список для пагинации
    tickets_list = list(pending.items())
    total_tickets = len(tickets_list)
    total_pages = (total_tickets + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    
    if page >= total_pages:
        page = total_pages - 1
    if page < 0:
        page = 0
    
    start_idx = page * ITEMS_PER_PAGE
    end_idx = min(start_idx + ITEMS_PER_PAGE, total_tickets)
    page_tickets = tickets_list[start_idx:end_idx]
    
    text = f"📋 *Новые обращения:*\n\n"
    
    for tid, t in page_tickets:
        type_icon = "📢" if t["type"] == "complaint" else "❓"
        name = escape_markdown(str(t['first_name']))
        username = escape_markdown(str(t['username']))
        text += f"🔹 {type_icon} Обращение #{tid} от {name} (@{username})\n"
    
    text += f"\n📊 *Всего:* {total_tickets} | 📄 *Страница {page + 1} из {total_pages}*"
    
    keyboard = []
    
    # Добавляем кнопки обращений на текущей странице
    for tid, t in page_tickets:
        keyboard.append([InlineKeyboardButton(f"📌 Обращение #{tid}", callback_data=f"admin_ticket_{tid}")])
    
    # Добавляем кнопки навигации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Назад", callback_data=f"admin_tickets_page_{page - 1}"))
    if page + 1 < total_pages:
        nav_buttons.append(InlineKeyboardButton("Вперед ▶️", callback_data=f"admin_tickets_page_{page + 1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="admin_panel")])
    
    await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_ticket_view(update: Update, context: ContextTypes.DEFAULT_TYPE, ticket_id: int):
    t = tickets.get(ticket_id)
    if not t or t["status"] != "pending":
        await update.callback_query.edit_message_text("❌ *Обращение уже обработано*", parse_mode="Markdown")
        return
    
    type_icon = "📢 Жалоба" if t["type"] == "complaint" else "❓ Вопрос"
    name = escape_markdown(str(t['first_name']))
    username = escape_markdown(str(t['username']))
    text_escaped = escape_markdown(str(t['text']))
    
    text = f"""
📌 *Обращение #{ticket_id}*

━━━━━━━━━━━━━━━━━━━
📌 *Тип:* {type_icon}
👤 *Пользователь:* {name} (@{username})
🆔 *ID:* `{t['user_id']}`
📝 *Текст:* {text_escaped}
📅 *Дата:* {t['date']}
━━━━━━━━━━━━━━━━━━━
"""
    keyboard = [
        [InlineKeyboardButton("✏️ Ответить", callback_data=f"admin_ticket_reply_{ticket_id}"),
         InlineKeyboardButton("❌ Отклонить", callback_data=f"admin_ticket_reject_{ticket_id}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="admin_tickets")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)

async def admin_ticket_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, ticket_id: int):
    context.user_data["replying_to_ticket"] = ticket_id
    await update.callback_query.edit_message_text(
        "✏️ *Введите ответ на обращение*\n\n"
        "📝 Напишите текст ответа — он будет отправлен пользователю.\n\n"
        "✨ Будьте вежливы и профессиональны.",
        parse_mode="Markdown"
    )

async def admin_ticket_reject(update: Update, context: ContextTypes.DEFAULT_TYPE, ticket_id: int):
    t = tickets.get(ticket_id)
    if not t or t["status"] != "pending":
        await update.callback_query.edit_message_text("❌ *Обращение уже обработано*", parse_mode="Markdown")
        return
    
    del tickets[ticket_id]
    save_tickets()
    
    await update.callback_query.edit_message_text(f"✅ *Обращение #{ticket_id} отклонено*", parse_mode="Markdown")
    
    type_text = "жалоба" if t["type"] == "complaint" else "вопрос"
    
    await context.bot.send_message(
        chat_id=t["user_id"],
        text=f"📋 *Ваш {type_text} рассмотрен*\n\n"
             f"❌ *Ответ:* Ваше обращение отклонено администратором.\n\n"
             f"📬 Если у вас остались вопросы, свяжитесь с поддержкой: {SUPPORT_NICK}",
        parse_mode="Markdown"
    )

async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ticket_id = context.user_data.get("replying_to_ticket")
    if not ticket_id:
        return
    
    if update.effective_user.id != ADMIN_ID:
        return
    
    reply_text = update.message.text
    t = tickets.get(ticket_id)
    
    if not t or t["status"] != "pending":
        await update.message.reply_text("❌ *Обращение уже обработано*", parse_mode="Markdown")
        context.user_data.pop("replying_to_ticket", None)
        return
    
    del tickets[ticket_id]
    save_tickets()
    
    type_text = "жалобу" if t["type"] == "complaint" else "вопрос"
    
    try:
        await context.bot.send_message(
            chat_id=t["user_id"],
            text=f"📋 *Ответ на ваш {type_text} #{ticket_id}*\n\n"
                 f"✏️ *Сообщение администратора:*\n{reply_text}\n\n"
                 f"✨ Спасибо за обращение!",
            parse_mode="Markdown"
        )
        await update.message.reply_text(f"✅ *Ответ на обращение #{ticket_id} отправлен!*", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ *Ошибка:* {e}", parse_mode="Markdown")
    
    context.user_data.pop("replying_to_ticket", None)

async def profile_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, device: str):
    clean_expired_subscriptions()
    user_id = update.callback_query.from_user.id
    sub = user_subscriptions.get(user_id)
    refs = load_referrals()
    invited = len(refs.get(str(user_id), []))
    
    if not sub:
        text = f"""
👤 *Личный кабинет* — {device}

━━━━━━━━━━━━━━━━━━━
❌ *Нет активной подписки*

💎 Выберите тариф в главном меню!
━━━━━━━━━━━━━━━━━━━
"""
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back")]]
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    days_left = max((sub['end_date'] - datetime.now()).days, 0)
    text = f"""
👤 *Личный кабинет* — {device}

━━━━━━━━━━━━━━━━━━━
📋 Тариф: `{sub['tariff']}`
💰 Оплачено: {sub['price']} ₽
📅 Активация: {sub['start_date'].strftime('%d.%m.%Y')}
⏳ Действует до: {sub['end_date'].strftime('%d.%m.%Y')}
📆 Осталось дней: {days_left}
👥 Приглашено: {invited}
━━━━━━━━━━━━━━━━━━━
"""
    keyboard = [
        [InlineKeyboardButton("🔌 Подключить устройство", callback_data=f"get_link_{device.lower()}")],
        [InlineKeyboardButton("🔄 Продлить подписку", callback_data=f"extend_{device.lower()}")],
        [InlineKeyboardButton("👥 Пригласить", callback_data="invite"), InlineKeyboardButton("ℹ️ О VPN", callback_data="faq")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back")]
    ]
    await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def extend_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, device: str):
    user_id = update.callback_query.from_user.id
    sub = user_subscriptions.get(user_id)
    
    if not sub:
        await update.callback_query.edit_message_text("❌ *Нет активной подписки*", parse_mode="Markdown")
        return
    
    # Если это пробный период, показываем выбор плана
    if sub.get("plan") == "trial":
        text = "🎉 *Пробный период закончился!*\n\n💎 *Выберите платный план:*"
        keyboard = [
            [InlineKeyboardButton(f"{PLAN_NAMES['base']} — {PLAN_DESCRIPTIONS['base']}", callback_data=f"extend_plan_base_{device}")],
            [InlineKeyboardButton(f"{PLAN_NAMES['family']} — {PLAN_DESCRIPTIONS['family']}", callback_data=f"extend_plan_family_{device}")],
            [InlineKeyboardButton("⬅️ Назад", callback_data=f"back_to_profile_{device}")]
        ]
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    # Для обычных подписок показываем продление с текущим планом
    plan = sub.get("plan", "base")
    
    text = f"🔄 *Продление подписки*\n\n📋 *Ваш план:* {PLAN_NAMES[plan]}\n\n💎 *Выберите период:*"
    
    if plan == "base":
        keyboard = [
            [InlineKeyboardButton("📆 1 месяц — 150 ₽", callback_data=f"extend_period_1_base_{device}")],
            [InlineKeyboardButton("📆 3 месяца — 350 ₽ 🔥", callback_data=f"extend_period_3_base_{device}")],
            [InlineKeyboardButton("📆 6 месяцев — 600 ₽ ⚡", callback_data=f"extend_period_6_base_{device}")],
            [InlineKeyboardButton("📆 12 месяцев — 1000 ₽ 🎁", callback_data=f"extend_period_12_base_{device}")],
            [InlineKeyboardButton("⬅️ Назад", callback_data=f"back_to_profile_{device}")]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("📆 1 месяц — 350 ₽", callback_data=f"extend_period_1_family_{device}")],
            [InlineKeyboardButton("📆 3 месяца — 750 ₽ 🔥", callback_data=f"extend_period_3_family_{device}")],
            [InlineKeyboardButton("📆 6 месяцев — 1200 ₽ ⚡", callback_data=f"extend_period_6_family_{device}")],
            [InlineKeyboardButton("📆 12 месяцев — 2000 ₽ 🎁", callback_data=f"extend_period_12_family_{device}")],
            [InlineKeyboardButton("⬅️ Назад", callback_data=f"back_to_profile_{device}")]
        ]
    
    await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def extend_plan_choice(update: Update, context: ContextTypes.DEFAULT_TYPE, plan: str, device: str):
    text = f"🔄 *Продление подписки*\n\n📋 *Выбран план:* {PLAN_NAMES[plan]}\n\n💎 *Выберите период:*"
    
    if plan == "base":
        keyboard = [
            [InlineKeyboardButton("📆 1 месяц — 150 ₽", callback_data=f"extend_period_1_base_{device}")],
            [InlineKeyboardButton("📆 3 месяца — 350 ₽ 🔥", callback_data=f"extend_period_3_base_{device}")],
            [InlineKeyboardButton("📆 6 месяцев — 600 ₽ ⚡", callback_data=f"extend_period_6_base_{device}")],
            [InlineKeyboardButton("📆 12 месяцев — 1000 ₽ 🎁", callback_data=f"extend_period_12_base_{device}")],
            [InlineKeyboardButton("⬅️ Назад", callback_data=f"extend_{device}")]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("📆 1 месяц — 350 ₽", callback_data=f"extend_period_1_family_{device}")],
            [InlineKeyboardButton("📆 3 месяца — 750 ₽ 🔥", callback_data=f"extend_period_3_family_{device}")],
            [InlineKeyboardButton("📆 6 месяцев — 1200 ₽ ⚡", callback_data=f"extend_period_6_family_{device}")],
            [InlineKeyboardButton("📆 12 месяцев — 2000 ₽ 🎁", callback_data=f"extend_period_12_family_{device}")],
            [InlineKeyboardButton("⬅️ Назад", callback_data=f"extend_{device}")]
        ]
    
    await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def extend_payment_menu(update, period_num: str, plan: str, price: int, device: str):
    user_data[update.callback_query.from_user.id] = {"plan": plan, "period": period_num, "price": price, "device": device}
    period_map = {"1": "1 месяц", "3": "3 месяца", "6": "6 месяцев", "12": "12 месяцев"}
    period = period_map[period_num]
    
    text = f"💳 *Оплата продления «{PLAN_NAMES[plan]} • {period}»*\n\n💵 Сумма: *{price} ₽*\n\nВыбери способ оплаты:"
    keyboard = [
        [InlineKeyboardButton("💎 Telegram Stars", callback_data=f"pay_stars_extend_{device}_{plan}_{period_num}_{price}")],
        [InlineKeyboardButton("₿ Крипта (TON)", callback_data=f"pay_crypto_extend_{device}_{plan}_{period_num}_{price}")],
        [InlineKeyboardButton("🇷🇺 Рубли (карта)", callback_data=f"pay_rub_extend_{device}_{plan}_{period_num}_{price}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data=f"back_to_extend_{device}")]
    ]
    await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def get_vpn_link(update, device):
    clean_expired_subscriptions()
    user_id = update.callback_query.from_user.id
    sub = user_subscriptions.get(user_id)
    if not sub:
        await update.callback_query.edit_message_text("❌ *Нет активной подписки*\n\nКупи тариф в главном меню.", parse_mode="Markdown")
        return
    
    if VPN_SUBSCRIPTION_URL:
        user_link = VPN_SUBSCRIPTION_URL
    else:
        user_link = f"https://happ.link/connect?user={user_id}&token={int(datetime.now().timestamp())}"
    
    if not SERVERS:
        servers_text = "❌ *Серверов пока что нет.*\n"
    else:
        flags = "".join([s["flag"] for s in SERVERS])
        servers_text = f"🌍 *Доступные сервера:*\n\n{flags}\n"
    
    if device == "Android":
        app_text = "📱 *Android*\n👉 [Скачать из Google Play](https://play.google.com/store/apps/details?id=com.happproxy)"
    elif device == "iOS":
        app_text = "🍎 *iOS*\n👉 [Скачать из App Store](https://apps.apple.com/ru/app/happ-proxy-utility-plus/id6746188973)"
    elif device == "Windows":
        app_text = "🖥️ *Windows*\n👉 [Скачать с GitHub](https://github.com/Happ-proxy/happ-desktop/releases/latest)\nВыбери setup-Happ.x64.exe"
    else:
        app_text = "❌ *Неизвестное устройство*"
    
    full_text = f"""
{servers_text}
🔌 *Ваша ссылка для подключения:*
`{user_link}`

📱 *Как подключиться:*
1️⃣ Скопируй ссылку выше
2️⃣ Скачай приложение:
{app_text}
3️⃣ Открой приложение → «+» → «Вставить из буфера»
4️⃣ Нажми «Подключиться»

✅ *Готово! Ты в защищённой сети.*
"""
    keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data=f"back_to_profile_{device.lower()}")]]
    await update.callback_query.edit_message_text(full_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)

async def trial_period(update, device):
    clean_expired_subscriptions()
    user_id = update.callback_query.from_user.id
    trial_users = load_trial_users()
    
    if str(user_id) in trial_users:
        await update.callback_query.edit_message_text(
            "❌ *Пробный период уже был использован*\n\n"
            "Пробный период можно активировать только один раз.\n"
            "Приобретите платную подписку в главном меню.",
            parse_mode="Markdown"
        )
        return
    
    now = datetime.now()
    end = now + timedelta(days=1)
    user_subscriptions[user_id] = {
        "tariff": "Пробный период • 1 день",
        "price": 0,
        "plan": "trial",
        "start_date": now,
        "end_date": end
    }
    save_subscriptions()
    
    trial_users.add(str(user_id))
    save_trial_users(trial_users)
    
    text = f"""
🎉 *Вам выдан пробный период!* 🎉

📋 *Тариф:* 1 день
💰 *Сумма:* 0 ₽
📅 *Действует до:* {end.strftime('%d.%m.%Y')}

🔌 *Чтобы начать пользоваться VPN:*
1️⃣ Зайдите в *Личный кабинет*
2️⃣ Нажмите *«Подключить устройство»*
3️⃣ Получите ссылку и вставьте в *Happ*

✨ Спасибо, что с нами! ✨
"""
    keyboard = [[InlineKeyboardButton("👤 Перейти в личный кабинет", callback_data=f"profile_{device.lower()}")]]
    await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def buy_menu(update, device):
    clean_expired_subscriptions()
    user_id = update.callback_query.from_user.id
    trial_users = load_trial_users()
    has_trial = str(user_id) in trial_users
    
    text = f"💎 *Выберите план подписки для {device}*"
    keyboard = [
        [InlineKeyboardButton(f"{PLAN_NAMES['base']} — {PLAN_DESCRIPTIONS['base']}", callback_data=f"plan_base_{device.lower()}")],
        [InlineKeyboardButton(f"{PLAN_NAMES['family']} — {PLAN_DESCRIPTIONS['family']}", callback_data=f"plan_family_{device.lower()}")],
    ]
    
    if not has_trial:
        keyboard.append([InlineKeyboardButton("🎁 Пробный период (1 день)", callback_data=f"trial_{device.lower()}")])
    
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back")])
    
    await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def period_menu(update, device, plan):
    user_data[update.callback_query.from_user.id] = {"plan": plan, "device": device}
    
    text = f"💎 *Выберите период для {PLAN_NAMES[plan]}*"
    
    if plan == "base":
        keyboard = [
            [InlineKeyboardButton("📆 1 месяц — 150 ₽", callback_data=f"period_1_{plan}_{device.lower()}")],
            [InlineKeyboardButton("📆 3 месяца — 350 ₽ 🔥", callback_data=f"period_3_{plan}_{device.lower()}")],
            [InlineKeyboardButton("📆 6 месяцев — 600 ₽ ⚡", callback_data=f"period_6_{plan}_{device.lower()}")],
            [InlineKeyboardButton("📆 12 месяцев — 1000 ₽ 🎁", callback_data=f"period_12_{plan}_{device.lower()}")],
            [InlineKeyboardButton("⬅️ Назад", callback_data=f"back_to_plans_{device.lower()}")]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("📆 1 месяц — 350 ₽", callback_data=f"period_1_{plan}_{device.lower()}")],
            [InlineKeyboardButton("📆 3 месяца — 750 ₽ 🔥", callback_data=f"period_3_{plan}_{device.lower()}")],
            [InlineKeyboardButton("📆 6 месяцев — 1200 ₽ ⚡", callback_data=f"period_6_{plan}_{device.lower()}")],
            [InlineKeyboardButton("📆 12 месяцев — 2000 ₽ 🎁", callback_data=f"period_12_{plan}_{device.lower()}")],
            [InlineKeyboardButton("⬅️ Назад", callback_data=f"back_to_plans_{device.lower()}")]
        ]
    
    await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def payment_menu(update, plan, period, price, device, is_extend):
    user_data[update.callback_query.from_user.id] = {"plan": plan, "period": period, "price": price, "device": device}
    text = f"💳 *Оплата подписки «{PLAN_NAMES[plan]} • {period}»*\n\n💵 Сумма: *{price} ₽*\n\nВыбери способ оплаты:"
    keyboard = [
        [InlineKeyboardButton("💎 Telegram Stars", callback_data=f"pay_stars_new_{device}_{plan}_{period}_{price}")],
        [InlineKeyboardButton("₿ Крипта (TON)", callback_data=f"pay_crypto_new_{device}_{plan}_{period}_{price}")],
        [InlineKeyboardButton("🇷🇺 Рубли (карта)", callback_data=f"pay_rub_new_{device}_{plan}_{period}_{price}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data=f"back_to_periods_{plan}_{device}_False")]
    ]
    await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def send_payment_instruction(update, user_id, device, plan, period, price, is_extend, method):
    req_id = get_next_request_id()
    payment_requests[req_id] = {
        "user_id": user_id, "device": device, "plan": plan, "period": period, "price": price,
        "is_extend": is_extend, "method": method, "status": "pending", "photo_file_id": None
    }
    save_requests()
    
    type_text = "продления" if is_extend else "подписки"
    
    if method == "stars":
        text = f"💎 *Оплата {type_text}*\n\n📋 Тариф: {PLAN_NAMES[plan]} • {period}\n💰 Сумма: {price} ₽ → {price} ⭐\n\n📬 Переведи звёзды: {STARS_USERNAME}\n\n✨ *После оплаты нажми на кнопку ниже и отправь скриншот перевода* ✨"
    elif method == "crypto":
        ton = round(price / 120, 4)
        text = f"₿ *Оплата {type_text}*\n\n📋 Тариф: {PLAN_NAMES[plan]} • {period}\n💰 Сумма: {price} ₽ ≈ {ton} TON\n\n📬 Кошелёк:\nСеть: `{CRYPTO_NETWORK}`\nАдрес: `{CRYPTO_WALLET}`\n\n✨ *После оплаты нажми на кнопку ниже и отправь хэш транзакции* ✨"
    else:
        text = f"🇷🇺 *Оплата {type_text}*\n\n📋 Тариф: {PLAN_NAMES[plan]} • {period}\n💰 Сумма: {price} ₽\n\n📬 Реквизиты:\n{RUB_CARD}\n\n✨ *После оплаты нажми на кнопку ниже и отправь скриншот перевода* ✨"
    
    keyboard = [[InlineKeyboardButton("✅ Я оплатил(а)", callback_data=f"confirm_payment_{req_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)

async def confirm_payment(update: Update, context: ContextTypes.DEFAULT_TYPE, req_id: int):
    req = payment_requests.get(req_id)
    if not req or req["status"] != "pending":
        await update.callback_query.edit_message_text("❌ Заявка уже обработана или не найдена", parse_mode="Markdown")
        return
    
    text = """
📸 *Подтверждение оплаты*

━━━━━━━━━━━━━━━━━━━
✨ *Пожалуйста, отправь подтверждающий документ:*

• Скриншот перевода из банка 💳
• Хэш транзакции ₿
• Скриншот перевода звёзд ⭐

━━━━━━━━━━━━━━━━━━━

📌 *Отправь фото или файл прямо в этот чат*

✅ После проверки администратор активирует подписку
"""
    await update.callback_query.edit_message_text(text, parse_mode="Markdown")
    context.user_data["awaiting_payment_proof"] = req_id

async def handle_payment_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    req_id = context.user_data.get("awaiting_payment_proof")
    if not req_id:
        return
    req = payment_requests.get(req_id)
    if not req or req["user_id"] != user_id or req["status"] != "pending":
        context.user_data.pop("awaiting_payment_proof", None)
        await update.message.reply_text("❌ Заявка не найдена или уже обработана", parse_mode="Markdown")
        return
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        req["photo_file_id"] = file_id
        save_requests()
        await update.message.reply_text(
            "✅ *Спасибо!* 📸\n\nТвой платёжный документ получен.\n🕐 Администратор проверит его в ближайшее время.\n\n✨ После активации ты получишь уведомление!",
            parse_mode="Markdown"
        )
        user = update.effective_user
        username = f" (@{user.username})" if user.username else ""
        keyboard = [[InlineKeyboardButton("📋 Перейти к заявкам", callback_data="admin_requests")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📨 *Новая заявка на оплату*\n\n👤 Пользователь: {user_id}{username}\n📋 Заявка #{req_id}\n📱 Устройство: {req['device']}\n📋 План: {req['plan']}\n📅 Период: {req['period']}\n💰 Сумма: {req['price']} ₽\n🔄 Тип: {'Продление' if req['is_extend'] else 'Новая подписка'}\n💳 Способ: {req['method']}\n\n📅 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        context.user_data.pop("awaiting_payment_proof", None)
    else:
        await update.message.reply_text(
            "⚠️ *Пожалуйста, отправь именно ФОТО или СКРИНШОТ*\n\n📸 Нажми на скрепку → выбери «Фото» или «Галерея»\n\nПосле этого администратор сможет проверить твою оплату.",
            parse_mode="Markdown"
        )

async def invite_menu(update, context):
    user_id = update.callback_query.from_user.id
    link = f"https://t.me/{context.bot.username}?start=ref_{user_id}"
    text = f"👥 *Пригласи ссылку*\n\n`{link}`\n\n✨ Друг перейдёт — получишь бонус после его подписки ✨"
    keyboard = [[InlineKeyboardButton("📤 Поделиться", url=f"https://t.me/share/url?url={link}&text=🔥 Отличный VPN! Подключайся по моей ссылке:")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="back")]]
    await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)

async def faq_menu(update, context):
    text = f"""
🔹 *О OvionVPN* 🔹

⚡ Скоростной VPN без ограничений
❌ Без лимитов
📱 Устройства: Android, iOS, Windows
💳 Оплата: Рубли, Крипта, Stars
🎁 Пробный период: 1 день

🌟 *OvionVPN — твой ключ к свободе!* 🌟

📌 По всем вопросам: {SUPPORT_NICK}
"""
    keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back")]]
    await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query.from_user.id != ADMIN_ID:
        await update.callback_query.edit_message_text("❌ Доступ запрещён", parse_mode="Markdown")
        return
    text = "🛠️ *Админ панель*\n\nВыбери действие:"
    keyboard = [
        [InlineKeyboardButton("➕ Выдать подписку", callback_data="admin_give_id")],
        [InlineKeyboardButton("➖ Забрать подписку", callback_data="admin_remove_list")],
        [InlineKeyboardButton("📋 Заявки на оплату", callback_data="admin_requests")],
        [InlineKeyboardButton("📋 Обращения", callback_data="admin_tickets")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back")]
    ]
    await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_give_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.edit_message_text(
        "✏️ *Введите Telegram ID пользователя*\n\n📌 *Как узнать ID?*\nПопросите пользователя написать `/id` в этом боте\n\n💡 *Пример:* `123456789`",
        parse_mode="Markdown"
    )
    context.user_data["admin_action"] = "waiting_id"

# Функция admin_remove_list с пагинацией
async def admin_remove_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    if not user_subscriptions:
        await update.callback_query.edit_message_text("📭 Нет активных подписок", parse_mode="Markdown")
        return
    
    # Получаем список пользователей (исключая админа)
    users_list = []
    for uid in user_subscriptions:
        if uid == ADMIN_ID:
            continue
        try:
            user = await context.bot.get_chat(uid)
            name = user.full_name or str(uid)
            username_display = f"@{user.username}" if user.username else "нет_username"
            users_list.append({
                "id": uid,
                "name": name,
                "username": username_display
            })
        except:
            users_list.append({
                "id": uid,
                "name": str(uid),
                "username": "нет_username"
            })
    
    total_users = len(users_list)
    total_pages = (total_users + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE if total_users > 0 else 1
    
    if page >= total_pages:
        page = total_pages - 1
    if page < 0:
        page = 0
    
    start_idx = page * ITEMS_PER_PAGE
    end_idx = min(start_idx + ITEMS_PER_PAGE, total_users)
    page_users = users_list[start_idx:end_idx]
    
    # Формируем текст
    text = f"📋 *Пользователи с подпиской:*\n\n"
    
    for u in page_users:
        name_escaped = escape_markdown(u['name'])
        username_escaped = escape_markdown(u['username'])
        text += f"🔹 {name_escaped} — {username_escaped} (`{u['id']}`)\n"
    
    if total_users > 0:
        text += f"\n📊 *Всего:* {total_users} | 📄 *Страница {page + 1} из {total_pages}*"
    else:
        text += "\n📭 *Нет пользователей*"
    
    # Строим клавиатуру
    keyboard = []
    
    # Добавляем кнопки пользователей на текущей странице
    for u in page_users:
        username_escaped = escape_markdown(u['username'])
        button_text = f"❌ {username_escaped} ({u['id']})"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"admin_remove_{u['id']}")])
    
    # Добавляем кнопки навигации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Назад", callback_data=f"admin_remove_page_{page - 1}"))
    if page + 1 < total_pages and total_users > 0:
        nav_buttons.append(InlineKeyboardButton("Вперед ▶️", callback_data=f"admin_remove_page_{page + 1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Кнопка назад в админку
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="admin_panel")])
    
    await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_requests_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pending = {rid: req for rid, req in payment_requests.items() if req["status"] == "pending"}
    if not pending:
        await update.callback_query.edit_message_text("📭 Нет новых заявок", parse_mode="Markdown")
        return
    text = "📋 *Новые заявки:*\n"
    keyboard = []
    for rid, req in pending.items():
        text += f"\n🔹 Заявка #{rid} от `{req['user_id']}` — {PLAN_NAMES.get(req['plan'], req['plan'])} • {req['period']} ({req['price']}₽)"
        keyboard.append([InlineKeyboardButton(f"📌 Заявка #{rid}", callback_data=f"admin_req_{rid}")])
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="admin_panel")])
    await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_show_request(update: Update, context: ContextTypes.DEFAULT_TYPE, req_id: int):
    req = payment_requests.get(req_id)
    if not req or req["status"] != "pending":
        await update.callback_query.edit_message_text("❌ Заявка уже обработана", parse_mode="Markdown")
        return
    user_id = req['user_id']
    username = ""
    try:
        chat = await context.bot.get_chat(user_id)
        username = f" (@{escape_markdown(chat.username)})" if chat.username else ""
    except:
        pass
    text = f"""
📌 *Заявка #{req_id}* от `{user_id}`{username}

━━━━━━━━━━━━━━━━━━━
📱 Устройство: {req['device']}
📋 План: {PLAN_NAMES.get(req['plan'], req['plan'])}
📅 Период: {req['period']}
💰 Сумма: {req['price']} ₽
🔄 Тип: {'Продление' if req['is_extend'] else 'Новая подписка'}
💳 Способ: {req['method']}
━━━━━━━━━━━━━━━━━━━
"""
    keyboard = [
        [InlineKeyboardButton("✅ Принять", callback_data=f"admin_accept_{req_id}"),
         InlineKeyboardButton("❌ Отклонить", callback_data=f"admin_reject_{req_id}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="admin_requests")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.delete_message()
    if req.get("photo_file_id"):
        await context.bot.send_photo(
            chat_id=update.callback_query.from_user.id,
            photo=req["photo_file_id"],
            caption=text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    else:
        await context.bot.send_message(
            chat_id=update.callback_query.from_user.id,
            text=text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

async def admin_accept_request(update: Update, context: ContextTypes.DEFAULT_TYPE, req_id: int):
    req = payment_requests.get(req_id)
    if not req or req["status"] != "pending":
        await update.callback_query.edit_message_text("❌ Заявка уже обработана", parse_mode="Markdown")
        return
    
    save_subscription(req["user_id"], req["plan"], req["period"], req["price"], add_days=req["is_extend"])
    del payment_requests[req_id]
    save_requests()
    await update.callback_query.delete_message()
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"✅ *Заявка #{req_id} принята!*\n\n👤 Пользователь: `{req['user_id']}`\n📋 План: {PLAN_NAMES.get(req['plan'], req['plan'])}\n📅 Период: {req['period']}\n💰 Сумма: {req['price']} ₽",
        parse_mode="Markdown"
    )
    keyboard = [[InlineKeyboardButton("👤 Перейти в личный кабинет", callback_data="profile")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(
        chat_id=req["user_id"],
        text="✅ *Ваша подписка активирована!*\n\n✨ Зайди в личный кабинет, чтобы получить ссылку для подключения.\n\n🌍 Спасибо, что с нами!",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

async def admin_reject_request(update: Update, context: ContextTypes.DEFAULT_TYPE, req_id: int):
    req = payment_requests.get(req_id)
    if not req or req["status"] != "pending":
        await update.callback_query.edit_message_text("❌ Заявка уже обработана", parse_mode="Markdown")
        return
    user_id = req["user_id"]
    del payment_requests[req_id]
    save_requests()
    await update.callback_query.delete_message()
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"❌ *Заявка #{req_id} отклонена и удалена*",
        parse_mode="Markdown"
    )
    await context.bot.send_message(
        chat_id=user_id,
        text=f"❌ *Ваша заявка отклонена*\n\nПожалуйста, проверьте правильность оплаты и отправьте подтверждение снова.\n\n📬 Связь с поддержкой: {SUPPORT_NICK}",
        parse_mode="Markdown"
    )

async def handle_admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("admin_action") == "waiting_id":
        text_input = update.message.text.strip()
        if not text_input.lstrip('-').isdigit():
            await update.message.reply_text(
                "❌ *Ошибка!* Введите корректный Telegram ID (только цифры).\n\n📌 Пример: `123456789`",
                parse_mode="Markdown"
            )
            return
        user_id = int(text_input)
        try:
            user = await context.bot.get_chat(user_id)
            user_name_display = f"@{escape_markdown(user.username)}" if user.username else escape_markdown(user.first_name)
            context.user_data["target_user_id"] = user_id
            context.user_data["target_username"] = user_name_display
            context.user_data["admin_action"] = "waiting_tariff"
            text = f"✅ *Вы выбрали:* {user_name_display} (ID: `{user_id}`)\n\n📋 *Выберите план и период:*\n\n"
            keyboard = [
                [InlineKeyboardButton(f"{PLAN_NAMES['base']} — 1 месяц", callback_data="admin_tariff_base_1")],
                [InlineKeyboardButton(f"{PLAN_NAMES['base']} — 3 месяца", callback_data="admin_tariff_base_3")],
                [InlineKeyboardButton(f"{PLAN_NAMES['base']} — 6 месяцев", callback_data="admin_tariff_base_6")],
                [InlineKeyboardButton(f"{PLAN_NAMES['base']} — 12 месяцев", callback_data="admin_tariff_base_12")],
                [InlineKeyboardButton(f"{PLAN_NAMES['family']} — 1 месяц", callback_data="admin_tariff_family_1")],
                [InlineKeyboardButton(f"{PLAN_NAMES['family']} — 3 месяца", callback_data="admin_tariff_family_3")],
                [InlineKeyboardButton(f"{PLAN_NAMES['family']} — 6 месяцев", callback_data="admin_tariff_family_6")],
                [InlineKeyboardButton(f"{PLAN_NAMES['family']} — 12 месяцев", callback_data="admin_tariff_family_12")],
                [InlineKeyboardButton("⬅️ Отмена", callback_data="admin_panel")]
            ]
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception as e:
            await update.message.reply_text(
                "❌ *Пользователь не найден!*\n\n🔍 Проверьте правильность ID.\n📌 Пользователь должен написать боту хотя бы `/start`, чтобы бот его \"увидел\".",
                parse_mode="Markdown"
            )

async def admin_tariff_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    parts = data.split("_")
    plan = parts[2]
    period_num = parts[3]
    
    plan_prices = {
        "base": {"1": 150, "3": 350, "6": 600, "12": 1000},
        "family": {"1": 350, "3": 750, "6": 1200, "12": 2000}
    }
    period_map = {"1": "1 месяц", "3": "3 месяца", "6": "6 месяцев", "12": "12 месяцев"}
    
    period = period_map[period_num]
    price = plan_prices[plan][period_num]
    user_id = context.user_data.get("target_user_id")
    user_name_display = context.user_data.get("target_username", str(user_id))
    
    if not user_id:
        await update.callback_query.edit_message_text("❌ *Ошибка!* Пользователь не найден.", parse_mode="Markdown")
        return
    
    save_subscription(user_id, plan, period, price, add_days=False)
    
    await update.callback_query.edit_message_text(
        f"✅ *Подписка успешно выдана!*\n\n"
        f"👤 *Пользователь:* {user_name_display} (ID: `{user_id}`)\n"
        f"📋 *План:* {PLAN_NAMES[plan]}\n"
        f"📅 *Период:* {period}\n"
        f"💰 *Сумма:* {price} ₽\n\n"
        f"🎉 Пользователь получит уведомление.",
        parse_mode="Markdown"
    )
    keyboard = [[InlineKeyboardButton("👤 Перейти в личный кабинет", callback_data="profile")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(
        chat_id=user_id,
        text=f"🎉 *Вам выдана подписка!* 🎉\n\n"
             f"📋 *План:* {PLAN_NAMES[plan]}\n"
             f"📅 *Период:* {period}\n"
             f"💰 *Сумма:* {price} ₽\n\n"
             f"🔌 *Чтобы начать пользоваться VPN:*\n"
             f"1️⃣ Зайдите в *Личный кабинет*\n"
             f"2️⃣ Нажмите *«Подключить устройство»*\n"
             f"3️⃣ Получите ссылку и вставьте в *Happ*\n\n"
             f"✨ Спасибо, что с нами! ✨",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    context.user_data["admin_action"] = None

async def admin_remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    delete_subscription(user_id)
    await update.callback_query.edit_message_text(f"✅ *Подписка удалена* у пользователя `{user_id}`", parse_mode="Markdown")
    await context.bot.send_message(
        chat_id=user_id,
        text="❌ *Ваша подписка была удалена администратором*\n\nЕсли вы считаете, что это ошибка, свяжитесь с поддержкой.",
        parse_mode="Markdown"
    )

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username
    first_name = update.effective_user.first_name
    text = f"👤 *Ваши данные*\n\n🆔 *Telegram ID:* `{user_id}`\n📝 *Имя:* {escape_markdown(first_name)}\n"
    if username:
        text += f"🔹 *Username:* @{escape_markdown(username)}\n"
    text += f"\n✨ Скопируйте этот ID и отправьте администратору для получения подписки."
    await update.message.reply_text(text, parse_mode="Markdown")

# ========== ЕДИНЫЙ МАРШРУТИЗАТОР ==========
async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("replying_to_ticket"):
        await handle_admin_reply(update, context)
        return

    if context.user_data.get("awaiting_ticket"):
        await handle_ticket_message(update, context)
        return

    if context.user_data.get("admin_action"):
        await handle_admin_text(update, context)
        return

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == "back":
        await main_menu(update, context, from_callback=True)
    elif data == "faq":
        await faq_menu(update, context)
    elif data == "invite":
        await invite_menu(update, context)
    elif data == "support":
        await support_menu(update, context)
    elif data == "ticket_complaint":
        await ticket_complaint(update, context)
    elif data == "ticket_question":
        await ticket_question(update, context)
    elif data == "profile":
        device = "Android"
        sub = user_subscriptions.get(user_id)
        if sub:
            await profile_menu(update, context, device)
        else:
            await buy_menu(update, device)
    elif data.startswith("profile_"):
        device = data.split("_")[1].capitalize()
        if device == "Ios":
            device = "iOS"
        await profile_menu(update, context, device)
    elif data.startswith("trial_"):
        device = data.split("_")[1].capitalize()
        if device == "Ios":
            device = "iOS"
        await trial_period(update, device)
    elif data.startswith("plan_"):
        parts = data.split("_")
        plan = parts[1]
        device = parts[2].capitalize()
        if device == "Ios":
            device = "iOS"
        await period_menu(update, device, plan)
    elif data.startswith("back_to_plans_"):
        device = data.split("_")[3].capitalize()
        if device == "Ios":
            device = "iOS"
        await buy_menu(update, device)
    elif data.startswith("period_"):
        parts = data.split("_")
        period_num = parts[1]
        plan = parts[2]
        device = parts[3].capitalize()
        if device == "Ios":
            device = "iOS"
        period_map = {"1": "1 месяц", "3": "3 месяца", "6": "6 месяцев", "12": "12 месяцев"}
        period = period_map[period_num]
        price = PRICES[plan][period]
        await payment_menu(update, plan, period, price, device, is_extend=False)
    elif data.startswith("extend_plan_"):
        parts = data.split("_")
        plan = parts[2]
        device = parts[3]
        await extend_plan_choice(update, context, plan, device)
    elif data.startswith("extend_period_"):
        parts = data.split("_")
        period_num = parts[2]
        plan = parts[3]
        device = parts[4]
        
        period_map = {
            "1": "1 месяц",
            "3": "3 месяца",
            "6": "6 месяцев",
            "12": "12 месяцев"
        }
        
        period = period_map[period_num]
        price = PRICES[plan][period]
        
        await extend_payment_menu(update, period_num, plan, price, device)
    elif data.startswith("extend_"):
        device = data.split("_")[1].capitalize()
        if device == "Ios":
            device = "iOS"
        await extend_menu(update, context, device)
    elif data.startswith("back_to_extend_"):
        device = data.split("_")[3]
        await extend_menu(update, context, device)
    elif data.startswith("back_to_periods_"):
        parts = data.split("_")
        plan = parts[3]
        device = parts[4].capitalize()
        is_extend = parts[5] == "True"
        if device == "Ios":
            device = "iOS"
        await period_menu(update, device, plan)
    elif data == "admin_panel":
        await admin_panel(update, context)
    elif data == "admin_give_id":
        await admin_give_id(update, context)
    elif data == "admin_remove_list":
        await admin_remove_list(update, context)
    elif data.startswith("admin_remove_page_"):
        page = int(data.split("_")[3])
        await admin_remove_list(update, context, page)
    elif data == "admin_requests":
        await admin_requests_menu(update, context)
    elif data == "admin_tickets":
        await admin_tickets_menu(update, context)
    elif data.startswith("admin_tickets_page_"):
        page = int(data.split("_")[3])
        await admin_tickets_menu(update, context, page)
    elif data.startswith("admin_ticket_"):
        if "reply" in data:
            tid = int(data.split("_")[3])
            await admin_ticket_reply(update, context, tid)
        elif "reject" in data:
            tid = int(data.split("_")[3])
            await admin_ticket_reject(update, context, tid)
        else:
            tid = int(data.split("_")[2])
            await admin_ticket_view(update, context, tid)
    elif data.startswith("admin_remove_"):
        uid = int(data.split("_")[2])
        await admin_remove_user(update, context, uid)
    elif data.startswith("admin_req_"):
        rid = int(data.split("_")[2])
        await admin_show_request(update, context, rid)
    elif data.startswith("admin_accept_"):
        rid = int(data.split("_")[2])
        await admin_accept_request(update, context, rid)
    elif data.startswith("admin_reject_"):
        rid = int(data.split("_")[2])
        await admin_reject_request(update, context, rid)
    elif data.startswith("admin_tariff_"):
        await admin_tariff_choice(update, context)
    elif data.startswith("confirm_payment_"):
        rid = int(data.split("_")[2])
        await confirm_payment(update, context, rid)
    elif data in ["android", "ios", "windows"]:
        if data == "ios":
            device = "iOS"
        else:
            device = data.capitalize()
        sub = user_subscriptions.get(user_id)
        if sub:
            await profile_menu(update, context, device)
        else:
            await buy_menu(update, device)
    elif data.startswith("get_link_"):
        device = data.split("_")[2].capitalize()
        if device == "Ios":
            device = "iOS"
        await get_vpn_link(update, device)
    elif data.startswith("pay_stars_new_"):
        parts = data.split("_")
        device = parts[3].capitalize()
        if device == "Ios":
            device = "iOS"
        plan = parts[4]
        period = parts[5]
        price = int(parts[6])
        await send_payment_instruction(update, user_id, device, plan, period, price, is_extend=False, method="stars")
    elif data.startswith("pay_crypto_new_"):
        parts = data.split("_")
        device = parts[3].capitalize()
        if device == "Ios":
            device = "iOS"
        plan = parts[4]
        period = parts[5]
        price = int(parts[6])
        await send_payment_instruction(update, user_id, device, plan, period, price, is_extend=False, method="crypto")
    elif data.startswith("pay_rub_new_"):
        parts = data.split("_")
        device = parts[3].capitalize()
        if device == "Ios":
            device = "iOS"
        plan = parts[4]
        period = parts[5]
        price = int(parts[6])
        await send_payment_instruction(update, user_id, device, plan, period, price, is_extend=False, method="rub")
    elif data.startswith("pay_stars_extend_"):
        parts = data.split("_")
        device = parts[3]
        plan = parts[4]
        period_num = parts[5]
        price = int(parts[6])
        
        period_map = {
            "1": "1 месяц",
            "3": "3 месяца",
            "6": "6 месяцев",
            "12": "12 месяцев"
        }
        period = period_map[period_num]
        
        await send_payment_instruction(update, user_id, device, plan, period, price, is_extend=True, method="stars")
    elif data.startswith("pay_crypto_extend_"):
        parts = data.split("_")
        device = parts[3]
        plan = parts[4]
        period_num = parts[5]
        price = int(parts[6])
        
        period_map = {
            "1": "1 месяц",
            "3": "3 месяца",
            "6": "6 месяцев",
            "12": "12 месяцев"
        }
        period = period_map[period_num]
        
        await send_payment_instruction(update, user_id, device, plan, period, price, is_extend=True, method="crypto")
    elif data.startswith("pay_rub_extend_"):
        parts = data.split("_")
        device = parts[3]
        plan = parts[4]
        period_num = parts[5]
        price = int(parts[6])
        
        period_map = {
            "1": "1 месяц",
            "3": "3 месяца",
            "6": "6 месяцев",
            "12": "12 месяцев"
        }
        period = period_map[period_num]
        
        await send_payment_instruction(update, user_id, device, plan, period, price, is_extend=True, method="rub")
    elif data.startswith("back_to_profile_"):
        device = data.split("_")[3].capitalize()
        if device == "Ios":
            device = "iOS"
        await profile_menu(update, context, device)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clean_expired_subscriptions()
    user_id = update.effective_user.id
    if context.args and context.args[0].startswith("ref_"):
        ref_id = int(context.args[0].split("_")[1])
        if ref_id != user_id:
            refs = load_referrals()
            if str(user_id) not in refs.get(str(ref_id), []):
                refs.setdefault(str(ref_id), []).append(str(user_id))
                save_referrals(refs)
    await main_menu(update, context)

async def daily_check(context: ContextTypes.DEFAULT_TYPE):
    clean_expired_subscriptions()
    await check_expiring_soon(context)

def main():
    global user_subscriptions
    user_subscriptions = load_subscriptions()
    load_requests()
    load_tickets()
    clean_expired_subscriptions()
    print(f"📁 Подписок: {len(user_subscriptions)}, заявок: {len(payment_requests)}, обращений: {len(tickets)}")
    print("🚀 VPN запущен")
    
    app = Application.builder().token(TOKEN).build()
    
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_daily(daily_check, time=datetime.strptime("12:00", "%H:%M").time())
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", get_id))
    app.add_handler(MessageHandler(filters.PHOTO, handle_payment_proof))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    app.run_polling()

if __name__ == "__main__":
    main()