import json
from typing import Union

from fastapi import FastAPI
from pydantic import BaseModel
from telethon.sync import TelegramClient

from telegram_utils import migrate_channel_to_supergroup

app = FastAPI()


class Item(BaseModel):
    name: str
    price: float
    is_offer: Union[bool, None] = None


telegram_sessions = []


def initialize_telegram_clients():
    global telegram_sessions
    telegram_sessions = []
    accounts = app.config['ACCOUNTS']
    for account in accounts:
        api_id = account['API_ID']
        api_hash = account['API_HASH']
        phone = account['PHONE']
        print(phone)

        telegram_client = TelegramClient(app.config['SESSION_FOLDER_PATH'] + "/" + phone, api_id, api_hash)
        telegram_client.start()
        if telegram_client.is_user_authorized():
            print('Login success')
            telegram_sessions.append({"phone": phone, "client": telegram_client})
        else:
            print('Login fail due to user not authorized. A code has been sent to ' + phone)
            try:
                telegram_client.send_code_request(phone)
                telegram_client.sign_in(phone, input("Enter the code: "))
            except Exception as e:
                print('Error trying to login with ' + phone)
                print(str(e))
                continue
    return telegram_sessions


def load_config():
    app.config.from_file("config/config.json", load=json.load)


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello {name}"}


@app.get("/items/{item_id}")
def read_item(item_id: int, q: Union[str, None] = None):
    return {"item_id": item_id, "q": q}


@app.put("/items/{item_id}")
def update_item(item_id: int, item: Item):
    return {"item_name": item.name, "item_id": item_id}


@app.get("/migrate-channel/{channel_title}")
def migrate_channel(channel_title: str):
    if channel_title:
        # asyncio.set_event_loop(loop)
        initialize_telegram_clients()
        client = telegram_sessions[0]['client']
        migrate_channel_to_supergroup(client, channel_title)
        return "Channel {} has been migrated successfully.".format(channel_title)
    else:
        return "No channel title was specified. Please, add it as a query parameter as ?channel_title=XXX"
