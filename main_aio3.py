import asyncio
import os
import logging
import aiosqlite
from aiogram import Bot, Dispatcher, types, Router, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.fsm.state import StatesGroup, State
from dotenv import load_dotenv
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, ReplyKeyboardRemove, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from aiogram.filters import Command
# from config import TOKEN  # Импортируем токен бота из файла конфигурации


# Загружаем переменные окружения из файла .env
load_dotenv()

# Получаем значения из .env файла
API_TOKEN = os.getenv('TELEGRAM_TOKEN')

# Настраиваем логирование для вывода информации в консоль
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
logger.info("Бот запущен.")
# Инициализируем бота с заданным токеном и диспетчера
session = AiohttpSession()
bot = Bot(token=API_TOKEN, session=session)
# Создаем роутер
router = Router()


# Регистрация обработчика для callback_query
@router.callback_query(F.data.startswith('lang_'))
async def process_callback_query(callback_query: CallbackQuery):
    await callback_query.answer()
    await callback_query.message.answer(f"You selected {callback_query.data}")
# Создаем хранилище состояний (используется для хранения данных между шагами диалога)
storage = MemoryStorage()
# Создаем диспетчер для обработки входящих сообщений и команд
dp = Dispatcher(storage=storage)
dp.include_router(router)


# Определяем машину состояний для диалога с пользователем
class Form(StatesGroup):
    name = State()   # Состояние ожидания ввода имени
    age = State()    # Состояние ожидания ввода возраста
    grade = State()  # Состояние ожидания ввода класса


# Функция для инициализации базы данных
async def init_db():
    # Подключаемся к базе данных или создаем новую, если её нет
    async with aiosqlite.connect('school_data.db') as db:
        # Создаем таблицу студентов, если она ещё не существует
        await db.execute('''
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                name TEXT NOT NULL,
                age INTEGER NOT NULL,
                grade TEXT NOT NULL
            )
        ''')
        # Создаем уникальный индекс по полю user_id для предотвращения дублирования
        await db.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_students_user_id ON students(user_id)')
        # Сохраняем изменения в базе данных
        await db.commit()


# Хендлер для команды /start — начало диалога
@dp.message(Command(commands=["start"]))
async def start(message: Message, state: FSMContext):
    await message.answer("Привет, ученик! \nТебе нужно ответить на следующие три вопроса:\n"
                         "\n*1. Как тебя зовут? (ФИО полностью)*", reply_markup=ReplyKeyboardRemove(),
                         parse_mode="Markdown")
    await state.set_state(Form.name)


# Хендлер для получения имени от пользователя
@dp.message(Form.name)
async def process_name(message: Message, state: FSMContext):
    if message.text.lower() == 'отменить':
        await cancel_handler(message, state)
        return
    await state.update_data(name=message.text)
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text='Отменить')]],
        resize_keyboard=True
    )
    await message.answer("*2. Сколько тебе лет?*", reply_markup=keyboard,
                         parse_mode="Markdown")
    await state.set_state(Form.age)


# Хендлер для получения возраста от пользователя
@dp.message(Form.age)
async def process_age(message: Message, state: FSMContext):
    if message.text.lower() == 'отменить':
        await cancel_handler(message, state)
        return
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введите корректный возраст (число).")
        return
    age_value = int(message.text)
    if not (5 <= age_value <= 100):
        await message.answer("Пожалуйста, введите реальный возраст от 5 до 100.")
        return
    await state.update_data(age=age_value)
    grades = [str(i) for i in range(1, 12)]
    buttons = [KeyboardButton(text=grade) for grade in grades] + [KeyboardButton(text='Отменить')]
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [buttons[i], buttons[i + 1], buttons[i + 2], buttons[i + 3]] for i in range(0, len(buttons), 4)]
    )

    await message.answer("*3. В каком ты классе учишься? (выбери цифру)*", reply_markup=keyboard,
                         parse_mode="Markdown")
    await state.set_state(Form.grade)


# Хендлер для получения класса от пользователя
@dp.message(Form.grade)
async def process_grade(message: Message, state: FSMContext):
    if message.text.lower() == 'отменить':
        await cancel_handler(message, state)
        return
    await state.update_data(grade=message.text)
    data = await state.get_data()
    inline_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='Подтвердить', callback_data='confirm'),
            InlineKeyboardButton(text='Отменить', callback_data='cancel')
        ]
    ])
    await message.answer(
        f"*Проверьте введенные данные:*\n"
        f"*Имя:* {data['name']}\n"
        f"*Возраст:* {data['age']}\n"
        f"*Класс:* {data['grade']}",
        reply_markup=inline_keyboard, parse_mode="Markdown"
    )


@router.callback_query(F.data == "confirm", StateFilter(Form.grade))
async def process_confirm(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    try:
        async with aiosqlite.connect('school_data.db') as db:
            await db.execute('''
                INSERT OR REPLACE INTO students (user_id, name, age, grade) VALUES (?, ?, ?, ?)
            ''', (callback.from_user.id, data['name'], data['age'], data['grade']))
            await db.commit()
        await bot.send_message(callback.from_user.id, "Данные сохранены.", reply_markup=ReplyKeyboardRemove())
    except Exception as e:
        logger.error(f"Ошибка базы данных: {e}")
        await bot.send_message(callback.from_user.id, "Произошла ошибка при сохранении данных.")
    await callback.message.edit_reply_markup(None)
    await state.clear()
    await callback.answer()


# Хендлер для обработки отмены ввода данных (нажатие на кнопку "Отменить")
# @dp.callback_query(Text("cancel"), Form.grade)
@router.callback_query(F.data == "cancel", StateFilter(Form.grade))
async def process_cancel(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await bot.send_message(callback.from_user.id, "Ввод данных отменен.", reply_markup=ReplyKeyboardRemove())
    await callback.message.edit_reply_markup(None)
    await state.clear()
    await callback.answer()


# Хендлер для команды /cancel — позволяет пользователю отменить текущий ввод
@dp.message(Command(commands=["cancel"]), F.state)  # Используйте F.state для фильтрации по состоянию
async def cancel_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.reply("Ввод данных отменен.")


# Хендлер для команды /profile — отображает сохраненные данные пользователя
@dp.message(Command(commands=["profile"]))
async def profile(message: Message):
    async with aiosqlite.connect('school_data.db') as db:
        async with db.execute(
            'SELECT name, age, grade FROM students WHERE user_id = ?',
            (message.from_user.id,)
        ) as cursor:
            data = await cursor.fetchone()
            if data:
                name, age, grade = data
                await message.answer(f"*Ваши данные:*\n*Имя:* {name}\n*Возраст:* {age}\n*Класс:* {grade}",
                                     parse_mode="Markdown")
            else:
                await message.answer("Вы еще *не предоставили свои данные*. Введите */start* для начала.",
                                     parse_mode="Markdown")


# Хендлер для команды /update — позволяет обновить данные пользователя
@dp.message(Command(commands=["update"]))
async def update_data(message: Message, state: FSMContext):
    await message.answer("Давай обновим твои данные. *Как тебя зовут? (ФИО полностью)*",
                         reply_markup=ReplyKeyboardRemove(), parse_mode="Markdown")
    # await dp.current_state(user=message.from_user.id).set_state(Form.name)
    await state.set_state(Form.name)


# Хендлер для команды /delete — удаляет данные пользователя из базы
@dp.message(Command(commands=["delete"]))
async def delete_data(message: Message):
    async with aiosqlite.connect('school_data.db') as db:
        await db.execute('DELETE FROM students WHERE user_id = ?', (message.from_user.id,))
        await db.commit()
    await message.answer("*Ваши данные были удалены.*", parse_mode="Markdown")


# Хендлер для команды /help — выводит справку по командам
@dp.message(Command(commands=["help"]))
async def help_command(message: Message):
    await message.answer(
        "Я собираю информацию об учениках.\n"
        "*Команды:*\n"
        "/start - начать ввод данных\n"
        "/profile - посмотреть ваши данные\n"
        "/update - обновить ваши данные\n"
        "/delete - удалить ваши данные\n"
        "/help - показать эту справку"
    )


# Хендлер для обработки неизвестных сообщений
@dp.message()
async def unknown_message(message: Message):
    await message.answer("*Извините, я не понимаю это сообщение*. Введите */help* для списка доступных команд.",
                         parse_mode="Markdown")

# Точка входа в программу
if __name__ == '__main__':
    from aiogram import F
    from aiogram.types import BotCommand

    async def main():
        # Устанавливаем команды бота
        await bot.set_my_commands([
            BotCommand(command="/start", description="Начать ввод данных"),
            BotCommand(command="/profile", description="Посмотреть ваши данные"),
            BotCommand(command="/update", description="Обновить ваши данные"),
            BotCommand(command="/delete", description="Удалить ваши данные"),
            BotCommand(command="/help", description="Показать справку")
        ])
        # Функция, выполняемая при запуске бота
        await init_db()
        logger.info("База данных инициализирована.")
        # Запускаем поллинг для обработки обновлений
        try:
            await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
        finally:
            await bot.session.close()

    asyncio.run(main())
