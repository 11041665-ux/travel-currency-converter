
import os
import time
import logging
from decimal import Decimal, InvalidOperation

import requests
from dotenv import load_dotenv


load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
WEATHER_CITY = os.getenv("WEATHER_CITY", "Kropyvnytskyi")
EXCHANGE_RATE_API_KEY = os.getenv("EXCHANGE_RATE_API_KEY", "").strip()

TELEGRAM_API_URL = (
    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
)

WEATHER_API_URL = "https://api.openweathermap.org/data/2.5/weather"

EXCHANGE_API_URL = "https://open.er-api.com/v6/latest"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)


def get_weather(city=None):
    """Отримує погоду для вказаного міста."""
    city = city or WEATHER_CITY

    if not WEATHER_API_KEY:
        raise RuntimeError(
            "Не вказано WEATHER_API_KEY у файлі .env."
        )

    response = requests.get(
        WEATHER_API_URL,
        params={
            "q": city,
            "appid": WEATHER_API_KEY,
            "units": "metric",
            "lang": "uk",
        },
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()

    if str(data.get("cod")) != "200":
        raise ValueError(
            data.get("message", "Не вдалося отримати погоду.")
        )

    description = data["weather"][0]["description"]
    temperature = data["main"]["temp"]
    feels_like = data["main"]["feels_like"]
    humidity = data["main"]["humidity"]
    wind_speed = data["wind"]["speed"]
    city_name = data["name"]

    return (
        f"🌤 Погода: {city_name}\n"
        f"Опис: {description.capitalize()}\n"
        f"Температура: {temperature} °C\n"
        f"Відчувається як: {feels_like} °C\n"
        f"Вологість: {humidity}%\n"
        f"Швидкість вітру: {wind_speed} м/с"
    )


def get_exchange_rates(base_currency):
    """Отримує курси валют відносно базової валюти."""
    base_currency = base_currency.upper()

    if not (
        len(base_currency) == 3
        and base_currency.isalpha()
    ):
        raise ValueError(
            "Код валюти має складатися з трьох літер, наприклад USD."
        )

    if EXCHANGE_RATE_API_KEY:
        url = (
            "https://v6.exchangerate-api.com/v6/"
            f"{EXCHANGE_RATE_API_KEY}/latest/{base_currency}"
        )
    else:
        url = f"{EXCHANGE_API_URL}/{base_currency}"

    response = requests.get(url, timeout=15)
    response.raise_for_status()
    data = response.json()

    if data.get("result") != "success":
        error = data.get("error-type", "невідома помилка")
        raise ValueError(
            f"Не вдалося отримати курс валют: {error}"
        )

    rates = data.get("conversion_rates")

    if not rates:
        raise ValueError("API не повернуло курси валют.")

    return rates, data.get("time_last_update_utc")


def convert_currency(amount_text, from_currency, to_currency):
    """Конвертує суму з однієї валюти в іншу."""
    try:
        amount = Decimal(amount_text.replace(",", "."))
    except InvalidOperation:
        raise ValueError("Введи коректну суму, наприклад 100 або 12.50.")

    if not amount.is_finite() or amount <= 0:
        raise ValueError("Сума має бути більшою за нуль.")

    from_currency = from_currency.upper()
    to_currency = to_currency.upper()

    rates, updated_at = get_exchange_rates(from_currency)

    if to_currency not in rates:
        raise ValueError(
            f"Валюта {to_currency} не знайдена. "
            "Перевір код валюти, наприклад EUR, USD або UAH."
        )

    rate = Decimal(str(rates[to_currency]))
    result = amount * rate

    return (
        f"💱 Конвертація валют\n"
        f"{amount:,.2f} {from_currency} = "
        f"{result:,.2f} {to_currency}\n"
        f"Курс: 1 {from_currency} = {rate} {to_currency}\n"
        f"Оновлення курсу: {updated_at or 'не вказано'}\n\n"
        "Примітка: це довідковий курс API; "
        "курс банку або обмінника може відрізнятися."
    )


def send_message(chat_id, text):
    """Надсилає повідомлення користувачу в Telegram."""
    response = requests.post(
        f"{TELEGRAM_API_URL}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text,
        },
        timeout=15,
    )
    response.raise_for_status()

    result = response.json()
    if not result.get("ok"):
        raise RuntimeError("Telegram не зміг надіслати повідомлення.")


def process_message(message):
    """Обробляє команду користувача."""
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()

    if not text:
        return

    command, _, args = text.partition(" ")
    command = command.split("@")[0].lower()
    args = args.strip()

    if command == "/start":
        reply = (
            "Привіт! Я Travel Weather Planner 🌍\n\n"
            "Я допоможу дізнатися погоду та конвертувати валюту.\n\n"
            "Команди:\n"
            "/weather — погода у налаштованому місті\n"
            "/weather London — погода в іншому місті\n"
            "/convert 100 EUR UAH — конвертація валют\n"
            "/rates USD — курси валют відносно USD\n"
            "/help — інструкція"
        )
        send_message(chat_id, reply)

    elif command == "/help":
        send_message(
            chat_id,
            "Приклади використання:\n"
            "/weather\n"
            "/weather London\n"
            "/convert 100 EUR UAH\n"
            "/convert 50 USD EUR\n"
            "/rates USD\n"
            "/rates EUR"
        )

    elif command == "/weather":
        try:
            reply = get_weather(args or WEATHER_CITY)
        except (ValueError, RuntimeError) as error:
            reply = f"Не вдалося отримати погоду: {error}"
        except requests.exceptions.RequestException:
            logging.exception("Помилка запиту погоди")
            reply = "Помилка з'єднання з сервісом погоди. Спробуй пізніше."

        send_message(chat_id, reply)

    elif command == "/convert":
        parts = args.split()

        if len(parts) != 3:
            send_message(
                chat_id,
                "Формат команди:\n/convert 100 EUR UAH\n\n"
                "Вкажи суму, початкову та кінцеву валюту."
            )
            return

        amount, from_currency, to_currency = parts

        try:
            reply = convert_currency(
                amount,
                from_currency,
                to_currency,
            )
        except (ValueError, RuntimeError) as error:
            reply = f"Не вдалося конвертувати валюту: {error}"
        except requests.exceptions.RequestException:
            logging.exception("Помилка запиту курсу валют")
            reply = "Не вдалося підключитися до сервісу курсів. Спробуй пізніше."

        send_message(chat_id, reply)

    elif command == "/rates":
        base_currency = args.upper() if args else "USD"

        try:
            rates, updated_at = get_exchange_rates(base_currency)

            preferred_currencies = ["UAH", "EUR", "USD", "GBP", "PLN", "CZK"]
            lines = [
                f"💱 Курси відносно {base_currency}:",
                f"Оновлення: {updated_at or 'не вказано'}",
                "",
            ]

            for currency in preferred_currencies:
                if currency != base_currency and currency in rates:
                    lines.append(
                        f"1 {base_currency} = "
                        f"{rates[currency]} {currency}"
                    )

            reply = "\n".join(lines)

        except (ValueError, RuntimeError) as error:
            reply = f"Не вдалося отримати курси: {error}"
        except requests.exceptions.RequestException:
            logging.exception("Помилка запиту курсів")
            reply = "Помилка з'єднання з сервісом курсів. Спробуй пізніше."

        send_message(chat_id, reply)

    else:
        send_message(
            chat_id,
            "Не знаю такої команди. Напиши /help, щоб побачити список."
        )


def main():
    """Запускає бота та отримує нові повідомлення."""
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "Не вказано TELEGRAM_BOT_TOKEN у файлі .env."
        )

    logging.info("Travel Weather Planner запущено.")

    offset = None

    while True:
        try:
            response = requests.get(
                f"{TELEGRAM_API_URL}/getUpdates",
                params={
                    "timeout": 30,
                    "offset": offset,
                },
                timeout=35,
            )
            response.raise_for_status()
            data = response.json()

            if not data.get("ok"):
                raise RuntimeError("Telegram API повернуло помилку.")

            for update in data.get("result", []):
                offset = update["update_id"] + 1

                message = update.get("message")
                if not message:
                    continue

                try:
                    process_message(message)
                except Exception:
                    logging.exception("Помилка обробки повідомлення")

        except requests.exceptions.RequestException:
            logging.exception("Помилка з'єднання з Telegram. Повтор через 5 секунд.")
            time.sleep(5)
        except RuntimeError:
            logging.exception("Помилка Telegram API. Повтор через 5 секунд.")
            time.sleep(5)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        logging.error(error)