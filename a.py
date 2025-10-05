import asyncio
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import Channel, Chat, User
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.errors import UserAlreadyParticipantError, InviteHashInvalidError
import motor.motor_asyncio
import os

# ===== CONFIG =====
API_ID = 21189715
API_HASH = '988a9111105fd2f0c5e21c2c2449edfd'
BOT_TOKEN = '8388314171:AAFXrRKZU0d7XMRP5sRNi89ixXXzYGo0_Ws'
OWNER_ID = 8111174619  # controller owner Telegram ID
MONGO_URI = os.environ.get('MONGO_URI', 'mongodb+srv://codexkairnex:gm6xSxXfRkusMIug@cluster0.bplk1.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0')

controller = TelegramClient('controller_bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# MongoDB
mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = mongo_client['telebot_db']
sessions_collection = db['sessions']

broadcast_tasks = {}  # track ongoing broadcasts
userbots = {}  # active sessions {name: client}


# ===== Load sessions from MongoDB =====
async def load_sessions():
    async for doc in sessions_collection.find({}):
        name = doc['name']
        string_session = doc['string_session']
        try:
            client = TelegramClient(StringSession(string_session), API_ID, API_HASH)
            await client.start()
            userbots[name] = client
            print(f"✅ Loaded session: {name}")
        except Exception as e:
            print(f"❌ Failed to load {name}: {e}")


# ===== /start Command =====
@controller.on(events.NewMessage(from_users=OWNER_ID, pattern=r'^/start'))
async def start_command(event):
    await event.reply(
        "🤖 Controller Bot is online!\n"
        "Commands available:\n"
        "/add_session <string>\n"
        "/list_sessions\n"
        "/broadcast_private <msg>\n"
        "/broadcast_group <msg>\n"
        "/stop_broadcast\n"
        "/join <invite_link>\n"
        "/leave <chat_id>"
    )


# ===== Add Session =====
@controller.on(events.NewMessage(from_users=OWNER_ID, pattern=r'^/add_session (.+)'))
async def add_session(event):
    string_session = event.pattern_match.group(1)
    name = f"userbot_{len(userbots)+1}"
    try:
        client = TelegramClient(StringSession(string_session), API_ID, API_HASH)
        await client.start()
        userbots[name] = client
        # save in MongoDB
        await sessions_collection.insert_one({"name": name, "string_session": string_session})
        await event.reply(f"✅ Session added: {name}")
    except Exception as e:
        await event.reply(f"❌ Failed to add session: {e}")


# ===== List Active Sessions =====
@controller.on(events.NewMessage(from_users=OWNER_ID, pattern=r'^/list_sessions'))
async def list_sessions(event):
    if not userbots:
        await event.reply("⚠️ No active sessions.")
        return
    msg = "🟢 Active Sessions:\n"
    for name in userbots.keys():
        msg += f"• {name}\n"
    await event.reply(msg)


# ===== Stop Broadcast =====
@controller.on(events.NewMessage(from_users=OWNER_ID, pattern=r'^/stop_broadcast'))
async def stop_broadcast(event):
    for task in broadcast_tasks.values():
        task.cancel()
    broadcast_tasks.clear()
    await event.reply("🛑 All ongoing broadcasts stopped!")


# ===== Broadcast Private =====
@controller.on(events.NewMessage(from_users=OWNER_ID, pattern=r'^/broadcast_private (.+)'))
async def broadcast_private(event):
    text = event.pattern_match.group(1)
    report = ""
    for name, client in userbots.items():
        async def run_broadcast(c=client, n=name):
            sent, failed = 0, 0
            async for dialog in c.iter_dialogs():
                chat = dialog.entity
                if isinstance(chat, User) and not chat.bot:
                    try:
                        await c.send_message(chat.id, text)
                        sent += 1
                        await asyncio.sleep(0.5)
                    except:
                        failed += 1
            return n, sent, failed

        task = asyncio.create_task(run_broadcast())
        broadcast_tasks[name] = task

    for name, task in broadcast_tasks.items():
        try:
            n, sent, failed = await task
            report += f"{n} → Sent: {sent}, Failed: {failed}\n"
        except asyncio.CancelledError:
            report += f"{name} → Broadcast Cancelled\n"
    broadcast_tasks.clear()
    await event.reply(f"📨 Broadcast Private Completed:\n{report}")


# ===== Broadcast Groups =====
@controller.on(events.NewMessage(from_users=OWNER_ID, pattern=r'^/broadcast_group (.+)'))
async def broadcast_group(event):
    text = event.pattern_match.group(1)
    report = ""
    for name, client in userbots.items():
        async def run_broadcast(c=client, n=name):
            sent, failed = 0, 0
            async for dialog in c.iter_dialogs():
                chat = dialog.entity
                if isinstance(chat, (Channel, Chat)) and not getattr(chat, 'broadcast', False):
                    try:
                        await c.send_message(chat.id, text)
                        sent += 1
                        await asyncio.sleep(0.5)
                    except:
                        failed += 1
            return n, sent, failed

        task = asyncio.create_task(run_broadcast())
        broadcast_tasks[name] = task

    for name, task in broadcast_tasks.items():
        try:
            n, sent, failed = await task
            report += f"{n} → Sent: {sent}, Failed: {failed}\n"
        except asyncio.CancelledError:
            report += f"{name} → Broadcast Cancelled\n"
    broadcast_tasks.clear()
    await event.reply(f"📢 Broadcast Groups Completed:\n{report}")


# ===== Join Group / Channel =====
@controller.on(events.NewMessage(from_users=OWNER_ID, pattern=r'^/join (.+)'))
async def join_group(event):
    target = event.pattern_match.group(1).strip()
    report = ""
    for name, client in userbots.items():
        try:
            if target.startswith("https://t.me/joinchat/"):  # private group
                hash_part = target.split('/')[-1]
                await client(ImportChatInviteRequest(hash_part))
            else:  # public group via @username
                if target.startswith('@'):
                    target = target[1:]
                await client(JoinChannelRequest(target))
            report += f"{name} → Joined successfully ✅\n"
        except UserAlreadyParticipantError:
            report += f"{name} → Already a member ⚠\n"
        except InviteHashInvalidError:
            report += f"{name} → Invalid invite link ❌\n"
        except Exception as e:
            report += f"{name} → Failed: {e}\n"
    await event.reply(f"📥 Join Report:\n{report}")


# ===== Leave Group / Channel =====
@controller.on(events.NewMessage(from_users=OWNER_ID, pattern=r'^/leave (.+)'))
async def leave_group(event):
    target = event.pattern_match.group(1).strip()
    report = ""
    for name, client in userbots.items():
        try:
            if target.startswith("-100") or target.isdigit():  # chat_id
                chat_id = int(target)
            elif target.startswith("https://t.me/joinchat/"):  # private link
                hash_part = target.split('/')[-1]
                result = await client(ImportChatInviteRequest(hash_part))
                chat_id = result.chats[0].id
            else:  # public group via @username
                if target.startswith('@'):
                    target = target[1:]
                chat = await client.get_entity(target)
                chat_id = chat.id
            await client(LeaveChannelRequest(chat_id))
            report += f"{name} → Left successfully ✅\n"
        except Exception as e:
            report += f"{name} → Failed: {e}\n"
    await event.reply(f"📤 Leave Report:\n{report}")

# ===== Startup tasks =====
controller.loop.create_task(load_sessions())
print("🚀 Controller Bot running...")
controller.run_until_disconnected()
