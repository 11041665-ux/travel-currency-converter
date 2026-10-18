import os
import time

import requests
from dotenv import load_dotenv


# Завантажуємо змінні з файлу .env
load_dotenv()

WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEATHER_CITY = os.getenv("WEATHER_CITY", "Kropyvnytskyi")

WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
TELEGRAM_URL = (
    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
    if TELEGRAM_BOT_TOKEN
    else None
)


def get_weather(city):
    """Отримує погоду для вказаного міста."""
    if not WEATHER_API_KEY:
        raise ValueError("Не задано WEATHER_API_KEY у файлі .env")

    try:
        response = requests.get(
            WEATHER_URL,
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

        return (
            f"🌍 Погода у місті {data['name']}\n"
            f"🌡 Температура: {data['main']['temp']} °C\n"
            f"🤗 Відчувається як: "
            f"{data['main']['feels_like']} °C\n"
            f"☁️ Умови: {data['weather'][0]['description']}\n"
            f"💧 Вологість: {data['main']['humidity']}%\n"
            f"💨 Швидкість вітру: {data['wind']['speed']} м/с"
        )

    except requests.exceptions.HTTPError as error:
        status = error.response.status_code

        if status == 401:
            raise RuntimeError(
                "OpenWeatherMap відхилив API-ключ. Перевір його."
            ) from error
        elif status == 404:
            raise RuntimeError(
                "Місто не знайдено. Перевір назву."
            ) from error
        elif status == 429:
            raise RuntimeError(
                "Перевищено ліміт запитів до погодного API."
            ) from error
        else:
            raise RuntimeError(
                f"Помилка погодного API: HTTP {status}"
            ) from error

    except requests.exceptions.Timeout as error:
        raise RuntimeError(
            "Сервіс погоди не відповідає вчасно."
        ) from error

    except requests.exceptions.RequestException as error:
        raise RuntimeError(
            "Не вдалося з'єднатися з сервісом погоди."
        ) from error

    except (KeyError, IndexError, ValueError) as error:
        raise RuntimeError(
            "Не вдалося обробити відповідь погодного API."
        ) from error


def send_message(chat_id, text):
    """Надсилає повідомлення користувачу в Telegram."""
    if not TELEGRAM_URL:
        raise ValueError("Не задано TELEGRAM_BOT_TOKEN у файлі .env")

    response = requests.post(
        f"{TELEGRAM_URL}/sendMessage",
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
    """Обробляє повідомлення користувача."""
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()

    if text.startswith("/start"):
        reply = (
            "Привіт! 👋 Я Travel Weather Planner.\n\n"
            "Я допоможу дізнатися погоду перед подорожжю.\n"
            "Надішли /weather, щоб отримати погоду "
            f"у місті {WEATHER_CITY}."
        )
        send_message(chat_id, reply)

    elif text.startswith("/weather"):
        try:
            weather = get_weather(WEATHER_CITY)
            send_message(chat_id, weather)
            print(f"Погоду для {WEATHER_CITY} надіслано.")

        except (RuntimeError, ValueError) as error:
            print(f"Помилка погоди: {error}")
            send_message(
                chat_id,
                f"Не вдалося отримати погоду.\nПричина: {error}",
            )

        except requests.exceptions.RequestException as error:
            print(f"Помилка Telegram API: {error}")

    elif text:
        send_message(
            chat_id,
            "Поки що я розумію команди /start і /weather.",
        )


def main():
    """Запускає бота та перевіряє нові повідомлення."""
    if not TELEGRAM_BOT_TOKEN or not WEATHER_API_KEY:
        print(
            "Помилка: перевір WEATHER_API_KEY і "
            "TELEGRAM_BOT_TOKEN у файлі .env"
        )
        return

    print("Travel Weather Planner запускається...")

    # Перевіряємо токен Telegram перед запуском.
    try:
        response = requests.get(
            f"{TELEGRAM_URL}/getMe",
            timeout=15,
        )
        response.raise_for_status()
        bot_data = response.json()

        if not bot_data.get("ok"):
            print("Telegram не підтвердив токен бота.")
            return

        print(f"Бот @{bot_data['result']['username']} запущений.")

    except (requests.exceptions.RequestException, ValueError) as error:
        print(f"Не вдалося підключитися до Telegram: {error}")
        return

    offset = None

    while True:
        try:
            response = requests.get(
                f"{TELEGRAM_URL}/getUpdates",
                params={
                    "offset": offset,
                    "timeout": 25,
                },
                timeout=35,
            )
            response.raise_for_status()
            result = response.json()

            if not result.get("ok"):
                print("Telegram повернув помилку отримання повідомлень.")
                time.sleep(3)
                continue

            for update in result["result"]:
                offset = update["update_id"] + 1
                message = update.get("message")

                if message and message.get("text"):
                    try:
                        process_message(message)
                    except (
                        requests.exceptions.RequestException,
                        RuntimeError,
                        ValueError,
                    ) as error:
                        print(f"Не вдалося обробити повідомлення: {error}")

        except requests.exceptions.Timeout:
            # Long polling може завершуватися за тайм-аутом.
            continue

        except requests.exceptions.RequestException as error:
            print(f"Помилка мережі: {error}")
            time.sleep(3)


if __name__ == "__main__":
    main()