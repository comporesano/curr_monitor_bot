from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from settings import TOKEN, API_KEY, CL_URL, PC_URL, PATH, CHAT_ID
import asyncio
import json
import requests
import threading


class CMB(Bot):
    '''
    Currency monitor bot
    '''
    def __init__(self, TOKEN: str) -> None:
        super().__init__(TOKEN)
        
        self.emit_main_menu_markup()
    
    def emit_main_menu_markup(self) -> None:
        check_button = InlineKeyboardButton(text='Check currencies', callback_data='check')
        add_button = InlineKeyboardButton(text='Add currency', callback_data='add')
        delete_button = InlineKeyboardButton(text='Delete currency', callback_data='delete')
        
        self.main_markup = InlineKeyboardMarkup().add(check_button,
                                                      add_button,
                                                      delete_button)

    def get_crypto_currencies_markup(self, count: int) -> InlineKeyboardMarkup:
        currencies_reply_markup = InlineKeyboardMarkup()
        
        parameters = {
        'start': '1',
        'limit': count,
        'convert': 'USD'
        }

        headers = {
        'Accepts': 'application/json',
        'X-CMC_PRO_API_KEY': API_KEY,
        }

        response = requests.get(url=CL_URL, headers=headers, params=parameters)

        if response.status_code == 200:
            data = response.json()
            currencies = []
            for currency in data['data']:
                if currency['symbol'] not in currencies:
                    currencies.append(currency['symbol'])
            for curr in currencies:
                currencies_reply_markup.add(InlineKeyboardButton(curr, callback_data=f'ch_curr_{curr}'))
        else:
            print(f"Error {response.status_code}: {response.json()['status']['error_message']}")

        return currencies_reply_markup
    
    def get_delete_markup(self) -> ReplyKeyboardMarkup:
        data_dict = json.load(open(PATH, 'r'))
        delete_markup = ReplyKeyboardMarkup(resize_keyboard=True)
        
        for curr in list(data_dict["data"].keys()):
            delete_markup.add(KeyboardButton(curr))
        
        return delete_markup
    

class AddState(StatesGroup):
    count_of_crypto = State()
    up_down = State()
    delete_currency_state = State()


cm_bot = CMB(TOKEN=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(cm_bot, storage=storage)

@dp.message_handler(commands=['start'])
async def help_message(message: types.Message) -> None:
    if message.chat.id != CHAT_ID:
        await message.reply('This is currency monitoring bot. Type /menu to start.')
        
@dp.message_handler(commands=['menu'])
async def main_menu(message: types.Message, state:FSMContext) -> None:
    if message.chat.id != CHAT_ID:
        await message.reply('Choose an option:', reply_markup=cm_bot.main_markup)

async def get_price_of_crypto() -> dict:
    data_dict = json.load(open(PATH, 'r'))
    price_list = {}
    headers = {
        'Accepts': 'application/json',
        'X-CMC_PRO_API_KEY': API_KEY,
    }
    if len(list(data_dict['data'].keys())) != 0:
        for key in list(data_dict['data'].keys()):
            parameters = {
                'symbol': key,
            }
            
            response = requests.get(url=PC_URL, headers=headers, params=parameters)
            
            if response.status_code == 200:
                data = response.json()
                price = data['data'][key]['quote']['USD']['price']
                price_list[key] = price
            else:
                print(f"Error {response.status_code}: {response.json()['status']['error_message']}")
                return None
    else:
        return None
    
    return price_list
        
async def check_price() -> None:
    data_dict = json.load(open(PATH, 'r'))
    prices = await get_price_of_crypto()
    messages = []
    
    if prices:
        for key in list(prices.keys()):
            if prices[key] >= int(data_dict['data'][key]['up']):
                messages.append(f'{key} - reached "up" value')
            elif prices[key] <= int(data_dict['data'][key]['down']):
                messages.append(f'{key} - reached "down" value')
    
    for msg in messages:
        await cm_bot.send_message(chat_id=CHAT_ID, text=msg)
        
async def check_price_task():
    while True:
        await check_price()
        await asyncio.sleep(5)
    
@dp.callback_query_handler(text=['check', 'add', 'delete'])
async def handle_main_functions(call: types.CallbackQuery, state: FSMContext) -> None:
    if call.data == 'check':
        data_dict = json.load(open(PATH, 'r'))
        if len(list(data_dict["data"].keys())) != 0:
            monitor_strs= '\n'.join([str(n + 1) + '. Currency: ' + key + ', Down value: ' + data_dict["data"][key]["down"] + '$, Up value: ' + data_dict["data"][key]["up"] + '$.' \
                                    for n, key in enumerate(list(data_dict["data"].keys()))])
            await call.message.answer(f'Current monitoring crypto currencies:\n{monitor_strs}')
        else:
            await call.message.answer("Nothing to monitor")
    if call.data == 'add':
        await call.message.answer(f'Choose count of crypto currencies in list')
        await AddState.count_of_crypto.set()
    if call.data == 'delete':
        data_dict = json.load(open(PATH, 'r'))
        if len(list(data_dict["data"].keys())) != 0:
            await call.message.answer("Choose currency for delete:", reply_markup=cm_bot.get_delete_markup())
            await AddState.delete_currency_state.set()
        else:
            await call.message.answer("Nothing to delete")

@dp.message_handler(state=AddState.delete_currency_state)
async def delete_currency(message: types.Message, state: FSMContext):
    curr = message.text
    data_dict = json.load(open(PATH, 'r'))
    del data_dict["data"][curr]
    
    with open(PATH, 'w') as jf:
        json.dump(data_dict, jf, indent=4)
    
    await message.reply(f'{curr} was deleted from monitoring!', reply_markup=types.ReplyKeyboardRemove())
    await state.finish()
    
@dp.message_handler(state=AddState.count_of_crypto)
async def crypto_count_handler(message: types.Message, state: FSMContext) -> None:
    count = message.text 
    try:
        count = int(count)
        if count <= 0:
            raise ValueError('Count of crypto currencies value - invalid(not num)')

        await message.answer(f'List of crypto currencies({count})', reply_markup=cm_bot.get_crypto_currencies_markup(count))

    except ValueError as e:
        await message.answer(str(e))
        await state.finish()
        return
    finally:
        await state.finish()

@dp.callback_query_handler(lambda callback_query: callback_query.data.startswith('ch_curr_'))
async def currency_handle(call: types.CallbackQuery, state: FSMContext):
    global currency_symbol
    
    currency_symbol = call.data.split('ch_curr_')[1]
    
    data_dict = json.load(open(PATH, 'r'))
    data_dict["data"][currency_symbol] = {"down": 0, "up": 0}
    
    with open(PATH, 'w') as jf:
        json.dump(data_dict, jf, indent=4)
    
    await call.message.reply(f'Current crypto: {currency_symbol}\nEnter up and down value in USD for {currency_symbol} like - "down up"', reply_markup=types.ReplyKeyboardRemove())
    await state.finish()
    await AddState.up_down.set()

@dp.message_handler(state=AddState.up_down)
async def get_up_down_values(message: types.Message, state: FSMContext):
    
    up_down_values = message.text
    
    try:
        values = up_down_values.split(' ')
        
        if len(values) != 2 or values[0] > values[1] or int(values[0]) <= 0 or int(values[1]) <= 0:
            raise ValueError('Invalid "down up" value (down > up or down, up are missing or down, up invalid values)')
    except ValueError as e:
        await message.answer(str(e))
        await state.finish()
        return
    finally:
        data_dict = json.load(open(PATH, 'r'))
        data_dict["data"][currency_symbol] = {"down": values[0], "up": values[1]}
        
        with open(PATH, 'w') as jf:
            json.dump(data_dict, jf, indent=4)
        
        await message.reply(f'Down value - {values[0]}$ and Up value - {values[1]}$ set for {currency_symbol} currency')
        await state.finish()
    
def main():
    executor.start_polling(dp)   
    
if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.create_task(check_price_task())
    main()
    
    