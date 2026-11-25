"""Customer-facing bot commands: /start, /help (contact the shop admin) and /settings.

Each customer has their own settings: language, phone, delivery address, notifications.
"""
import sqlite3

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    WebAppInfo,
)

LANGS = {"en": "🇬🇧 English", "ru": "🇷🇺 Русский", "uz": "🇺🇿 O'zbekcha"}

TEXTS = {
    "start": {
        "en": "Hi, {name}! 👋 Tap the button below to open the shop.",
        "ru": "Привет, {name}! 👋 Нажмите кнопку ниже, чтобы открыть магазин.",
        "uz": "Salom, {name}! 👋 Do'konni ochish uchun quyidagi tugmani bosing.",
    },
    "open_app": {"en": "🛍 Open shop", "ru": "🛍 Открыть магазин", "uz": "🛍 Do'konni ochish"},
    "help": {
        "en": "Need help with an order or have a question?\nTap the button to write to the shop admin.",
        "ru": "Нужна помощь с заказом или есть вопрос?\nНажмите кнопку, чтобы написать администратору магазина.",
        "uz": "Buyurtma bo'yicha yordam kerakmi yoki savolingiz bormi?\nDo'kon administratoriga yozish uchun tugmani bosing.",
    },
    "contact_admin": {"en": "💬 Message the admin", "ru": "💬 Написать администратору", "uz": "💬 Administratorga yozish"},
    "no_admin": {
        "en": "Sorry, the admin contact isn't set up yet.",
        "ru": "Извините, контакт администратора ещё не настроен.",
        "uz": "Kechirasiz, administrator kontakti hali sozlanmagan.",
    },
    "settings": {
        "en": "⚙️ <b>Your settings</b>\n\n🌐 Language: {lang}\n📞 Phone: {phone}\n📍 Address: {address}\n🔔 Notifications: {notify}",
        "ru": "⚙️ <b>Ваши настройки</b>\n\n🌐 Язык: {lang}\n📞 Телефон: {phone}\n📍 Адрес: {address}\n🔔 Уведомления: {notify}",
        "uz": "⚙️ <b>Sozlamalaringiz</b>\n\n🌐 Til: {lang}\n📞 Telefon: {phone}\n📍 Manzil: {address}\n🔔 Bildirishnomalar: {notify}",
    },
    "not_set": {"en": "not set", "ru": "не указан", "uz": "kiritilmagan"},
    "on": {"en": "on ✅", "ru": "вкл ✅", "uz": "yoqilgan ✅"},
    "off": {"en": "off ❌", "ru": "выкл ❌", "uz": "o'chirilgan ❌"},
    "btn_lang": {"en": "🌐 Language", "ru": "🌐 Язык", "uz": "🌐 Til"},
    "btn_phone": {"en": "📞 Phone", "ru": "📞 Телефон", "uz": "📞 Telefon"},
    "btn_address": {"en": "📍 Address", "ru": "📍 Адрес", "uz": "📍 Manzil"},
    "btn_notify": {"en": "🔔 Notifications", "ru": "🔔 Уведомления", "uz": "🔔 Bildirishnomalar"},
    "choose_lang": {"en": "Choose your language:", "ru": "Выберите язык:", "uz": "Tilni tanlang:"},
    "ask_phone": {
        "en": "Tap the button below to share your phone number.",
        "ru": "Нажмите кнопку ниже, чтобы отправить номер телефона.",
        "uz": "Telefon raqamingizni yuborish uchun quyidagi tugmani bosing.",
    },
    "share_phone": {"en": "📱 Share my number", "ru": "📱 Отправить номер", "uz": "📱 Raqamni yuborish"},
    "ask_address": {
        "en": "Type your delivery address (street, house, apartment):",
        "ru": "Напишите адрес доставки (улица, дом, квартира):",
        "uz": "Yetkazib berish manzilini yozing (ko'cha, uy, xonadon):",
    },
    "saved": {"en": "✅ Saved!", "ru": "✅ Сохранено!", "uz": "✅ Saqlandi!"},
    "not_your_phone": {
        "en": "Please share your own number using the button.",
        "ru": "Пожалуйста, отправьте свой номер с помощью кнопки.",
        "uz": "Iltimos, tugma orqali o'z raqamingizni yuboring.",
    },
    "cmd_start": {"en": "Open the shop", "ru": "Открыть магазин", "uz": "Do'konni ochish"},
    "cmd_help": {"en": "Contact the shop admin", "ru": "Связаться с администратором", "uz": "Administrator bilan bog'lanish"},
    "cmd_settings": {"en": "My settings", "ru": "Мои настройки", "uz": "Mening sozlamalarim"},
}


class Edit(StatesGroup):
    phone = State()
    address = State()


def bot_commands(lang: str) -> list[BotCommand]:
    """The command list shown in Telegram's menu, in the given language."""
    return [
        BotCommand(command="start", description=TEXTS["cmd_start"][lang]),
        BotCommand(command="help", description=TEXTS["cmd_help"][lang]),
        BotCommand(command="settings", description=TEXTS["cmd_settings"][lang]),
    ]


def setup(db: sqlite3.Connection, webapp_url: str, admin_username: str) -> Router:
    router = Router()
    admin_username = admin_username.lstrip("@")

    db.execute(
        """CREATE TABLE IF NOT EXISTS customers (
            user_id INTEGER PRIMARY KEY,
            lang TEXT,
            phone TEXT,
            address TEXT,
            notify INTEGER NOT NULL DEFAULT 1
        )"""
    )
    db.commit()

    # ------------------------------------------------------------ helpers
    def get_customer(user) -> sqlite3.Row:
        row = db.execute("SELECT * FROM customers WHERE user_id=?", (user.id,)).fetchone()
        if row is None:
            # First visit: guess the language from the user's Telegram app.
            code = (user.language_code or "en")[:2]
            db.execute(
                "INSERT INTO customers (user_id, lang) VALUES (?, ?)",
                (user.id, code if code in LANGS else "en"),
            )
            db.commit()
            row = db.execute("SELECT * FROM customers WHERE user_id=?", (user.id,)).fetchone()
        return row

    def update(user_id: int, **fields):
        sets = ", ".join(f"{k}=?" for k in fields)
        db.execute(f"UPDATE customers SET {sets} WHERE user_id=?", (*fields.values(), user_id))
        db.commit()

    def t(key: str, lng: str, **kw) -> str:
        return TEXTS[key][lng].format(**kw)

    def settings_view(c: sqlite3.Row) -> tuple[str, InlineKeyboardMarkup]:
        lang = c["lang"]
        text = t(
            "settings", lang,
            lang=LANGS[lang],
            phone=c["phone"] or t("not_set", lang),
            address=c["address"] or t("not_set", lang),
            notify=t("on" if c["notify"] else "off", lang),
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t("btn_lang", lang), callback_data="set:lang"),
             InlineKeyboardButton(text=t("btn_notify", lang), callback_data="set:notify")],
            [InlineKeyboardButton(text=t("btn_phone", lang), callback_data="set:phone"),
             InlineKeyboardButton(text=t("btn_address", lang), callback_data="set:address")],
        ])
        return text, kb

    async def show_settings(message: Message, user):
        text, kb = settings_view(get_customer(user))
        await message.answer(text, reply_markup=kb, parse_mode="HTML")

    async def set_user_commands(bot, user_id: int, lang: str):
        from aiogram.types import BotCommandScopeChat
        await bot.set_my_commands(bot_commands(lang), scope=BotCommandScopeChat(chat_id=user_id))

    # ------------------------------------------------------------ /start
    @router.message(CommandStart())
    async def start(message: Message, state: FSMContext):
        await state.clear()
        lang = get_customer(message.from_user)["lang"]
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=t("open_app", lang), web_app=WebAppInfo(url=webapp_url))
        ]])
        await message.answer(t("start", lang, name=message.from_user.first_name), reply_markup=kb)

    # ------------------------------------------------------------ /help
    @router.message(Command("help"))
    async def help_cmd(message: Message, state: FSMContext):
        await state.clear()
        lang = get_customer(message.from_user)["lang"]
        if not admin_username:
            await message.answer(t("no_admin", lang))
            return
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=t("contact_admin", lang), url=f"https://t.me/{admin_username}")
        ]])
        await message.answer(t("help", lang), reply_markup=kb)

    # ------------------------------------------------------------ /settings
    @router.message(Command("settings"))
    async def settings_cmd(message: Message, state: FSMContext):
        await state.clear()
        await show_settings(message, message.from_user)

    @router.callback_query(F.data == "set:notify")
    async def toggle_notify(call: CallbackQuery):
        c = get_customer(call.from_user)
        update(call.from_user.id, notify=0 if c["notify"] else 1)
        text, kb = settings_view(get_customer(call.from_user))
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await call.answer()

    @router.callback_query(F.data == "set:lang")
    async def choose_lang(call: CallbackQuery):
        lang = get_customer(call.from_user)["lang"]
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=name, callback_data=f"lang:{code}")] for code, name in LANGS.items()
        ])
        await call.message.edit_text(t("choose_lang", lang), reply_markup=kb)
        await call.answer()

    @router.callback_query(F.data.startswith("lang:"))
    async def set_lang(call: CallbackQuery):
        code = call.data.split(":", 1)[1]
        if code in LANGS:
            update(call.from_user.id, lang=code)
            await set_user_commands(call.bot, call.from_user.id, code)
        text, kb = settings_view(get_customer(call.from_user))
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await call.answer(t("saved", get_customer(call.from_user)["lang"]))

    @router.callback_query(F.data == "set:phone")
    async def ask_phone(call: CallbackQuery, state: FSMContext):
        lang = get_customer(call.from_user)["lang"]
        await state.set_state(Edit.phone)
        kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=t("share_phone", lang), request_contact=True)]],
            resize_keyboard=True, one_time_keyboard=True,
        )
        await call.message.answer(t("ask_phone", lang), reply_markup=kb)
        await call.answer()

    @router.message(Edit.phone, F.contact)
    async def got_phone(message: Message, state: FSMContext):
        lang = get_customer(message.from_user)["lang"]
        if message.contact.user_id != message.from_user.id:
            await message.answer(t("not_your_phone", lang))
            return
        phone = message.contact.phone_number
        update(message.from_user.id, phone=phone if phone.startswith("+") else "+" + phone)
        await state.clear()
        await message.answer(t("saved", lang), reply_markup=ReplyKeyboardRemove())
        await show_settings(message, message.from_user)

    @router.message(Edit.phone)
    async def phone_not_contact(message: Message):
        await message.answer(t("ask_phone", get_customer(message.from_user)["lang"]))

    @router.callback_query(F.data == "set:address")
    async def ask_address(call: CallbackQuery, state: FSMContext):
        await state.set_state(Edit.address)
        await call.message.answer(t("ask_address", get_customer(call.from_user)["lang"]))
        await call.answer()

    @router.message(Edit.address, F.text)
    async def got_address(message: Message, state: FSMContext):
        update(message.from_user.id, address=message.text.strip()[:300])
        await state.clear()
        await message.answer(t("saved", get_customer(message.from_user)["lang"]))
        await show_settings(message, message.from_user)

    return router
