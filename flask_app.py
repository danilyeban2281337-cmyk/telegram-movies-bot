import logging
import time
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ConversationHandler, ContextTypes
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== Настройки =====
TOKEN = "8333782250:AAGJB8VWICLYDH25_6OymlQIo4xU6V9ccKo"
ADMINS = [986905315, 1844738340, 668733591]

# ===== База данных =====
movies_db = {}
last_reminder = {}  # user_id -> timestamp последней рассылки

# ===== Состояния =====
STATE_SEARCH, STATE_ADD_CODE, STATE_ADD_NAME, STATE_ADD_GENRE, STATE_ADD_DESC, STATE_ADD_IMAGE = range(6)
STATE_UPDATE_CODE, STATE_UPDATE_FIELD, STATE_UPDATE_VALUE = range(6, 9)
STATE_DELETE_CODE = 9

# ===== Flask =====
app = Flask(__name__)
bot = Bot(token=TOKEN)
tg_app = Application.builder().token(TOKEN).build()

# ===== Функции рассылки =====
async def send_reminder(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("📢 Подписаться", url="https://t.me/+2aEKMiwM90hkNjY1")]]
    await context.bot.send_message(
        chat_id=user_id,
        text="⚠️ На случай блокировки бота подпишитесь на канал!\n\n"
             "В этом канале всегда актуальный бот ✅",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def check_and_send_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    now = time.time()
    last = last_reminder.get(user_id, 0)
    if now - last >= 24 * 3600:
        await send_reminder(user_id, context)
        last_reminder[user_id] = now

# ===== Главное меню =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await check_and_send_reminder(update, context)
    user_id = update.effective_user.id
    keyboard = [[InlineKeyboardButton("🔍 Поиск фильма", callback_data="search")]]
    if user_id in ADMINS:
        keyboard.append([InlineKeyboardButton("⚙️ Админ-панель", callback_data="admin")])
    await update.message.reply_text(
        "👋 Добро пожаловать в библиотеку фильмов! 🎬\n\n"
        "📚 Здесь ты найдешь лучшие фильмы, включая самые свежие новинки!\n\n"
        "Выберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await check_and_send_reminder(update, context)
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    keyboard = [[InlineKeyboardButton("🔍 Поиск фильма", callback_data="search")]]
    if user_id in ADMINS:
        keyboard.append([InlineKeyboardButton("⚙️ Админ-панель", callback_data="admin")])
    await query.message.reply_text(
        "👋 Главное меню:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ===== Поиск фильма =====
async def search_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await check_and_send_reminder(update, context)
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Введите код фильма для поиска:")
    return STATE_SEARCH

async def search_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await check_and_send_reminder(update, context)
    code = update.message.text.strip()
    movie = movies_db.get(code)
    keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]]
    if not movie:
        await update.message.reply_text("❌ Фильм с таким кодом не найден!", reply_markup=InlineKeyboardMarkup(keyboard))
        return ConversationHandler.END
    caption = (
        f"🎬 Название: {movie.get('name','—')}\n"
        f"📌 Жанр: {movie.get('genre','—')}\n"
        f"📝 Описание: {movie.get('desc','—')}"
    )
    image = (movie.get("image") or "").strip()
    if image:
        try:
            await update.message.reply_photo(photo=image, caption=caption,
                                           reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception as e:
            logger.warning("Не удалось отправить фото для кода %s: %s", code, e)
            await update.message.reply_text(caption, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(caption, reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

# ===== Админ-панель =====
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await check_and_send_reminder(update, context)
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if user_id not in ADMINS:
        await query.message.reply_text("❌ У вас нет доступа!")
        return
    keyboard = [
        [InlineKeyboardButton("➕ Добавить фильм", callback_data="add_film")],
        [InlineKeyboardButton("♻️ Обновить фильм", callback_data="update")],
        [InlineKeyboardButton("❌ Удалить фильм", callback_data="delete")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")],
    ]
    await query.message.reply_text("🔐 Админ-панель:\nВыберите действие:",
                                   reply_markup=InlineKeyboardMarkup(keyboard))

# ===== Добавление фильма =====
async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Введите код фильма:")
    return STATE_ADD_CODE

async def add_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    if code in movies_db:
        await update.message.reply_text("❌ Фильм с таким кодом уже существует! Введите другой код:")
        return STATE_ADD_CODE
    context.user_data["code"] = code
    await update.message.reply_text("Введите название фильма:")
    return STATE_ADD_NAME

async def add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text.strip()
    await update.message.reply_text("Введите жанр фильма:")
    return STATE_ADD_GENRE

async def add_genre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["genre"] = update.message.text.strip()
    await update.message.reply_text("Введите описание фильма:")
    return STATE_ADD_DESC

async def add_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["desc"] = update.message.text.strip()
    await update.message.reply_text("Введите ссылку на картинку (или 'нет'):")
    return STATE_ADD_IMAGE

async def add_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = context.user_data["code"]
    image_value = update.message.text.strip()
    movies_db[code] = {
        "name": context.user_data["name"],
        "genre": context.user_data["genre"],
        "desc": context.user_data["desc"],
        "image": None if image_value.lower() == "нет" else image_value,
    }
    keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]]
    await update.message.reply_text("✅ Фильм добавлен!", reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

# ===== Обновление фильма =====
async def update_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Введите код фильма для обновления:")
    return STATE_UPDATE_CODE

async def update_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    if code not in movies_db:
        keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]]
        await update.message.reply_text("❌ Фильм с таким кодом не найден!", reply_markup=InlineKeyboardMarkup(keyboard))
        return ConversationHandler.END
    context.user_data["code"] = code
    keyboard = [
        [InlineKeyboardButton("Название", callback_data="field_name")],
        [InlineKeyboardButton("Жанр", callback_data="field_genre")],
        [InlineKeyboardButton("Описание", callback_data="field_desc")],
        [InlineKeyboardButton("Картинка", callback_data="field_image")],
    ]
    await update.message.reply_text("Выберите поле для обновления:", reply_markup=InlineKeyboardMarkup(keyboard))
    return STATE_UPDATE_FIELD

async def update_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    field_map = {
        "field_name": "name",
        "field_genre": "genre",
        "field_desc": "desc",
        "field_image": "image"
    }
    context.user_data["field"] = field_map.get(query.data)
    await query.message.reply_text(f"Введите новое значение для {context.user_data['field']}:")
    return STATE_UPDATE_VALUE

async def update_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = context.user_data["code"]
    field = context.user_data["field"]
    movies_db[code][field] = update.message.text.strip()
    keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]]
    await update.message.reply_text("✅ Фильм обновлён!", reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

# ===== Удаление фильма =====
async def delete_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Введите код фильма для удаления:")
    return STATE_DELETE_CODE

async def delete_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]]
    if code in movies_db:
        del movies_db[code]
        await update.message.reply_text("🗑 Фильм удалён!", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text("❌ Фильм с таким кодом не найден!", reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

# ===== Регистрация хэндлеров =====
def register_handlers(app: Application):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(main_menu, pattern="main_menu"))
    app.add_handler(CallbackQueryHandler(search_start, pattern="search"))
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="admin"))

    search_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(search_start, pattern="search")],
        states={STATE_SEARCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_movie)]},
        fallbacks=[]
    )
    add_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_start, pattern="add_film")],
        states={
            STATE_ADD_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_code)],
            STATE_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_name)],
            STATE_ADD_GENRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_genre)],
            STATE_ADD_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_desc)],
            STATE_ADD_IMAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_image)],
        },
        fallbacks=[]
    )
    update_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(update_start, pattern="update")],
        states={
            STATE_UPDATE_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, update_code)],
            STATE_UPDATE_FIELD: [CallbackQueryHandler(update_field, pattern="field_.*")],
            STATE_UPDATE_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, update_value)],
        },
        fallbacks=[]
    )
    delete_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(delete_start, pattern="delete")],
        states={STATE_DELETE_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_code)]},
        fallbacks=[]
    )

    app.add_handler(search_conv)
    app.add_handler(add_conv)
    app.add_handler(update_conv)
    app.add_handler(delete_conv)

register_handlers(tg_app)

# ===== Webhook для Render =====
@app.route(f"/webhook/{TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    tg_app.update_queue.put(update)
    return "OK", 200
