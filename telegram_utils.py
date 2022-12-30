import csv
import datetime
import json
import random
import re
import time
import traceback

from easychatgpt import ChatClient
from telethon import functions
from telethon.errors.rpcerrorlist import PeerFloodError, UserPrivacyRestrictedError, FloodWaitError
from telethon.sync import TelegramClient
from telethon.tl.functions.channels import InviteToChannelRequest, CreateChannelRequest
from telethon.tl.functions.messages import GetDialogsRequest
from telethon.tl.types import InputPeerEmpty, InputPeerChannel, InputPeerUser, Channel, Chat, InputUser

import logging

WAIT_BETWEEN_OPERATION = 120

WAIT_BETWEEN_CHUNKS = 900

USERS_CHUNK = 35

ERRORS_ALLOWED = 3

config = {}


def evaluate_sleep_message(message):
    seconds_str = re.findall('\d+', message)
    if seconds_str:
        countdown(int(str(seconds_str[0])) + random.randint(60, 180))


def scrap_members(client):
    logging.info("Scrapping members.")
    group = get_group_by_user_input(client, True)
    logging.info('Fetching Members...')
    all_participants = client.get_participants(group, aggressive=True)
    logging.info('Saving In file...')
    with open("data/members.csv", "w", encoding='UTF-8') as f:
        writer = csv.writer(f, delimiter=",", lineterminator="\n")
        writer.writerow(['username', 'user id', 'access hash', 'name', 'group', 'group id', 'group hash'])
        for user in all_participants:
            if user.username:
                username = user.username
            else:
                username = ""
            if user.first_name:
                first_name = user.first_name
            else:
                first_name = ""
            if user.last_name:
                last_name = user.last_name
            else:
                last_name = ""
            name = (first_name + ' ' + last_name).strip()
            writer.writerow([username, user.id, user.access_hash, name, group.title, group.id, group.hash])
    logging.info('Members scraped successfully.')


def get_users_from_file(file_path):
    users = []
    with open(file_path, encoding='UTF-8') as f:
        rows = csv.reader(f, delimiter=",", lineterminator="\n")
        next(rows, None)
        for row in rows:
            user = {'username': row[0], 'id': int(row[1]), 'access_hash': int(row[2]), 'name': row[3]}
            users.append(user)
    return users


def get_users_from_participants(participants):
    users = []
    for participant in participants:
        users.append(
            {'username': participant.username, 'id': int(participant.id), 'access_hash': int(participant.access_hash),
             'name': participant.first_name + ' ' + participant.last_name})
    return users


def evaluate_errors(num_errors):
    if num_errors >= ERRORS_ALLOWED:
        logging.info(str(ERRORS_ALLOWED) + " number of errors reached.")
        quit()


def add_members_progressively(client, group_entity, users):
    num_errors = 0
    iteration = 0
    members_added = 0
    for user in users:
        iteration += 1
        if iteration % USERS_CHUNK == 0:
            logging.info("Waiting " + str(WAIT_BETWEEN_CHUNKS) + " Seconds...")
            countdown(WAIT_BETWEEN_CHUNKS)
        try:
            logging.info("Adding {}".format(user))

            updates = client(InviteToChannelRequest(channel=group_entity,
                                                    users=[InputUser(user_id=user['id'],
                                                                     access_hash=user['access_hash'])]))
            if len(updates.updates) > 0:
                logging.info("Username {} added.".format(user['name']))
                members_added += 1
            else:
                logging.info("User {} was already in the group.".format(user['name']))
            print("Waiting " + str(WAIT_BETWEEN_OPERATION) + " Seconds...")
            countdown(WAIT_BETWEEN_OPERATION)
        except (PeerFloodError, FloodWaitError) as e:
            num_errors += 1
            logging.info("Getting Flood Error from telegram operating with api_id {}.".format(client.api_id))
            traceback.print_exc()
        except UserPrivacyRestrictedError as e:
            num_errors += 1
            logging.info("The user's privacy settings do not allow you to do this. Skipping.")
            traceback.print_exc()
        except Exception as e:
            num_errors += 1
            evaluate_sleep_message(str(e))
            logging.info("Unexpected Error.")
            traceback.print_exc()
        finally:
            evaluate_errors(num_errors)

    logging.info("Total members added: " + str(members_added))


def add_members(client, file_path):
    logging.info("Adding members from " + file_path + ".")

    users = get_users_from_file(file_path)
    group = get_group_by_user_input(client, True)
    target_group_entity = InputPeerChannel(group.id, group.access_hash)

    add_members_progressively(client, target_group_entity, users)


def set_supergroup(client):
    logging.info("Setting supergroup.")
    target_group = get_group_by_user_input(client, False)
    client(functions.messages.MigrateChatRequest(chat_id=target_group.id))


def get_chats(client):
    all_chats = []
    chats = []
    result = client(GetDialogsRequest(
        offset_date=None,
        offset_id=0,
        offset_peer=InputPeerEmpty(),
        limit=200,
        hash=0
    ))
    chats.extend(result.chats)
    for chat in chats:
        if chat.title == 'Testing channel':
            all_chats.append(chat)
    return all_chats


def is_active(chat):
    return (isinstance(chat, Channel) or isinstance(chat, Chat)) and (
            not hasattr(chat, "deactivated") or (hasattr(chat, "deactivated") and not chat.deactivated))


def get_groups(client, megagroup):
    chats = []
    groups = []
    result = client(GetDialogsRequest(
        offset_date=None,
        offset_id=0,
        offset_peer=InputPeerEmpty(),
        limit=200,
        hash=0
    ))
    chats.extend(result.chats)
    for chat in chats:
        try:
            is_chat_active = is_active(chat)
            if is_chat_active:
                if megagroup is None or (not megagroup and not hasattr(chat, "megagroup") or not chat.megagroup) or \
                        (megagroup and hasattr(chat, "megagroup") and chat.megagroup):
                    groups.append(chat)
        except Exception as inst:
            logging.info(type(inst))  # the exception instance
            logging.info(inst.args)  # arguments stored in .args
            logging.info(inst)  # __str__ allows args to be printed directly,
            continue
    return groups


def get_group_by_user_input(client, megagroup):
    groups = get_groups(client, megagroup)
    logging.info('Choose a group: ')
    i = 0
    for group in groups:
        logging.info(str(i) + '- ' + group.title)
        i += 1
    g_index = input("Enter the number: ")
    return groups[int(g_index)]


def get_group_by_title(client, megagroup, title):
    groups = get_groups(client, megagroup)
    result = None
    for group in groups:
        if group.title == title:
            result = group
            break
    return result


def countdown(t):
    while t:
        timer = 'Sleeping for ' + str(datetime.timedelta(seconds=t))
        print(timer, end="\r")
        time.sleep(1)
        t -= 1
    print()


def generate_session(configuration):
    sessions = []
    accounts = configuration['ACCOUNTS']
    for account in accounts:
        api_id = account['API_ID']
        api_hash = account['API_HASH']
        phone = account['PHONE']
        logging.info(phone)

        telegram_client = TelegramClient(configuration['SESSION_FOLDER_PATH'] + "/" + phone, api_id, api_hash)
        telegram_client.start()
        if telegram_client.is_user_authorized():
            logging.info('Login success')
            sessions.append({"phone": phone, "client": telegram_client})
        else:
            logging.info('Login fail due to user not authorized. A code has been sent to ' + phone)
            try:
                telegram_client.send_code_request(phone)
                telegram_client.sign_in(phone, input("Enter the code: "))
            except Exception as e:
                logging.info('Error trying to login with ' + phone)
                logging.info(str(e))
                continue
    return sessions


def create_super_group(client, channel):
    title = channel.title + "_group"
    result = get_group_by_title(client, True, title)
    if result is None:
        result = client(CreateChannelRequest(channel.title + "_group", "about", megagroup=True)).chats[0]

    return result


def migrate_channel_to_supergroup(client, channel_title):
    channel = get_group_by_title(client, False, channel_title)
    if channel is not None:
        group = create_super_group(client, channel)

        channel_participants = client.get_participants(channel, aggressive=True)
        users = get_users_from_participants(channel_participants)
        # Just for testing purposes, doing the users array bigger. But data is not 100% reliable
        # users = users + get_users_from_file('data/members.csv')

        group_entity = client.get_entity(InputPeerChannel(group.id, group.access_hash))
        logging.info(str(len(users)) + ' users to add in total to the channel {}.'.format(group.title))
        add_members_progressively(client, group_entity, users)
    else:
        logging.info('No channel found with name {}'.format(channel_title))


def summarize(client):
    to_summarize = ''
    group = get_group_by_user_input(client, None)

    for message in client.iter_messages(group, reverse=True, limit=100):
        if message.text is not None:
            # logging.info(message.sender_id, ':', message.text)
            to_summarize = to_summarize + message.text + "\n"

    logging.info('Text to summarize: ', to_summarize)

    chat = ChatClient("adpabloslopez+openai@gmail.com", "dwp*wpt0xvt-rjn7YPH")
    answer = chat.interact('Summarize the following text: ' + to_summarize)
    logging.info(answer)


def menu(client):
    ans = True
    while ans:
        print("""
    1.Set supergroup
    2.Scrap members
    3.Migrate channel to supergroup
    4.Add members
    5.Summarize        
    6.Exit/Quit
        """)
        ans = input("What would you like to do? ")
        if ans == "1":
            logging.info("Set supergroup option selected.")
            set_supergroup(client)
            ans = None
        elif ans == "2":
            logging.info("Scrap members")
            scrap_members(client)
            ans = None
        elif ans == "3":
            logging.info("Migrate channel to supergroup option selected.")
            channel_title = input("What is the title of your channel? ")
            migrate_channel_to_supergroup(client, channel_title)
            ans = None
        elif ans == "4":
            logging.info("Add members option selected.")
            add_members(client, 'data/members.csv')
            ans = None
        elif ans == "5":
            logging.info("Summarize option selected.")
            summarize(client)
            ans = None
        elif ans == "6":
            logging.info("Exit option selected.")
            ans = None
        else:
            print("Not Valid Choice selected Try again")


if __name__ == "__main__":
    logging.basicConfig(filename='logs.log', encoding='utf-8', level=logging.INFO)
    start_time = datetime.datetime.now()

    with open('config/config.json', 'r', encoding='utf-8') as f:
        config = json.loads(f.read())

    clients = generate_session(config)
    client = clients[0]
    logging.info("Selected telegram client with phone {}.".format(client['phone']))
    menu(client['client'])

    logging.info("Total time: " + str(datetime.datetime.now() - start_time))
