from asyncio import sleep
from random import choice

from telebot.types import CallbackQuery, Message, InlineKeyboardMarkup

from bot.config import mongo_client
from bot.exec import bot
from bot.modules.data_format import (escape_markdown, list_to_inline,
                                     list_to_keyboard, seconds_to_str,
                                     user_name)
from bot.modules.item import AddItemToUser, counts_items, get_name, item_info
from bot.modules.localization import get_data, get_lang, t
from bot.modules.market import (add_product, buy_product, create_seller,
                                delete_product, preview_product, product_ui,
                                seller_ui, create_push)
from bot.modules.market_chose import (buy_item, find_prepare,
                                      pr_edit_description, pr_edit_image,
                                      pr_edit_name, prepare_add,
                                      prepare_data_option, prepare_delete_all,
                                      prepare_edit_price, promotion_prepare,
                                      send_info_pr)
from bot.modules.markup import answer_markup, cancel_markup, count_markup
from bot.modules.markup import markups_menu as m
from bot.modules.states_tools import (ChooseOptionState, ChoosePagesState,
                                      ChooseStepState, prepare_steps)
from bot.modules.user import premium
from bot.modules.over_functions import send_message


users = mongo_client.user.users
sellers = mongo_client.market.sellers
products = mongo_client.market.products
puhs = mongo_client.market.puhs

async def create_adapter(return_data, transmitted_data):
    chatid = transmitted_data['chatid']
    userid = transmitted_data['userid']
    lang = transmitted_data['lang']

    name = return_data['name']
    description = return_data['description']
    description = escape_markdown(description)
    await create_seller(userid, name, description)

    await send_message(chatid, t('market_create.create', lang), 
                           reply_markup= await m(userid, 'seller_menu', lang), parse_mode='Markdown')

async def custom_name(message: Message, transmitted_data):
    userid = message.from_user.id
    lang = await get_lang(message.from_user.id)

    max_len = 50
    min_len = 3

    content = str(message.text)
    content_len = len(content)
    name = escape_markdown(content)

    if content_len > max_len:
        await send_message(message.chat.id, 
                t('states.ChooseString.error_max_len', lang,
                number = content_len, max = max_len))
    elif content_len < min_len:
        await send_message(message.chat.id, 
                t('states.ChooseString.error_min_len', lang,
                number = content_len, min = min_len))
    elif await sellers.find_one({'name': name}):
        await send_message(message.chat.id, 
                t('market_create.name_error', lang))
    else: 
        return True, name
    return False, None

@bot.message_handler(pass_bot=True, text='commands_name.seller_profile.create_market', is_authorized=True)
async def create_market(message: Message):
    userid = message.from_user.id
    lang = await get_lang(message.from_user.id)
    chatid = message.chat.id

    res = await sellers.find_one({'owner_id': userid})
    user = await users.find_one({'userid': userid})

    if res or not user:
        await send_message(message.chat.id, t('menu_text.seller', lang), 
                           reply_markup= await m(userid, 'market_menu', lang))
    elif user['lvl'] < 2:
        await send_message(message.chat.id, t('market_create.lvl', lang))
    else:
        transmitted_data = {}
        steps = [
            {
             "type": 'custom', "name": 'name',
                "data": {'custom_handler': custom_name},
             "translate_message": True,
             'message': {
                'text': "market_create.name",
                'reply_markup': cancel_markup(lang)}
            },
            {
             "type": 'str', "name": 'description', "data": {'max_len': 500}, 
             "translate_message": True,
             'message': {
                'text': "market_create.description",
                'reply_markup': cancel_markup(lang)}
            }
        ]

        await ChooseStepState(create_adapter, userid, chatid, 
                              lang, steps, 
                              transmitted_data=transmitted_data)

@bot.message_handler(pass_bot=True, text='commands_name.seller_profile.my_market', is_authorized=True)
async def my_market(message: Message):
    userid = message.from_user.id
    lang = await get_lang(message.from_user.id)
    chatid = message.chat.id

    res = await sellers.find_one({'owner_id': userid})
    if res:
        text, markup, image = await seller_ui(userid, lang, True)
        await bot.send_photo(chatid, image, text, parse_mode='Markdown', reply_markup=markup)

@bot.message_handler(pass_bot=True, text='commands_name.seller_profile.add_product', is_authorized=True)
async def add_product_com(message: Message):
    userid = message.from_user.id
    lang = await get_lang(message.from_user.id)
    chatid = message.chat.id

    options = {
        "🍕 ➞ 🪙": 'items_coins',
        "🪙 ➞ 🍕": 'coins_items',
        "🍕 ➞ 🍕": 'items_items',
        "🍕 ➞ ⏳": 'auction'
    }

    b_list = list(options.keys())
    markup = list_to_keyboard(
        [b_list, t('buttons_name.cancel', lang)], 2
    )

    await send_message(chatid, t('add_product.options_info', lang), reply_markup=markup)
    await ChooseOptionState(prepare_data_option, userid, chatid, lang, options)

@bot.message_handler(pass_bot=True, text='commands_name.seller_profile.my_products', is_authorized=True)
async def my_products(message: Message):
    userid = message.from_user.id
    lang = await get_lang(message.from_user.id)
    chatid = message.chat.id

    user_prd = list(await products.find({'owner_id': userid}).to_list(None))
    rand_p = {}

    if user_prd:
        for product in user_prd:
            rand_p[
                preview_product(product['items'], product['price'], 
                                product['type'], lang)
            ] = product['_id']

        await send_message(chatid, t('products.search', lang))
        await ChoosePagesState(send_info_pr, userid, chatid, lang, rand_p, 1, 3, 
                               None, False, False)
    else:
        text = t('no_products', lang)
        await send_message(chatid, text,  parse_mode='Markdown')

@bot.callback_query_handler(pass_bot=True, func=lambda call: call.data.startswith('product_info'))
async def product_info(call: CallbackQuery):
    call_data = call.data.split()
    chatid = call.message.chat.id
    userid = call.from_user.id
    lang = await get_lang(call.from_user.id)

    call_type = call_data[1]
    alt_id = call_data[2]
    product = await products.find_one({'alt_id': alt_id})
    if product:
        if call_type == 'delete':
            if product['owner_id'] == userid:
                status = await delete_product(None, alt_id)

                if status: text = t('product_info.delete', lang)
                else: text = t('product_info.error', lang)

                markup = list_to_inline([])
                await bot.edit_message_text(text, chatid, call.message.id, reply_markup=markup, parse_mode='Markdown')
        else:
            if call_type == 'edit_price' and product['owner_id'] == userid:
                await prepare_edit_price(userid, chatid, lang, alt_id)

            elif call_type == 'add' and product['owner_id'] == userid:
                await prepare_add(userid, chatid, lang, alt_id)

            elif call_type == 'items':
                itm = []
                for item in product['items']:
                    if item not in itm:
                        itm.append(item)
                        text, image = item_info(item, lang)

                        try:
                            await bot.send_photo(chatid, image, text, 'Markdown')
                        except:
                            await send_message(chatid, text, parse_mode='Markdown')

            elif call_type == 'buy' and product['owner_id'] != userid:
                if product['owner_id'] != userid:
                    await buy_item(userid, chatid, lang, product, 
                                   user_name(call.from_user), call.message.id)

            elif call_type == 'info':
                text, markup = await product_ui(lang, product['_id'], 
                                          product['owner_id'] == userid)
                await send_message(userid, text, reply_markup=markup, parse_mode='Markdown')

            elif call_type == 'promotion' and product['owner_id'] == userid:
                await promotion_prepare(userid, chatid, lang, product['_id'], 
                                        call.message.id)

@bot.callback_query_handler(pass_bot=True, func=lambda call: call.data.startswith('seller'), private=True)
async def seller(call: CallbackQuery):
    call_data = call.data.split()
    chatid = call.message.chat.id
    userid = call.from_user.id
    lang = await get_lang(call.from_user.id)

    call_type = call_data[1]
    owner_id = int(call_data[2])

    # Кнопки вызываемые владельцем
    if call_type == 'cancel_all':
        await prepare_delete_all(userid, chatid, lang, call.message.id)
    elif call_type == 'edit_text':
        await pr_edit_description(userid, chatid, lang, call.message.id)
    elif call_type == 'edit_name':
        await pr_edit_name(userid, chatid, lang, call.message.id)
    elif call_type == 'edit_image':
        if await premium(userid):
            await pr_edit_image(userid, chatid, lang, call.message.id)
        else:
            await send_message(chatid, t('no_premium', lang))

    # Кнопки вызываемые не владельцем
    elif call_type == 'info':
        my_status = owner_id == userid

        seller = await sellers.find_one({'owner_id': owner_id})
        if seller:
            try:
                chat_user = await bot.get_chat_member(seller['owner_id'], 
                                                      seller['owner_id'])
                name = user_name(chat_user.user)
            except: name = '-'

            text, markup, image = await seller_ui(owner_id, lang, my_status, name)
            await bot.send_photo(chatid, image, text, parse_mode='Markdown', reply_markup=markup)

    elif call_type == 'all':
        user_prd = list(await products.find({'owner_id': owner_id}).to_list(None))

        rand_p = {}
        for product in user_prd:
            rand_p[
                preview_product(product['items'], product['price'], 
                                product['type'], lang)
            ] = product['_id']

        await send_message(chatid, t('products.search', lang))
        await ChoosePagesState(send_info_pr, userid, chatid, lang, rand_p, 1, 3, 
                               None, False, False)
    
    elif call_type == 'сomplain':
        ...

@bot.message_handler(pass_bot=True, text='commands_name.market.random', is_authorized=True)
async def random_products(message: Message):
    userid = message.from_user.id
    lang = await get_lang(message.from_user.id)
    chatid = message.chat.id

    products_all = list(await products.find({"owner_id": {"$ne": userid}}).to_list(None)).copy()
    rand_p = {}

    if products_all:
        for _ in range(18):
            if products_all:
                prd = choice(products_all)
                products_all.remove(prd)

                product = await products.find_one({'_id': prd['_id']})
                if product:
                    rand_p[
                        preview_product(product['items'], product['price'], 
                                        product['type'], lang)
                    ] = product['_id']
            else: break

        await send_message(chatid, t('products.search', lang))
        await ChoosePagesState(send_info_pr, userid, chatid, lang, rand_p, 1, 3, 
                               None, False, False)
    else:
        await send_message(chatid, t('products.null', lang))

@bot.message_handler(pass_bot=True, text='commands_name.market.find', is_authorized=True)
async def find_products(message: Message):
    userid = message.from_user.id
    lang = await get_lang(message.from_user.id)
    chatid = message.chat.id

    await find_prepare(userid, chatid, lang)

@bot.callback_query_handler(pass_bot=True, func=lambda call: call.data.startswith('create_push'), private=True)
async def push(call: CallbackQuery):
    call_data = call.data.split()
    chatid = call.message.chat.id
    userid = call.from_user.id
    lang = await get_lang(call.from_user.id)

    channel_id = int(call_data[1])

    res = await puhs.find_one({'owner_id': userid})
    if res:
        await puhs.update_one({'owner_id': userid}, 
                        {'channel_id': channel_id, 'lang': lang})
        text = t('push.update', lang)
    else: 
        await create_push(userid, channel_id, lang)
        text = t('push.new', lang)

    await send_message(userid, text)
    await bot.edit_message_reply_markup(chatid, call.message.id, 
                                        reply_markup=InlineKeyboardMarkup())
    