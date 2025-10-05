import os
import asyncio
from pyrogram import Client, filters
from pyrogram.errors import FloodWait, PeerIdInvalid, ChatWriteForbidden, UserIsBlocked, ChannelPrivate, RPCError

# ===== CONFIG =====
API_ID = int(os.environ.get("API_ID", "21189715"))
API_HASH = os.environ.get("API_HASH", "988a9111105fd2f0c5e21c2c2449edfd")
STRING_SESSION = os.environ.get("STRING_SESSION", "BQGuP2cAxapVVTIPhHzzDbV3UhpBB_BExvbbRzovJLS4PQqL7Fg-MoJNST8lOoDuMsPjw80t_fBQ19BqtIp14Z5a6qgsNZ--gwrxWLlut9gRQCxQKbckI_DwE2owHHmrVJO-nOuT_BiW6ddeQ496-5ahXmRloFXvV6_XpxrNbxjUdPoK0AaabiklydkZWZ2vuklZpxWOldS0vjt2xYsMhrABTZwVrpxtFlwKz8dn5g4Z1Chpya-7AVgfr1hew0ar8-k6hIi_QbXqcDNocASajIyHWk_Ccie9lNrR9rdMh2NuvO4ut2Rm28nbV7Kfv6IG0UwWgK-vIagswbPre_FG-wQ02uU7xgAAAAFGEz7IAA")
OWNER_ID = int(os.environ.get("OWNER_ID", "5470633672"))  # your Telegram user id

# ===== USERBOT CLIENT =====
app = Client(
    name="broadcast_userbot",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=STRING_SESSION,
)

# ===== BROADCAST COMMAND =====
@app.on_message(filters.user(OWNER_ID) & filters.command("broadcast", prefixes=[".", "/", "!", "?"]))
async def broadcast_command(_, message):
    if len(message.command) < 2:
        await message.reply_text("⚠️ Usage: `.broadcast your message`")
        return

    text = message.text.split(maxsplit=1)[1]
    sent = 0
    failed = 0
    total = 0

    msg = await message.reply_text("📢 Broadcast started...")

    async for dialog in app.iter_dialogs():
        chat = dialog.chat
        chat_id = chat.id
        total += 1

        try:
            await app.send_message(chat_id, text)
            sent += 1
            print(f"[+] Sent to {chat_id}")
            await asyncio.sleep(1.5)  # prevent floodwait
        except FloodWait as e:
            print(f"[!] FloodWait {e.value}s")
            await asyncio.sleep(e.value + 1)
            try:
                await app.send_message(chat_id, text)
                sent += 1
            except Exception:
                failed += 1
        except (PeerIdInvalid, ChatWriteForbidden, UserIsBlocked, ChannelPrivate):
            failed += 1
        except RPCError as e:
            print(f"RPCError: {e}")
            failed += 1
        except Exception as e:
            print(f"Error: {e}")
            failed += 1

    await msg.edit_text(
        f"✅ **Broadcast completed!**\n\n"
        f"📊 Total: {total}\n"
        f"✅ Sent: {sent}\n"
        f"❌ Failed: {failed}"
    )


@app.on_message(filters.user(OWNER_ID) & filters.command("ping", prefixes=[".", "/", "!", "?"]))
async def ping(_, message):
    await message.reply_text("🏓 Pong! Userbot is active.")


print("🚀 Userbot broadcast running...")
app.run()
