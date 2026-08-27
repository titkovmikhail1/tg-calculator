"""Telegram-бот с Web App-калькулятором."""

import asyncio
import json
import logging
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import ChatNotFound
from aiogram.filters import CommandStart
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup, WebAppInfo

from config import BOT_TOKEN, WEBAPP_URL

logging.basicConfig(level=logging.INFO)

router = Router()
CHANNEL_LINE_PATTERN = re.compile(
    r"^(?:(?:https?://)?t\.me/|@)([A-Za-z0-9_]{5,32})/?\s+([0-9]+(?:[.,][0-9]+)?)$",
    re.IGNORECASE,
)


def calculate_price(input_number: Decimal, erid: bool, urgent: bool, gazprom: bool) -> Decimal:
    """Рассчитывает стоимость по общей формуле с математическим округлением."""
    result = input_number / Decimal("0.8") * Decimal("1.4")

    if erid:
        result *= Decimal("1.03")
    if urgent:
        result *= Decimal("1.1")
    result /= Decimal("0.94") if gazprom else Decimal("0.87")

    return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_vat_details(final_price: Decimal, nds_mode: str) -> tuple[Decimal, Decimal]:
    """Возвращает отображаемую стоимость и сумму НДС."""
    if nds_mode == "none":
        return final_price, Decimal("0.00")
    vat = (final_price * Decimal("0.05") / Decimal("1.05")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    displayed_price = final_price if nds_mode == "inside" else (final_price - vat).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return displayed_price, vat


def format_money(value: Decimal) -> str:
    """Форматирует сумму с пробелами между разрядами и двумя знаками."""
    return f"{value:,.2f}".replace(",", " ")


def parse_input_number(value: object) -> Decimal:
    """Проверяет число из Web App и возвращает положительное Decimal."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError("Некорректное число")

    text = str(value).strip().replace(",", ".")
    if not text or len(text) > 100:
        raise ValueError("Некорректное число")

    try:
        number = Decimal(text)
    except InvalidOperation as error:
        raise ValueError("Некорректное число") from error

    if not number.is_finite() or number <= 0:
        raise ValueError("Число должно быть больше нуля")

    # Ограничение защищает от чрезмерных значений и переполнения интерфейса.
    if number > Decimal("1e100"):
        raise ValueError("Число слишком большое")

    return number


def parse_boolean(value: object, field_name: str) -> bool:
    """Строго проверяет булевы флаги из Web App."""
    if not isinstance(value, bool):
        raise ValueError(f"Некорректное значение поля «{field_name}»")
    return value


def parse_nds_mode(payload: dict) -> str:
    """Проверяет новый режим НДС и поддерживает старый boolean-формат."""
    nds_mode = payload.get("nds_mode")
    if nds_mode is None:
        nds_mode = "inside" if parse_boolean(payload.get("nds"), "НДС") else "outside"
    if nds_mode not in ("inside", "outside", "none"):
        raise ValueError("Некорректный режим НДС")
    return nds_mode


def parse_channel_line(line: str) -> tuple[str, Decimal]:
    """Извлекает username и стоимость из строки массового расчёта."""
    match = CHANNEL_LINE_PATTERN.fullmatch(line.strip())
    if not match:
        raise ValueError("Неверный формат строки")
    return match.group(1), parse_input_number(match.group(2))


def escape_markdown(value: str) -> str:
    """Экранирует символы Markdown в названии канала."""
    return re.sub(r"([\\_*`\[\]])", r"\\\1", value)


async def send_long_message(message: Message, text: str) -> None:
    """Отправляет текст частями, не превышая лимит Telegram."""
    chunks: list[str] = []
    current = ""
    for line in text.splitlines():
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) <= 4000:
            current = candidate
        else:
            if current:
                chunks.append(current)
            while len(line) > 4000:
                chunks.append(line[:4000])
                line = line[4000:]
            current = line
    if current:
        chunks.append(current)

    for chunk in chunks:
        await message.answer(chunk, parse_mode="Markdown")


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    """Показывает кнопку открытия калькулятора."""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="Открыть калькулятор",
                    web_app=WebAppInfo(url=WEBAPP_URL),
                )
            ]
        ],
        resize_keyboard=True,
    )
    await message.answer(
        "Здравствуйте! Откройте калькулятор, чтобы рассчитать стоимость.",
        reply_markup=keyboard,
    )


@router.message(F.web_app_data)
async def handle_web_app_data(message: Message, bot: Bot) -> None:
    """Проверяет данные Web App и отправляет результат в чат."""
    try:
        payload = json.loads(message.web_app_data.data)
        if not isinstance(payload, dict):
            raise ValueError("Ожидался JSON-объект")

        mode = payload.get("mode", "single")
        if mode not in ("single", "bulk"):
            raise ValueError("Некорректный режим расчёта")
        erid = parse_boolean(payload.get("erid"), "ЕРИД")
        urgent = parse_boolean(payload.get("urgent"), "Срочно")
        gazprom = parse_boolean(payload.get("gazprom"), "Газпром")
        nds_mode = parse_nds_mode(payload)
    except (json.JSONDecodeError, TypeError, ValueError, InvalidOperation) as error:
        logging.warning("Отклонены данные Web App: %s", error)
        await message.answer("Не удалось проверить данные калькулятора. Попробуйте ещё раз.")
        return

    if mode == "bulk":
        bulk_text = payload.get("bulk_text")
        if not isinstance(bulk_text, str) or not bulk_text.strip():
            await message.answer("Список каналов пуст. Добавьте хотя бы одну строку.")
            return

        output_lines = []
        for raw_line in bulk_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                username, input_number = parse_channel_line(line)
                chat = await bot.get_chat(chat_id=f"@{username}")
                title = chat.title or username
            except ChatNotFound:
                username_match = CHANNEL_LINE_PATTERN.fullmatch(line)
                if not username_match:
                    output_lines.append(f"⚠️ Не удалось распознать: {line}")
                    continue
                username = username_match.group(1)
                title = f"{username} (название недоступно)"
                input_number = parse_input_number(username_match.group(2))
            except (TypeError, ValueError, InvalidOperation):
                output_lines.append(f"⚠️ Не удалось распознать: {line}")
                continue

            final_price = calculate_price(input_number, erid, urgent, gazprom)
            displayed_price, vat = calculate_vat_details(final_price, nds_mode)
            channel = f"[{escape_markdown(title)}](https://t.me/{username})"
            if nds_mode == "inside":
                details = (
                    f"{format_money(displayed_price)} руб., "
                    f"в том числе НДС (НДС {format_money(vat)} руб.)"
                )
            elif nds_mode == "outside":
                details = (
                    f"{format_money(displayed_price)} руб. + НДС "
                    f"{format_money(vat)} руб. = {format_money(final_price)} руб."
                )
            else:
                details = f"{format_money(displayed_price)} руб."
            output_lines.append(f"{channel} ({details})")

        if not output_lines:
            await message.answer("В списке нет непустых строк для расчёта.")
            return
        await send_long_message(message, "\n".join(output_lines))
        return

    try:
        input_number = parse_input_number(payload.get("input_number"))
        final_price = calculate_price(input_number, erid, urgent, gazprom)
        displayed_price, vat = calculate_vat_details(final_price, nds_mode)
    except (TypeError, ValueError, InvalidOperation) as error:
        logging.warning("Отклонены данные одиночного расчёта: %s", error)
        await message.answer("Не удалось проверить данные калькулятора. Попробуйте ещё раз.")
        return

    if nds_mode == "inside":
        response = (
            f"Итого: {format_money(displayed_price)} руб.\n"
            f"в том числе НДС (НДС {format_money(vat)} руб.)"
        )
    elif nds_mode == "outside":
        response = (
            f"Стоимость без НДС: {format_money(displayed_price)} руб.\n"
            f"+ НДС {format_money(vat)} руб. = {format_money(final_price)} руб."
        )
    else:
        response = f"Итого: {format_money(displayed_price)} руб.\nНДС не начисляется"
    await message.answer(response)


async def main() -> None:
    """Запускает бота в режиме long polling."""
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        raise RuntimeError("Укажите BOT_TOKEN в config.py")

    bot = Bot(token=BOT_TOKEN)
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен")
