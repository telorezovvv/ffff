import asyncio
import logging
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# ============= ВСТАВЬ СВОИ ДАННЫЕ ЗДЕСЬ =============
BOT_TOKEN = "8874682296:AAELInLbRLVDhQ_BgzpVUWc9rOELLMtZt6Y"  # ← Свой токен
ADMIN_CHAT_ID = -1004342858165  # ← Свой ID админ-чата (с минусом если группа)
# ===================================================

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ============= БАЗА ДАННЫХ =============
DB_NAME = "feedback.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            is_banned INTEGER DEFAULT 0,
            reg_date TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            message_id INTEGER,
            chat_id INTEGER,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            admin_id INTEGER,
            message_id INTEGER,
            chat_id INTEGER,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def register_user(user_id: int, username: str = None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)', (user_id, username))
    conn.commit()
    conn.close()

def is_banned(user_id: int) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT is_banned FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row and row[0] == 1

def ban_user(user_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_banned = 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def unban_user(user_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_banned = 0 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, username, first_name, is_banned FROM users')
    users = cursor.fetchall()
    conn.close()
    return users

# ============= ХРАНИЛИЩЕ СООБЩЕНИЙ ДЛЯ УДАЛЕНИЯ =============
user_messages = {}

async def delete_old_messages(user_id: int):
    """Удаляет все старые сообщения пользователя"""
    if user_id in user_messages:
        for msg_id in user_messages[user_id]:
            try:
                await bot.delete_message(user_id, msg_id)
            except:
                pass
    user_messages[user_id] = []

async def save_message(message: Message):
    """Сохраняет ID сообщения для удаления"""
    user_id = message.from_user.id
    if user_id not in user_messages:
        user_messages[user_id] = []
    user_messages[user_id].append(message.message_id)
    # Оставляем только последние 5 сообщений
    if len(user_messages[user_id]) > 5:
        user_messages[user_id] = user_messages[user_id][-5:]

# ============= КЛАВИАТУРЫ =============
def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Написать администратору", callback_data="write_admin")],
        [InlineKeyboardButton(text="❓ Частые вопросы", callback_data="faq")],
        [InlineKeyboardButton(text="📖 Информация", callback_data="info")]
    ])

def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🚫 Забанить", callback_data="admin_ban")],
        [InlineKeyboardButton(text="✅ Разбанить", callback_data="admin_unban")],
        [InlineKeyboardButton(text="📝 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])

def back_to_main_btn():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]
    ])

# ============= СОСТОЯНИЯ =============
class FeedbackStates(StatesGroup):
    waiting_for_message = State()
    waiting_for_reply = State()
    waiting_for_ban_user = State()
    waiting_for_unban_user = State()
    waiting_for_broadcast = State()
    waiting_for_admin_reply = State()

# ============= ОБРАБОТЧИКИ =============
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await delete_old_messages(message.from_user.id)
    register_user(message.from_user.id, message.from_user.username)
    
    msg = await message.answer(
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        f"📌 Я бот обратной связи.\n"
        f"Ты можешь задать вопрос, отправить жалобу или предложение.\n\n"
        f"💬 Напиши мне что-нибудь, и я передам это администраторам.",
        reply_markup=main_menu()
    )
    await save_message(msg)

@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    await delete_old_messages(callback.from_user.id)
    msg = await callback.message.edit_text(
        "📌 Главное меню:",
        reply_markup=main_menu()
    )
    await save_message(msg)
    await callback.answer()

@dp.callback_query(F.data == "write_admin")
async def write_admin(callback: CallbackQuery, state: FSMContext):
    await delete_old_messages(callback.from_user.id)
    await state.set_state(FeedbackStates.waiting_for_message)
    
    msg = await callback.message.edit_text(
        "✍️ **Напиши своё сообщение администратору.**\n\n"
        "Можешь отправить текст, фото, видео или документ.\n\n"
        "❗ Ты получишь ответ, когда администратор ответит.",
        reply_markup=back_to_main_btn(),
        parse_mode="Markdown"
    )
    await save_message(msg)
    await callback.answer()

@dp.message(FeedbackStates.waiting_for_message)
async def forward_to_admin(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    if is_banned(user_id):
        msg = await message.answer("🚫 Вы забанены и не можете отправлять сообщения.")
        await save_message(msg)
        await state.clear()
        return
    
    await delete_old_messages(user_id)
    await save_message(message)
    
    # Формируем текст для админа
    text = (
        f"📩 **Новое сообщение от пользователя**\n\n"
        f"👤 ID: `{user_id}`\n"
        f"📛 Имя: {message.from_user.first_name}\n"
        f"🆔 Username: @{message.from_user.username or 'Нет'}\n\n"
    )
    
    # Добавляем текст если есть
    if message.text:
        text += f"💬 Текст: {message.text}"
    elif message.caption:
        text += f"💬 Текст: {message.caption}"
    else:
        text += "📎 Вложение без текста"
    
    # Отправляем админу
    forwarded = await bot.send_message(ADMIN_CHAT_ID, text, parse_mode="Markdown")
    
    # Если есть медиа, пересылаем отдельно
    if message.photo:
        await bot.send_photo(ADMIN_CHAT_ID, message.photo[-1].file_id, caption="📸 Фото от пользователя")
    elif message.video:
        await bot.send_video(ADMIN_CHAT_ID, message.video.file_id, caption="🎬 Видео от пользователя")
    elif message.document:
        await bot.send_document(ADMIN_CHAT_ID, message.document.file_id, caption="📄 Документ от пользователя")
    elif message.audio:
        await bot.send_audio(ADMIN_CHAT_ID, message.audio.file_id, caption="🎵 Аудио от пользователя")
    elif message.voice:
        await bot.send_voice(ADMIN_CHAT_ID, message.voice.file_id, caption="🎤 Голосовое от пользователя")
    
    # Сохраняем в базу
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO messages_log (user_id, message_id, chat_id) VALUES (?, ?, ?)',
                  (user_id, message.message_id, message.chat.id))
    conn.commit()
    conn.close()
    
    msg = await message.answer(
        "✅ **Сообщение отправлено администратору!**\n\n"
        "⏳ Ожидай ответа. Как только админ ответит, я перешлю тебе.",
        reply_markup=back_to_main_btn(),
        parse_mode="Markdown"
    )
    await save_message(msg)
    await state.clear()

# ============= АДМИН-ПАНЕЛЬ =============
@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id not in [ADMIN_CHAT_ID]:
        await message.answer("⛔ Нет доступа")
        return
    
    await delete_old_messages(message.from_user.id)
    msg = await message.answer(
        "🛠 **Админ-панель**\n\n"
        "Выбери действие:",
        reply_markup=admin_menu(),
        parse_mode="Markdown"
    )
    await save_message(msg)

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    if callback.from_user.id not in [ADMIN_CHAT_ID]:
        await callback.answer("⛔ Нет доступа")
        return
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM users WHERE is_banned = 1')
    banned_users = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM messages_log')
    total_messages = cursor.fetchone()[0]
    conn.close()
    
    msg = await callback.message.edit_text(
        f"📊 **Статистика**\n\n"
        f"👤 Всего пользователей: {total_users}\n"
        f"🚫 Забанено: {banned_users}\n"
        f"💬 Сообщений: {total_messages}",
        reply_markup=back_to_main_btn(),
        parse_mode="Markdown"
    )
    await save_message(msg)
    await callback.answer()

@dp.callback_query(F.data == "admin_ban")
async def admin_ban(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in [ADMIN_CHAT_ID]:
        await callback.answer("⛔ Нет доступа")
        return
    
    await state.set_state(FeedbackStates.waiting_for_ban_user)
    msg = await callback.message.edit_text(
        "🚫 **Введите ID пользователя для бана**\n\n"
        "Пример: `123456789`",
        reply_markup=back_to_main_btn(),
        parse_mode="Markdown"
    )
    await save_message(msg)
    await callback.answer()

@dp.message(FeedbackStates.waiting_for_ban_user)
async def process_ban(message: Message, state: FSMContext):
    if message.from_user.id not in [ADMIN_CHAT_ID]:
        return
    
    try:
        user_id = int(message.text.strip())
        ban_user(user_id)
        msg = await message.answer(f"✅ Пользователь {user_id} забанен!")
        await save_message(msg)
        
        try:
            await bot.send_message(user_id, "🚫 Вы были забанены администратором.")
        except:
            pass
    except:
        msg = await message.answer("❌ Ошибка! Введите корректный ID.")
        await save_message(msg)
    
    await state.clear()

@dp.callback_query(F.data == "admin_unban")
async def admin_unban(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in [ADMIN_CHAT_ID]:
        await callback.answer("⛔ Нет доступа")
        return
    
    await state.set_state(FeedbackStates.waiting_for_unban_user)
    msg = await callback.message.edit_text(
        "✅ **Введите ID пользователя для разбана**\n\n"
        "Пример: `123456789`",
        reply_markup=back_to_main_btn(),
        parse_mode="Markdown"
    )
    await save_message(msg)
    await callback.answer()

@dp.message(FeedbackStates.waiting_for_unban_user)
async def process_unban(message: Message, state: FSMContext):
    if message.from_user.id not in [ADMIN_CHAT_ID]:
        return
    
    try:
        user_id = int(message.text.strip())
        unban_user(user_id)
        msg = await message.answer(f"✅ Пользователь {user_id} разбанен!")
        await save_message(msg)
        
        try:
            await bot.send_message(user_id, "✅ Вы были разбанены администратором.")
        except:
            pass
    except:
        msg = await message.answer("❌ Ошибка! Введите корректный ID.")
        await save_message(msg)
    
    await state.clear()

@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in [ADMIN_CHAT_ID]:
        await callback.answer("⛔ Нет доступа")
        return
    
    await state.set_state(FeedbackStates.waiting_for_broadcast)
    msg = await callback.message.edit_text(
        "📢 **Введите текст для рассылки**\n\n"
        "Сообщение будет отправлено ВСЕМ пользователям.",
        reply_markup=back_to_main_btn(),
        parse_mode="Markdown"
    )
    await save_message(msg)
    await callback.answer()

@dp.message(FeedbackStates.waiting_for_broadcast)
async def process_broadcast(message: Message, state: FSMContext):
    if message.from_user.id not in [ADMIN_CHAT_ID]:
        return
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users WHERE is_banned = 0')
    users = cursor.fetchall()
    conn.close()
    
    sent = 0
    for user in users:
        try:
            await bot.send_message(user[0], f"📢 **Рассылка**\n\n{message.text}", parse_mode="Markdown")
            sent += 1
            await asyncio.sleep(0.1)
        except:
            pass
    
    msg = await message.answer(f"✅ Рассылка отправлена {sent} пользователям!")
    await save_message(msg)
    await state.clear()

# ============= FAQ =============
@dp.callback_query(F.data == "faq")
async def show_faq(callback: CallbackQuery):
    await delete_old_messages(callback.from_user.id)
    
    faq_text = (
        "❓ **Частые вопросы**\n\n"
        "1️⃣ **Как задать вопрос?**\n"
        "Нажми 'Написать администратору' и отправь сообщение.\n\n"
        "2️⃣ **Когда придет ответ?**\n"
        "Администраторы ответят в ближайшее время.\n\n"
        "3️⃣ **Как узнать статус?**\n"
        "Ты получишь уведомление, когда админ ответит.\n\n"
        "4️⃣ **Я забанен, что делать?**\n"
        "Свяжись с администратором другим способом."
    )
    
    msg = await callback.message.edit_text(faq_text, reply_markup=back_to_main_btn(), parse_mode="Markdown")
    await save_message(msg)
    await callback.answer()

@dp.callback_query(F.data == "info")
async def show_info(callback: CallbackQuery):
    await delete_old_messages(callback.from_user.id)
    
    info_text = (
        "📖 **Информация**\n\n"
        "🤖 Этот бот создан для обратной связи.\n"
        "📩 Все сообщения передаются администраторам.\n"
        "⏳ Ответ придет в ближайшее время.\n\n"
        "👨‍💻 Версия: 1.0\n"
        "📅 Дата: 2024"
    )
    
    msg = await callback.message.edit_text(info_text, reply_markup=back_to_main_btn(), parse_mode="Markdown")
    await save_message(msg)
    await callback.answer()

# ============= ОБРАБОТКА ОТВЕТОВ АДМИНА =============
@dp.message(F.chat.id == ADMIN_CHAT_ID)
async def admin_reply_to_user(message: Message):
    # Проверяем, что это ответ на сообщение
    if not message.reply_to_message:
        await message.reply("ℹ️ Нажми 'Ответить' на сообщении пользователя, чтобы ответить ему.")
        return
    
    # Извлекаем ID пользователя из текста пересланного сообщения
    reply_text = message.reply_to_message.text or message.reply_to_message.caption or ""
    
    # Ищем ID пользователя в формате "ID: 123456789"
    import re
    match = re.search(r"ID:\s*`?(\d+)`?", reply_text)
    
    if not match:
        await message.reply("❌ Не удалось найти ID пользователя в сообщении.")
        return
    
    user_id = int(match.group(1))
    
    try:
        # Отправляем ответ пользователю
        await bot.send_message(
            user_id,
            f"📩 **Ответ администратора**\n\n{message.text}",
            parse_mode="Markdown"
        )
        await message.reply(f"✅ Ответ отправлен пользователю {user_id}")
    except Exception as e:
        await message.reply(f"❌ Ошибка: {str(e)}")

# ============= ЗАПУСК =============
async def main():
    init_db()
    print("🤖 Бот запущен!")
    print(f"📊 Админ-чат ID: {ADMIN_CHAT_ID}")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
