import os
import re
import logging
from zoneinfo import ZoneInfo
from datetime import time, datetime

import requests as _requests

from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from dotenv import load_dotenv

import ai
from data import WOMAN_KEYWORDS, FEMALE_NAMES, COMPANIES, DICK_KEYWORDS, ANIMAL_KEYWORDS
from responses import get_woman_response, get_name_response, get_company_response, get_dick_response, get_animal_response, get_howto_response, get_sanya_response, get_night_response, get_weekday_response, get_proverb, get_german_phrase, get_brag_response, get_pickup_response

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
CHAT_ID = os.getenv("CHAT_ID")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Граница слова для кириллицы и латиницы
_BOUND = r"(?<![а-яёА-ЯЁa-zA-Z0-9.])"
_BOUND_END = r"(?![а-яёА-ЯЁa-zA-Z0-9])"


def get_moscow_time() -> str:
    """Возвращает текущее время в Москве в формате ЧЧ:ММ."""
    now = datetime.now(ZoneInfo("Europe/Moscow"))
    return now.strftime("%H:%M")


def get_vietnam_time() -> str:
    """Возвращает текущее время во Вьетнаме (Нячанг) в формате ЧЧ:ММ."""
    now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    return now.strftime("%H:%M")


def _fetch_temp(lat: float, lon: float, tz: str) -> str | None:
    try:
        r = _requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m",
                "timezone": tz,
            },
            timeout=5,
        )
        r.raise_for_status()
        temp = r.json()["current"]["temperature_2m"]
        return f"{temp:+.0f}"
    except Exception:
        return None


def get_moscow_weather() -> str | None:
    """Возвращает температуру в Москве через Open-Meteo (без ключа)."""
    return _fetch_temp(55.7558, 37.6176, "Europe/Moscow")


def get_vietnam_weather() -> str | None:
    """Возвращает температуру в Нячанге через Open-Meteo (без ключа)."""
    return _fetch_temp(12.2388, 109.1967, "Asia/Ho_Chi_Minh")


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

TIME_PATTERN = re.compile(
    r'котор[ыой][йе]?\s+час|сколько\s+времени|какое\s+время|который\s+час|время\s+сейчас|сейчас\s+времен',
    re.IGNORECASE | re.UNICODE
)
WEATHER_PATTERN = re.compile(
    r'погод[аеуы]|температур[аеуы]|как\s+на\s+улице|холодно|тепло\s+на\s+улице|что\s+на\s+улице',
    re.IGNORECASE | re.UNICODE
)

HOWTO_PATTERN = re.compile(r'расскажи[,.]?\s+как\s+(.+)', re.IGNORECASE | re.UNICODE)
PROVERB_PATTERN = re.compile(r'поговорк[уиаё]|поговорки', re.IGNORECASE | re.UNICODE)
GERMAN_PATTERN = re.compile(r'немецк|по-немецки|deutsch|скажи.{0,20}немец|немец.{0,20}скажи', re.IGNORECASE | re.UNICODE)
BRAG_PATTERN = re.compile(r'качок|телосложен|мышц|спортсмен|феррари|парашют|лошад|тело\b|форма\b|физическ|качаешься|занимаешься спортом', re.IGNORECASE | re.UNICODE)
SANYA_PATTERN = re.compile(
    r'(?<![а-яёА-ЯЁa-zA-Z])'
    r'(?:саня|сань|сане|саней|саню|саней|санёк|санек|санчос|санчес|санчез|санюха|санюша|санёчек|санечек|саныч|сантос|сандро|сантик|санчик|санёша|санюшка|степанов|саш)'
    r'(?![а-яёА-ЯЁa-zA-Z])',
    re.IGNORECASE | re.UNICODE
)
THANKS_PATTERN = re.compile(r'спасибо|благодарю|спс|thank', re.IGNORECASE | re.UNICODE)
RIDDLE_PATTERN = re.compile(r'загадк[уиаё]|загадай|отгадай|угадай|загадывай|давай загадку|ещё загадку|следующ.{0,10}загадк', re.IGNORECASE | re.UNICODE)
RIDDLE_ANSWER_PATTERN = re.compile(r'отвечаю|мой ответ|это\s+\w+\??\s*$|ответ\s*[:—]?\s*\w|я думаю это|наверное\s+\w+\?', re.IGNORECASE | re.UNICODE)
PICKUP_PATTERN = re.compile(r'пикап|как познакомиться|как подойти|как снять|совет.{0,15}девушк|девушк.{0,15}совет|как клеить', re.IGNORECASE | re.UNICODE)
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
    if PROVERB_PATTERN.search(text):
        return get_proverb()
    if GERMAN_PATTERN.search(text):
        return get_german_phrase()
    if BRAG_PATTERN.search(text):
        return get_brag_response()
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
        PROVERB_PATTERN.search(text),
        GERMAN_PATTERN.search(text),
        BRAG_PATTERN.search(text),
        SANYA_PATTERN.search(text),
        THANKS_PATTERN.search(text),
        PICKUP_PATTERN.search(text),
        ANIMAL_PATTERN.search(text),
        DICK_PATTERN.search(text),
        WOMAN_PATTERN.search(text),
        NAMES_PATTERN.search(text),
        COMPANIES_PATTERN.search(text),
        TIME_PATTERN.search(text),
        WEATHER_PATTERN.search(text),
        RIDDLE_PATTERN.search(text),
        RIDDLE_ANSWER_PATTERN.search(text),
    ])

    # Проверяем — ответили ли на сообщение Сани
    reply_to = update.message.reply_to_message
    is_reply_to_bot = (
        reply_to is not None
        and reply_to.from_user is not None
        and reply_to.from_user.is_bot
        and reply_to.from_user.id == context.bot.id
    )

    # В групповом чате отвечаем только если есть триггер или ответили на сообщение Сани
    is_group = update.message.chat.type in ("group", "supergroup")
    if is_group and not has_trigger and not is_reply_to_bot:
        return

    # Пробуем AI
    if GROQ_API_KEY or MISTRAL_API_KEY:
        extra_context = None
        if TIME_PATTERN.search(text):
            msk_time = get_moscow_time()
            vn_time = get_vietnam_time()
            extra_context = (
                f"[реальное время: Москва {msk_time}, Нячанг (Вьетнам) {vn_time}. "
                f"обязательно упомяни оба города. про нячангское время скажи что это специально для Влада который сейчас в Нячанге "
                f"и пожелай ему потрахаться с местными там]"
            )
        elif WEATHER_PATTERN.search(text):
            msk_temp = get_moscow_weather()
            vn_temp = get_vietnam_weather()
            parts = []
            if msk_temp:
                parts.append(f"Москва {msk_temp}°C")
            if vn_temp:
                parts.append(f"Нячанг {vn_temp}°C")
            if parts:
                extra_context = (
                    f"[реальная температура: {', '.join(parts)}. "
                    f"обязательно упомяни оба города. про нячангскую погоду скажи что это специально для Влада который сейчас в Нячанге "
                    f"и пожелай ему потрахаться с местными там]"
                )
        elif is_reply_to_bot:
            extra_context = "[тебе отвечают на твоё предыдущее сообщение — продолжай разговор, добавь деталь или историю, не повторяй слово собеседника]"
        reply = ai.get_response(chat_id, text, username, extra_context=extra_context)
        if reply:
            await update.message.reply_text(reply)
            return
        else:
            logger.warning(f"AI вернул None для: {text!r}")

    # Запасной вариант — статичные ответы
    reply = fallback_response(text)
    if reply:
        await update.message.reply_text(reply)


async def chatid_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"Chat ID: `{update.message.chat_id}`", parse_mode="Markdown")


async def send_night_message(context: ContextTypes.DEFAULT_TYPE) -> None:
    if not CHAT_ID:
        return
    from datetime import datetime
    from zoneinfo import ZoneInfo
    weekday = datetime.now(ZoneInfo("Europe/Moscow")).weekday()  # 0=пн, 6=вс
    if weekday < 4:  # пн-чт
        msg = get_weekday_response()
    else:  # пт-вс
        msg = get_night_response()
    await context.bot.send_message(chat_id=int(CHAT_ID), text=msg)


def main() -> None:
    if not TOKEN:
        raise ValueError("Задай BOT_TOKEN в файле .env!")

    if MISTRAL_API_KEY or GROQ_API_KEY:
        ai.init(groq_api_key=GROQ_API_KEY, mistral_api_key=MISTRAL_API_KEY)
    else:
        print("AI ключи не заданы — работаю в статичном режиме")

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("chatid", chatid_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Ночное сообщение каждый день в 00:05 по Москве
    if CHAT_ID and app.job_queue:
        msk = ZoneInfo("Europe/Moscow")
        app.job_queue.run_daily(
            send_night_message,
            time=time(22, 0, tzinfo=msk),
        )
        print(f"Сообщения настроены → чат {CHAT_ID} в 22:00 МСК")

    print("Саня Степанов запущен. Ctrl+C чтобы остановить.")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
