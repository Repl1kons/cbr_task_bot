import asyncio
import aiohttp
import json
import xml.etree.ElementTree as ET
import redis.asyncio as redis
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import CommandStart, Command
import os
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

# Подключение к Redis
redis_pool = redis.ConnectionPool.from_url("redis://redis:6379")
r = redis.Redis(connection_pool=redis_pool, decode_responses=True)


async def update_rates():
    cbr_url = "https://cbr.ru/scripts/XML_daily.asp"  # url для загрузки курса валют с центра банка России
    async with aiohttp.ClientSession() as session:
        async with session.get(cbr_url) as response:
            response_content = await response.read()

    # Парсинг XML файла
    tree = ET.ElementTree(ET.fromstring(response_content))
    root = tree.getroot()

    currencies = []
    for currency in root.findall('Valute'):
        char_code = currency.find('CharCode').text
        name = currency.find('Name').text
        nominal = currency.find('Nominal').text
        unit_value_price = currency.find('VunitRate').text
        unit_price = currency.find('Value').text

        # Добавление данных в массив
        currencies.append({
            "char_code": char_code,
            "name": name,
            "nominal": nominal,
            "unit_value_price": unit_value_price,
            "unit_price": unit_price
        })

    # Сохранение массива в Redis в формате JSON
    await r.set("currencies", json.dumps(currencies), ex=3600)
    print(f"Все данные успешно обновлены в Redis. {await r.keys('*')}")


# Инициализация диспетчера
dp = Dispatcher()


@dp.message(CommandStart())
async def start(message: Message) -> None:
    await message.answer(
        text=('👋 *Привет!*\n\n'
              'Я твой помощник для показа актуальных курсов валют. 💱\n\n'
              '📈 *Команды для использования:*\n'
              '1. /rates — узнать курс всех валют.\n'
              '2. /exchange — конвертировать одну валюту в другую.\n\n'
              'Если у тебя есть вопросы по использованию команд,\n'
              'используй команду /help 😊'),
        parse_mode='Markdown'
    )


@dp.message(Command('help'))
async def command_help(message: Message) -> None:
    await message.answer(
        text="*Помощь по командам:*\n\n"
             "`1️⃣.` Введи команду /rates для показа актуального курса валют\n\n"
             "`2️⃣.` *Как правильно использовать команду /exchange:*\n"
             "`1`. Первый аргумент: укажите валюту, которую хотите конвертировать.\n"
             "`2`. Второй аргумент: укажите валюту, в которую хотите конвертировать.\n"
             "`3`. Третий аргумент: укажите сумму, которую хотите конвертировать.\n\n"
             "```Пример\n"
             "/exchange USD RUB 10```",
        parse_mode='Markdown')


@dp.message(Command('rates'))
async def rates(message: Message) -> None:
    # Проверка наличия данных в Redis
    data = await r.get("currencies")
    if not data:
        await update_rates()
        data = await r.get("currencies")

    currencies = json.loads(data)

    # Формирование сообщения с курсами валют
    message_text = "*Актуальные курсы валют:*\n\n"
    for currency in currencies:
        message_text += f"- 1 *{currency['char_code']}/RUB*: = `{currency['unit_value_price']}`₽\n"

    await message.answer(text=message_text, parse_mode='Markdown')


@dp.message(Command('exchange'))
async def exchange(message: Message) -> None:
    try:
        args = message.text.split(' ')
        if len(args) != 4:
            raise ValueError("Invalid number of arguments")
        from_currency = args[1].upper()
        to_currency = args[2].upper()
        value = int(args[3])

        data = await r.get("currencies")
        if not data:
            await update_rates()
            data = await r.get("currencies")

        currencies = json.loads(data)

        # Поиск валюты по коду в Redis
        from_currency_data = next((c for c in currencies if c['char_code'] == from_currency), None)
        to_currency_data = next((c for c in currencies if c['char_code'] == to_currency), None)

        if from_currency == 'RUB':
            to_value = float(to_currency_data['unit_value_price'].replace(',', '.'))
            result = round(value / to_value, 2)
            message_text = f"{value} RUB в {to_currency}: `{result}`"

        elif to_currency == 'RUB':
            from_value = float(from_currency_data['unit_value_price'].replace(',', '.'))
            to_value = 1.0
            # Перевод суммы в рубли, затем в целевую валюту
            amount_in_rub = (value * from_value)
            result = round(amount_in_rub / to_value, 2)
            message_text = f"{value} {from_currency_data['char_code']} в {to_currency}: `{result}`"
        else:
            from_value = float(from_currency_data['unit_value_price'].replace(',', '.'))
            to_value = float(to_currency_data['unit_value_price'].replace(',', '.'))
            amount_in_rub = (value * from_value)
            result = round(amount_in_rub / to_value, 2)
            message_text = f"{value} {from_currency_data['char_code']} в {to_currency}: `{result}`"

        await message.answer(text=message_text, parse_mode='Markdown')

    except Exception:
        await message.answer("Ошибка в использовании команды\n/exchange\n\n"
                             "Возможно, произошла ошибка при указании аргументов команды.\n\n"
                             "*Как правильно использовать команду /exchange:*\n\n"
                             "`1`. Первый аргумент: укажите валюту, которую хотите конвертировать.\n"
                             "`2`. Второй аргумент: укажите валюту, в которую хотите конвертировать.\n"
                             "`3`. Третий аргумент: укажите сумму, которую хотите конвертировать.\n\n"
                             "```Пример\n"
                             "/exchange USD RUB 10```", parse_mode='Markdown')


async def main() -> None:
    bot = Bot(token=os.getenv('TOKEN_BOT'))
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
