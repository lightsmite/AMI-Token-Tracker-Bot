import requests
import time
import os
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from telegram import Bot
import logging

# === ЗАГРУЗКА .env ===
load_dotenv()

MAX_SUPPLY = 1_000_000_000
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
DATA_URL = os.getenv("DATA_URL")
CMC_API_KEY = os.getenv("CMC_API_KEY")
DELAY = int(os.getenv("DELAY", 10))

# === НАСТРОЙКА ЛОГИРОВАНИЯ ===
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler("log.txt", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

bot = Bot(token=TELEGRAM_TOKEN)

def get_token_supply():
    response = requests.get(DATA_URL)
    response.raise_for_status()
    supply = int(float(response.json()))
    return supply

def send_telegram_message(msg):
    asyncio.run(bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg))

def format_time_delta(seconds):
    mins, secs = divmod(int(seconds), 60)
    hours, mins = divmod(mins, 60)
    if hours:
        return f"{hours}ч {mins}м {secs}с"
    elif mins:
        return f"{mins}м {secs}с"
    else:
        return f"{secs}с"

def get_price_from_cmc():
    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
    params = {
        "symbol": "AMI",
        "convert": "USD"
    }
    headers = {
        "X-CMC_PRO_API_KEY": CMC_API_KEY
    }

    response = requests.get(url, params=params, headers=headers)
    response.raise_for_status()
    data = response.json()
    price = float(data["data"]["AMI"]["quote"]["USD"]["price"])
    return price

def main():
    last_supply = None
    last_update_time = None

    logging.info("🔄 Бот запущен. Ожидаем изменения supply с сайта...")

    while True:
        try:
            current_time = time.time()
            TOKEN_PRICE = get_price_from_cmc()
            current_supply = get_token_supply()

            if last_supply is not None and current_supply != last_supply:
                delta = current_supply - last_supply
                sign = "+" if delta > 0 else ""
                percentage = round((current_supply / MAX_SUPPLY) * 100, 4)
                market_cap = round(current_supply * TOKEN_PRICE, 2)
                cap_growth = round(delta * TOKEN_PRICE, 2)

                if last_update_time:
                    time_diff = format_time_delta(current_time - last_update_time)
                else:
                    time_diff = "—"

                message = (
                    f"📢 AMI Обновление\n"
                    f"Выпущено: {current_supply} токенов ({sign}{delta})\n"
                    f"{percentage}% от максимума\n"
                    f"💲 Цена: ${TOKEN_PRICE:.5f}\n"
                    f"🏦 Капа: ${market_cap}\n"
                    f"💰 Прирост капы: ${cap_growth}\n"
                    f"⏱️ Прошло времени: {time_diff}"
                )
                send_telegram_message(message)

                log_msg = (
                    f"Обновление: {current_supply} токенов ({sign}{delta}), "
                    f"Капа: ${market_cap}, Прирост: ${cap_growth}, "
                    f"Время: {time_diff}, Цена: ${TOKEN_PRICE:.5f}"
                )
                logging.info(log_msg)

                last_update_time = current_time

            last_supply = current_supply

        except Exception as e:
            error_msg = f"⚠️ Ошибка: {str(e)}"
            logging.error(error_msg)
            try:
                send_telegram_message(error_msg)
            except:
                logging.error("❌ Ошибка при отправке сообщения в Telegram")

        time.sleep(DELAY)


if __name__ == '__main__':
    main()
