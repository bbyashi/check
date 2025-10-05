import asyncio
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import Channel, Chat, User
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest, GetFullChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest, CheckChatInviteRequest
from telethon.errors import UserAlreadyParticipantError, InviteHashInvalidError, FloodWaitError, UserNotParticipantError
import motor.motor_asyncio
import os

# ===== CONFIG =====
API_ID = 21189715
API_HASH = '988a9111105fd2f0c5e21c2c2449edfd'
BOT_TOKEN = '8366485956:AAGZmX9wTyYuxSIZNW0xTWsgOY8LGwLqoAk'
OWNER_ID = 8331749547  # controller owner Telegram ID
MONGO_URI = os.environ.get('MONGO_URI', 'mongodb+srv://ayanosuvii0925:subhichiku123@cluster0.uw8yxkl.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0')

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


@controller.on(events.NewMessage(from_users=OWNER_ID, pattern=r'^/remove_session (.+)'))
async def remove_session(event):
    name = event.pattern_match.group(1).strip()

    if name not in userbots:
        await event.reply(f"⚠️ Session `{name}` not found.")
        return

    try:
        await userbots[name].disconnect()
        del userbots[name]
        await sessions_collection.delete_one({"name": name})
        await event.reply(f"🗑️ Session `{name}` removed successfully.")
    except Exception as e:
        await event.reply(f"❌ Error removing session `{name}`:\n`{e}`")


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
            # --- Private group or channel link ---
            if "joinchat" in target or target.startswith("https://t.me/+"):
                # Extract only the hash part
                invite_hash = target.split("/")[-1].replace("+", "")
                await client(ImportChatInviteRequest(invite_hash))
                report += f"{name} → Joined via private link ✅\n"

            # --- Public group or channel link ---
            else:
                username = target.replace("https://t.me/", "").lstrip("@")
                await client(JoinChannelRequest(username))
                report += f"{name} → Joined @{username} ✅\n"

        except UserAlreadyParticipantError:
            report += f"{name} → Already joined ⚠️\n"
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
            chat = None
            chat_id = None

            # Detect chat ID / username / invite
            if target.startswith("-100") or target.isdigit():
                chat_id = int(target)
                chat = await client(GetFullChannelRequest(chat_id))
            elif "joinchat" in target or target.startswith("https://t.me/+"):
                invite_hash = target.split("/")[-1].replace("+", "")
                try:
                    invite = await client(CheckChatInviteRequest(invite_hash))
                    if invite.chat:
                        chat_id = invite.chat.id
                except UserAlreadyParticipantError:
                    pass
                except FloodWaitError as e:
                    report += f"{name} → Wait {e.seconds}s (Telegram flood-wait) ⚠️\n"
                    continue
            else:
                username = target.replace("https://t.me/", "").lstrip("@")
                entity = await client.get_entity(username)
                chat_id = entity.id

            # Try to leave
            if chat_id:
                try:
                    await client(LeaveChannelRequest(chat_id))
                    report += f"{name} → Left successfully ✅\n"
                except UserNotParticipantError:
                    report += f"{name} → Not a member ⚠️\n"
            else:
                report += f"{name} → Could not resolve chat ID ❌\n"

        except Exception as e:
            report += f"{name} → Failed: {e}\n"

    await event.reply(f"📤 Leave Report:\n{report}")



# ===== Startup tasks =====
controller.loop.create_task(load_sessions())
print("🚀 Controller Bot running...")
controller.run_until_disconnected()
