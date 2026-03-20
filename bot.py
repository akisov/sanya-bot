import os
import re
import logging
from zoneinfo import ZoneInfo
from datetime import time

from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from dotenv import load_dotenv

import ai
from data import WOMAN_KEYWORDS, FEMALE_NAMES, COMPANIES, DICK_KEYWORDS, ANIMAL_KEYWORDS
from responses import get_woman_response, get_name_response, get_company_response, get_dick_response, get_animal_response, get_howto_response, get_sanya_response, get_night_response

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
CHAT_ID = os.getenv("CHAT_ID")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Граница слова для кириллицы и латиницы
_BOUND = r"(?<![а-яёА-ЯЁa-zA-Z0-9.])"
_BOUND_END = r"(?![а-яёА-ЯЁa-zA-Z0-9])"


def build_pattern(words: list[str]) -> re.Pattern:
    sorted_words = sorted(words, key=len, reverse=True)
    parts = [_BOUND + re.escape(w) + _BOUND_END for w in sorted_words]
    return re.compile("|".join(parts), re.IGNORECASE | re.UNICODE)


def name_stem_pattern(name: str) -> str:
    if name.endswith("ья"):
        stem = re.escape(name[:-2])
        return stem + r"(?:ья|ьи|ье|ью|ьей)"
    elif name.endswith("ия"):
        stem = re.escape(name[:-2])
        return stem + r"(?:ия|ии|ию|ией)"
    elif name.endswith("я"):
        stem = re.escape(name[:-1])
        return stem + r"(?:я|ю|и|е|ей)"
    elif name.endswith("а"):
        stem = re.escape(name[:-1])
        return stem + r"(?:а|у|ы|е|ой|ою)"
    else:
        return re.escape(name)


def build_names_pattern(names: list[str]) -> re.Pattern:
    sorted_names = sorted(names, key=len, reverse=True)
    parts = [_BOUND + name_stem_pattern(w) + _BOUND_END for w in sorted_names]
    return re.compile("|".join(parts), re.IGNORECASE | re.UNICODE)


def _stem(name: str) -> str:
    for suffix in ("ья", "ия", "я", "а"):
        if name.endswith(suffix):
            return name[:-len(suffix)]
    return name


_NAME_STEMS = {_stem(n).lower(): n for n in FEMALE_NAMES}

HOWTO_PATTERN = re.compile(r'расскажи[,.]?\s+как\s+(.+)', re.IGNORECASE | re.UNICODE)
SANYA_PATTERN = re.compile(r'(?<![а-яёА-ЯЁa-zA-Z])саня(?![а-яёА-ЯЁa-zA-Z])', re.IGNORECASE | re.UNICODE)
THANKS_PATTERN = re.compile(r'спасибо|благодарю|спс|thank', re.IGNORECASE | re.UNICODE)
ANIMAL_PATTERN = build_pattern(ANIMAL_KEYWORDS)
DICK_PATTERN = build_pattern(DICK_KEYWORDS)
WOMAN_PATTERN = build_pattern(WOMAN_KEYWORDS)
NAMES_PATTERN = build_names_pattern(FEMALE_NAMES)
COMPANIES_PATTERN = build_pattern(COMPANIES)


def canonical(match_str: str, source_list: list[str]) -> str:
    lo = match_str.lower()
    for item in source_list:
        if item.lower() == lo:
            return item
    return match_str


def canonical_name(match_str: str) -> str:
    lo = match_str.lower()
    for name in FEMALE_NAMES:
        if name.lower() == lo:
            return name
    for suffix in ("ой", "ою", "ей", "ью", "ию", "ье", "ьи", "ия", "ии", "ую", "ю", "ы", "и", "е", "у", "а"):
        if lo.endswith(suffix):
            stem = lo[:-len(suffix)]
            if stem in _NAME_STEMS:
                return _NAME_STEMS[stem]
    return match_str.capitalize()


def fallback_response(text: str) -> str | None:
    """Статичные ответы как запасной вариант если AI недоступен."""
    howto_match = HOWTO_PATTERN.search(text)
    if howto_match:
        return get_howto_response(howto_match.group(1).rstrip("?!. "))
    if SANYA_PATTERN.search(text):
        return get_sanya_response()
    if ANIMAL_PATTERN.search(text):
        return get_animal_response()
    if DICK_PATTERN.search(text):
        return get_dick_response()
    if WOMAN_PATTERN.search(text):
        return get_woman_response()
    name_match = NAMES_PATTERN.search(text)
    if name_match:
        return get_name_response(canonical_name(name_match.group()))
    company_match = COMPANIES_PATTERN.search(text)
    if company_match:
        return get_company_response(canonical(company_match.group(), COMPANIES))
    return None


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    if update.message.from_user and update.message.from_user.is_bot:
        return

    text = update.message.text
    chat_id = update.message.chat_id
    username = update.message.from_user.first_name or ""

    # Определяем — есть ли триггер или обращение к Сане
    has_trigger = any([
        HOWTO_PATTERN.search(text),
        SANYA_PATTERN.search(text),
        THANKS_PATTERN.search(text),
        ANIMAL_PATTERN.search(text),
        DICK_PATTERN.search(text),
        WOMAN_PATTERN.search(text),
        NAMES_PATTERN.search(text),
        COMPANIES_PATTERN.search(text),
    ])

    # В групповом чате отвечаем только если есть триггер или упомянули Саню
    is_group = update.message.chat.type in ("group", "supergroup")
    if is_group and not has_trigger:
        return

    # Пробуем AI
    if GROQ_API_KEY:
        reply = ai.get_response(chat_id, text, username)
        if reply:
            await update.message.reply_text(reply)
            return

    # Запасной вариант — статичные ответы
    reply = fallback_response(text)
    if reply:
        await update.message.reply_text(reply)


async def chatid_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"Chat ID: `{update.message.chat_id}`", parse_mode="Markdown")


async def send_night_message(context: ContextTypes.DEFAULT_TYPE) -> None:
    if not CHAT_ID:
        return
    msg = get_night_response()
    await context.bot.send_message(chat_id=int(CHAT_ID), text=msg)


def main() -> None:
    if not TOKEN:
        raise ValueError("Задай BOT_TOKEN в файле .env!")

    if GROQ_API_KEY:
        ai.init(GROQ_API_KEY)
        print("AI режим включён (Groq)")
    else:
        print("GROQ_API_KEY не задан — работаю в статичном режиме")

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("chatid", chatid_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Ночное сообщение каждый день в 00:05 по Москве
    if CHAT_ID and app.job_queue:
        msk = ZoneInfo("Europe/Moscow")
        app.job_queue.run_daily(
            send_night_message,
            time=time(0, 20, tzinfo=msk),
        )
        print(f"Ночные сообщения настроены → чат {CHAT_ID} в 00:05 МСК")

    print("Саня Степанов запущен. Ctrl+C чтобы остановить.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
