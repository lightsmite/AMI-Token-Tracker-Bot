import os
import asyncio
import logging
import signal
from dotenv import load_dotenv
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
import aiohttp

# === ЗАГРУЗКА .env ===
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
CMC_API_KEY = os.getenv("CMC_API_KEY")
DATA_URL = os.getenv("DATA_URL")
DELAY = int(os.getenv("DELAY", 10))
MAX_SUPPLY = 1_000_000_000
MIN_INTERVAL = 15  # секунд между сообщениями

# === ЛОГИ ===
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler("log.txt", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
# Убираем лишние логи от httpx и telegram.ext
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram.bot").setLevel(logging.WARNING)
logging.getLogger("telegram.ext._application").setLevel(logging.INFO)


# === ФИЛЬТР ТОКЕНА ===
class TokenFilter(logging.Filter):
    def filter(self, record):
        if isinstance(record.msg, str):
            record.msg = record.msg.replace(BOT_TOKEN, "[TOKEN]")
        return True

for handler in logging.getLogger().handlers:
    handler.addFilter(TokenFilter())

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===

def format_time_delta(seconds):
    mins, secs = divmod(int(seconds), 60)
    hours, mins = divmod(mins, 60)
    if hours:
        return f"{hours}ч {mins}м {secs}с"
    elif mins:
        return f"{mins}м {secs}с"
    else:
        return f"{secs}с"

async def fetch_supply(session):
    try:
        async with session.get(DATA_URL) as resp:
            data = await resp.text()
            return int(float(data))
    except Exception as e:
        logging.error(f"Ошибка получения supply: {e}")
        return None

async def fetch_price(session):
    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
    headers = {"X-CMC_PRO_API_KEY": CMC_API_KEY}
    params = {"symbol": "AMI", "convert": "USD"}
    try:
        async with session.get(url, headers=headers, params=params) as resp:
            data = await resp.json()
            return float(data["data"]["AMI"]["quote"]["USD"]["price"])
    except Exception as e:
        logging.error(f"Ошибка получения цены: {e}")
        return None

# === КОМАНДА /report ===

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with aiohttp.ClientSession() as session:
        supply = await fetch_supply(session)
        price = await fetch_price(session)

    if supply is None or price is None:
        await update.message.reply_text("⚠️ Не удалось получить данные.")
        return

    percent = round((supply / MAX_SUPPLY) * 100, 4)
    market_cap = round(supply * price, 2)

    message = (
        f"📊 Отчёт по AMI:\n"
        f"Выпущено: {supply:,} токенов\n"
        f"{percent}% от максимума\n"
        f"💲 Цена: ${price:.5f}\n"
        f"🏦 Капа: ${market_cap:,.2f}"
    )
    await update.message.reply_text(message)

# === ОСНОВНОЙ ЦИКЛ ===

async def main_loop(bot: Bot, stop_event: asyncio.Event):
    last_supply = None
    last_update_time = None
    last_sent_time = 0

    await bot.send_message(chat_id=CHAT_ID, text="✅ Бот запущен и отслеживает выпуск AMI.")

    logging.info("🔄 Парсинг запущен...")

    async with aiohttp.ClientSession() as session:
        while not stop_event.is_set():
            try:
                now = asyncio.get_event_loop().time()
                supply = await fetch_supply(session)
                price = await fetch_price(session)

                if supply is None or price is None:
                    await asyncio.sleep(DELAY)
                    continue

                if last_supply is not None and supply != last_supply:
                    delta = supply - last_supply
                    sign = "+" if delta > 0 else ""
                    percent = round((supply / MAX_SUPPLY) * 100, 4)
                    market_cap = round(supply * price, 2)
                    cap_growth = round(delta * price, 2)
                    time_diff = format_time_delta(now - last_update_time) if last_update_time else "—"

                    message = (
                        f"📢 Обновление AMI\n"
                        f"🟢 Выпущено: {supply:,} токенов ({sign}{delta:,})\n"
                        f"{percent}% от максимума\n"
                        f"💲 Цена: ${price:.5f}\n"
                        f"🏦 Капа: ${market_cap:,.2f}\n"
                        f"💰 Прирост капы: ${cap_growth:,.2f}\n"
                        f"⏱️ Прошло времени: {time_diff}"
                    )

                    logging.info(message)

                    if now - last_sent_time >= MIN_INTERVAL:
                        await bot.send_message(chat_id=CHAT_ID, text=message)
                        last_sent_time = now
                    else:
                        logging.warning("⛔ Пропущено сообщение — слишком частая отправка.")

                    last_update_time = now

                last_supply = supply
                await asyncio.sleep(DELAY)

            except Exception as e:
                logging.error(f"⚠️ Ошибка в парсинге: {e}")
                await asyncio.sleep(DELAY)

# === ЗАПУСК ===

async def main():
    stop_event = asyncio.Event()

    def shutdown():
        logging.info("⏹️ Завершение работы...")
        stop_event.set()

    signal.signal(signal.SIGINT, lambda s, f: shutdown())
    signal.signal(signal.SIGTERM, lambda s, f: shutdown())

    bot = Bot(token=BOT_TOKEN)
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("report", report_command))

    loop_task = asyncio.create_task(main_loop(bot, stop_event))
    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    await stop_event.wait()

    await app.updater.stop()
    await app.stop()
    await app.shutdown()
    loop_task.cancel()

if __name__ == '__main__':
    asyncio.run(main())
