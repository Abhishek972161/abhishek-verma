from pyrogram import utils as pyroutils
pyroutils.MIN_CHAT_ID = -999999999999
pyroutils.MIN_CHANNEL_ID = -100999999999999
import pyromod
import os
import re
import sys
import json
import time
import asyncio
import requests
import subprocess
import logging
from utils import progress_bar
import core as helper
from config import BOT_TOKEN, API_ID, API_HASH, MONGO_URI, BOT_NAME
import aiohttp
from aiohttp import ClientSession
from subprocess import getstatusoutput
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from pyrogram.errors.exceptions.bad_request_400 import StickerEmojiInvalid
from pyrogram.types.messages_and_media import message
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from bs4 import BeautifulSoup
from logs import get_last_two_minutes_logs
import tempfile
from db import get_collection, save_name, load_name, save_log_channel_id, load_log_channel_id, save_authorized_users, load_authorized_users, load_allowed_channel_ids, save_allowed_channel_ids, load_accept_logs, save_accept_logs # Import the database functions
from db import save_bot_running_time, load_bot_running_time, reset_bot_running_time, save_max_running_time, load_max_running_time
from db import save_queue_file, load_queue_file
from PIL import Image
from pytube import Playlist  #Youtube Playlist Extractor
from yt_dlp import YoutubeDL
import yt_dlp as youtube_dl

# Initialize bot
bot = Client("bot",
             bot_token=BOT_TOKEN,
             api_id=API_ID,
             api_hash=API_HASH)

# Get the MongoDB collection for this bot
collection = get_collection(BOT_NAME, MONGO_URI)
# Constants
OWNER_IDS = [5840594311]  # Replace with the actual owner user IDs

cookies_file_path ="modules/cookies.txt"
# Global variables
log_channel_id = [-1002323970081]
authorized_users = [5840594311,7856557198]
ALLOWED_CHANNEL_IDS = [-1002323970081]
my_name = "❤️"
overlay = None 
accept_logs = 0
bot_running = False
start_time = None
total_running_time = None
max_running_time = None
file_queue = []

# Load initial data from files
def load_initial_data():
    global log_channel_id, authorized_users, ALLOWED_CHANNEL_IDS, my_name, accept_logs
    global total_running_time, max_running_time
  
    log_channel_id = load_log_channel_id(collection)
    authorized_users = load_authorized_users(collection)
    ALLOWED_CHANNEL_IDS = load_allowed_channel_ids(collection)
    my_name = load_name(collection)
    accept_logs = load_accept_logs(collection)
    # Load bot running time and max running time
    total_running_time = load_bot_running_time(collection)
    max_running_time = load_max_running_time(collection)
    file_queue = load_queue_file(collection)

# Filters
def owner_filter(_, __, message):
    return bool(message.from_user and message.from_user.id in OWNER_IDS)

def channel_filter(_, __, message):
    return bool(message.chat and message.chat.id in ALLOWED_CHANNEL_IDS)

def auth_user_filter(_, __, message):
    return bool(message.from_user and message.from_user.id in authorized_users)

auth_or_owner_filter = filters.create(lambda _, __, m: auth_user_filter(_, __, m) or owner_filter(_, __, m))
auth_owner_channel_filter = filters.create(lambda _, __, m: auth_user_filter(_, __, m) or owner_filter(_, __, m) or channel_filter(_, __, m))
owner_or_channel_filter = filters.create(lambda _, __, m: owner_filter(_, __, m) or channel_filter(_, __, m))


#===================== Callback query handler ===============================

# Callback query handler for help button
@bot.on_callback_query(filters.regex("help") & auth_or_owner_filter)
async def help_callback(client: Client, query: CallbackQuery):
    await help_command(client, query.message)

@bot.on_callback_query(filters.regex("show_channels") & auth_or_owner_filter)
async def show_channels_callback(client: Client, query: CallbackQuery):
    await show_channels(client, query.message)

@bot.on_callback_query(filters.regex("remove_chat") & auth_or_owner_filter)
async def remove_chat_callback(client: Client, query: CallbackQuery):
    await remove_channel(client, query.message)

#====================== Command handlers ========================================
@bot.on_message(filters.command("add_log_channel") & filters.create(owner_filter))
async def add_log_channel(client: Client, message: Message):
    global log_channel_id
    try:
        new_log_channel_id = int(message.text.split(maxsplit=1)[1])
        log_channel_id = new_log_channel_id
        save_log_channel_id(collection, -1002323970081)
        await message.reply(f"Log channel ID updated to {new_log_channel_id}.")
    except (IndexError, ValueError):
        await message.reply("Please provide a valid channel ID.")

@bot.on_message(filters.command("auth_users") & filters.create(owner_filter))
async def show_auth_users(client: Client, message: Message):
    await message.reply(f"Authorized users: {authorized_users}")

@bot.on_message(filters.command("add_auth") & filters.create(owner_filter))
async def add_auth_user(client: Client, message: Message):
    global authorized_users
    try:
        new_user_id = int(message.text.split(maxsplit=1)[1])
        if new_user_id not in authorized_users:
            authorized_users.append(new_user_id)
            save_authorized_users(collection, authorized_users)
            await message.reply(f"User {new_user_id} added to authorized users.")
        else:
            await message.reply(f"User {new_user_id} is already in the authorized users list.")
    except (IndexError, ValueError):
        await message.reply("Please provide a valid user ID.")

@bot.on_message(filters.command("remove_auth") & filters.create(owner_filter))
async def remove_auth_user(client: Client, message: Message):
    global authorized_users
    try:
        user_to_remove = int(message.text.split(maxsplit=1)[1])
        if user_to_remove in authorized_users:
            authorized_users.remove(user_to_remove)
            save_authorized_users(collection, authorized_users)
            await message.reply(f"User {user_to_remove} removed from authorized users.")
        else:
            await message.reply(f"User {user_to_remove} is not in the authorized users list.")
    except (IndexError, ValueError):
        await message.reply("Please provide a valid user ID.")

@bot.on_message(filters.command("add_channel") & auth_or_owner_filter)
async def add_channel(client: Client, message: Message):
    global ALLOWED_CHANNEL_IDS
    try:
        new_channel_id = int(message.text.split(maxsplit=1)[1])
        if new_channel_id not in ALLOWED_CHANNEL_IDS:
            ALLOWED_CHANNEL_IDS.append(new_channel_id)
            save_allowed_channel_ids(collection, ALLOWED_CHANNEL_IDS)
            await message.reply(f"Channel {new_channel_id} added to allowed channels.")
        else:
            await message.reply(f"Channel {new_channel_id} is already in the allowed channels list.")
    except (IndexError, ValueError):
        await message.reply("Please provide a valid channel ID.")

@bot.on_message(filters.command("remove_channel") & auth_or_owner_filter)
async def remove_channel(client: Client, message: Message):
    global ALLOWED_CHANNEL_IDS
    try:
        channel_to_remove = int(message.text.split(maxsplit=1)[1])
        if channel_to_remove in ALLOWED_CHANNEL_IDS:
            ALLOWED_CHANNEL_IDS.remove(channel_to_remove)
            save_allowed_channel_ids(collection, ALLOWED_CHANNEL_IDS)
            await message.reply(f"Channel {channel_to_remove} removed from allowed channels.")
        else:
            await message.reply(f"Channel {channel_to_remove} is not in the allowed channels list.")
    except (IndexError, ValueError):
        await message.reply("Please provide a valid channel ID.")

@bot.on_message(filters.command("show_channels") & auth_or_owner_filter)
async def show_channels(client: Client, message: Message):
    if ALLOWED_CHANNEL_IDS:
        channels_list = "\n".join(map(str, ALLOWED_CHANNEL_IDS))
        await message.reply(f"Allowed channels:\n{channels_list}")
    else:
        await message.reply("No channels are currently allowed.")


# Add Chat Callback
@bot.on_callback_query(filters.regex("add_chat") & auth_or_owner_filter)
async def add_chat_callback(client: Client, query: CallbackQuery):
    await query.message.reply_text("Send me the Telegram post link of the channel where you want to use the bot:")
    input_msg = await client.listen(query.message.chat.id)
    await handle_add_chat(client, input_msg, query.message)

# Add Chat Command
@bot.on_message(filters.command("add_chat") & auth_or_owner_filter)
async def add_chat_command(client: Client, message: Message):
    await message.delete()
    editable = await message.reply_text("Send me the Telegram post link of the channel where you want to use the bot:")
    input_msg = await client.listen(editable.chat.id)
    await handle_add_chat(client, input_msg, editable)

# Handler to process the chat link
async def handle_add_chat(client: Client, input_msg: Message, original_msg: Message):
    global ALLOWED_CHANNEL_IDS

    url = input_msg.text
    await input_msg.delete()
    await original_msg.delete()

    # Extract chat ID from Telegram post link
    chat_id_match = re.search(r't\.me\/(?:c\/)?(\d+)', url)
    if chat_id_match:
        chat_id = chat_id_match.group(1)
        new_channel_id = int("-100" + chat_id)
    else:
        await original_msg.reply("Invalid Telegram post link.")
        return

    try:
        if new_channel_id not in ALLOWED_CHANNEL_IDS:
            ALLOWED_CHANNEL_IDS.append(new_channel_id)
            save_allowed_channel_ids(collection, ALLOWED_CHANNEL_IDS)
            await original_msg.reply(f"Channel {new_channel_id} added to allowed channels.")
        else:
            await original_msg.reply(f"Channel {new_channel_id} is already in the allowed channels list.")
    except (IndexError, ValueError) as e:
        await original_msg.reply(f"An error occurred while processing the channel ID: {str(e)}. Please try again.")

# Remove chat command handler
@bot.on_message(filters.command("remove_chat") & auth_or_owner_filter)
async def remove_channel(client: Client, message: Message):
    global ALLOWED_CHANNEL_IDS
    await message.delete()
    editable = await message.reply_text("Send Me The post link of The Channel to remove it from Allowed Channel List: ")
    input_msg = await client.listen(editable.chat.id)
    url = input_msg.text
    await input_msg.delete()
    await editable.delete()
    
    # Extract chat ID from Telegram post link
    chat_id_match = re.search(r't\.me\/(?:c\/)?(\d+)', url)
    if chat_id_match:
        chat_id = chat_id_match.group(1)
        channel_to_remove = int("-100" + chat_id)
    else:
        await message.reply("Invalid Telegram post link.")
        return
    
    try:
        if channel_to_remove in ALLOWED_CHANNEL_IDS:
            ALLOWED_CHANNEL_IDS.remove(channel_to_remove)
            save_allowed_channel_ids(collection, ALLOWED_CHANNEL_IDS)
            await message.reply(f"Channel {channel_to_remove} removed from allowed channels.")
        else:
            await message.reply(f"Channel {channel_to_remove} is not in the allowed channels list.")
    except (IndexError, ValueError):
        await message.reply("Please provide a valid channel ID.")

# Define the /watermark command handler
@bot.on_message(filters.command("watermark") & auth_or_owner_filter)
async def watermark_command(client: Client, message: Message):
    global overlay
    chat_id = message.chat.id
    editable = await message.reply("To set the Watermark upload an image or send `df` for default use")
    input_msg = await client.listen(chat_id)
    if input_msg.photo:
        overlay_path = await input_msg.download()
        if has_transparency(overlay_path):
            overlay = overlay_path
        else:
            overlay = await convert_to_png(overlay_path)
    if input_msg.document:
        document = input_msg.document
        if document.mime_type == "image/png":
            overlay_path = await input_msg.download(file_name=document.file_name)
            overlay = overlay_path
        else:
            await editable.edit("Please upload a .png file for the watermark.")
            await input_msg.delete()
            return    
    else:
        raw_text = input_msg.text
        if raw_text == "df":
            overlay = "watermark.png"
        elif raw_text.startswith("http://") or raw_text.startswith("https://"):
            getstatusoutput(f"wget '{raw_text}' -O 'raw_text.jpg'")
            overlay = "raw_text.jpg"
        else:
            overlay = None 
    await input_msg.delete()
    await editable.edit(f"Watermark set to: {overlay}")

# Function to check if an image has transparency
def has_transparency(image_path):
    # Implement logic to check for transparency
    # For example, using PIL library:
    from PIL import Image
    try:
        image = Image.open(image_path)
        if image.mode == "RGBA":
            return True
    except Exception as e:
        print(f"Error: {e}")
    return False

# Function to convert image to PNG format
async def convert_to_png(image_path):
    # Implement logic to convert image to PNG format
    # For example, using PIL library:
    from PIL import Image
    try:
        image = Image.open(image_path)
        # Create a new image with an alpha channel (transparency)
        new_image = Image.new("RGBA", image.size)
        new_image.paste(image, (0, 0), image)
        # Save the image as PNG
        png_path = image_path.replace(".jpg", ".png")
        new_image.save(png_path)
        return png_path
    except Exception as e:
        print(f"Error: {e}")
        return None

@bot.on_message(filters.command("logs") & filters.create(owner_filter))
async def send_logs(client: Client, message: Message):
    logs = get_last_two_minutes_logs()
    if logs:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as temp_file:
            temp_file.write("".join(logs).encode('utf-8'))
            temp_file_path = temp_file.name
        
        await client.send_document(
            chat_id=message.chat.id,
            document=temp_file_path,
            file_name="Heroku_logs.txt"
        )
        os.remove(temp_file_path)
    else:
        await message.reply_text("No logs found for the last two minutes.")

@bot.on_message(filters.command("accept_logs") & filters.create(owner_filter))
async def accept_logs_command(client: Client, message: Message):
    global accept_logs
    chat_id = message.chat.id
    editable = await message.reply("Hey If You Want Accept The Logs send `df` Otherwise `no`")
    input_msg = await client.listen(chat_id)
    if input_msg.text.strip() == 'df':
        accept_logs = 1  
    else:
        accept_logs = 0
    save_accept_logs(collection, accept_logs)
    await input_msg.delete()
    await editable.edit(f"Accept logs set to: {accept_logs}")

@bot.on_message(filters.command("name") & auth_or_owner_filter)
async def set_name(client: Client, message: Message):
    global my_name
    try:
        my_name = message.text.split(maxsplit=1)[1]  # Extract the name from the message
        save_name(collection, my_name)  # Save the name to the database
        await message.reply(f"Name updated to {my_name}.")
    except IndexError:
        await message.reply("Please provide a name.")

#====================== START COMMAND ======================
class Data:
    START = (
        "🌟 𝗪𝗘𝗟𝗖𝗢𝗠𝗘 {0}! 🌟\n\n"
    )
# Define the start command handler
@bot.on_message(filters.command("start"))
async def start(client: Client, msg: Message):
    user = await client.get_me()
    mention = user.mention
    start_message = await client.send_message(
        msg.chat.id,
        Data.START.format(msg.from_user.mention)
    )

    await asyncio.sleep(1)
    await start_message.edit_text(
        Data.START.format(msg.from_user.mention) +
        "Initializing Uploader bot... 🤖\n\n"
        "Progress: [🤍🤍🤍🤍🤍🤍🤍🤍🤍🤍] 0%\n\n"
    )

    await asyncio.sleep(1)
    await start_message.edit_text(
        Data.START.format(msg.from_user.mention) +
        "Loading features... ⏳\n\n"
        "Progress: [🩵🩵🩵🤍🤍🤍🤍🤍🤍🤍] 25%\n\n"
    )
    
    await asyncio.sleep(1)
    await start_message.edit_text(
        Data.START.format(msg.from_user.mention) +
        "This may take a moment, sit back and relax! 😊\n\n"
        "Progress: [🩵🩵🩵🩵🩵🤍🤍🤍🤍🤍] 50%\n\n"
    )

    await asyncio.sleep(1)
    await start_message.edit_text(
        Data.START.format(msg.from_user.mention) +
        "Checking subscription status... 🔍\n\n"
        "Progress: [🩵🩵🩵🩵🩵🩵🩵🤍🤍🤍] 75%\n\n"
    )

    await asyncio.sleep(1)
    if msg.from_user.id in authorized_users:
        await start_message.edit_text(
            Data.START.format(msg.from_user.mention) +
            "Great!, You are a 𝗣𝗥𝗘𝗠𝗜𝗨𝗠 member! 🌟 press `/help` in order to use me properly\n\n",
            reply_markup=help_button_keyboard
        )
    else:
        await asyncio.sleep(2)
        await start_message.edit_text(
            Data.START.format(msg.from_user.mention) +
            "You are currently using the 𝗙𝗥𝗘𝗘 version. 🆓\n\n"
            "I'm here to make your life easier by downloading videos from your **.txt** file 📄 and uploading them directly to Telegram!\n\n"
            "Want to get started? 𝗣𝗥𝗘𝗦𝗦 /id\n\n💬 Contact @Bhandara_2_O to get the 𝗦𝗨𝗕𝗦𝗖𝗥𝗜𝗣𝗧𝗜𝗢𝗡 🎫 and unlock the full potential of your new bot! 🔓"
        )


@bot.on_message(filters.command("stop"))
async def stop_handler(_, message):
    global bot_running, start_time
    if bot_running:
        bot_running = False
        start_time = None
        await message.reply_text("**𝗦𝗧𝗢𝗣𝗣𝗘𝗗**🚦", True)
        os.execl(sys.executable, sys.executable, *sys.argv)
    else:
        await message.reply_text("Bot is 𝗡𝗢𝗧 running.", True)


@bot.on_message(filters.command("check") & filters.create(owner_filter))
async def owner_command(bot: Client, message: Message):
    global OWNER_TEXT
    await message.reply_text(OWNER_TEXT)


# Help command handler
@bot.on_message(filters.command("help") & auth_owner_channel_filter)
async def help_command(client: Client, message: Message):
    await message.reply(help_text, reply_markup=keyboard)


#=================== TELEGRAM ID INFORMATION =============

@bot.on_message(filters.private & filters.command("info"))
async def info(bot: Client, update: Message):
    
    text = f"""--**Information**--

**🙋🏻‍♂️ First Name :** {update.from_user.first_name}
**🧖‍♂️ Your Second Name :** {update.from_user.last_name if update.from_user.last_name else 'None'}
**🧑🏻‍🎓 Your Username :** {update.from_user.username}
**🆔 Your Telegram ID :** {update.from_user.id}
**🔗 Your Profile Link :** {update.from_user.mention}"""
    
    await update.reply_text(        
        text=text,
        disable_web_page_preview=True,
        reply_markup=BUTTONS
    )


@bot.on_message(filters.private & filters.command("id"))
async def id(bot: Client, update: Message):
    if update.chat.type == "channel":
        await update.reply_text(
            text=f"**This Channel's ID:** {update.chat.id}",
            disable_web_page_preview=True
        )
    else:
        await update.reply_text(        
            text=f"**Your Telegram ID :** {update.from_user.id}",
            disable_web_page_preview=True,
            reply_markup=BUTTONS
        )  

#==========================  YOUTUBE EXTRACTOR =======================

@bot.on_message(filters.command('youtube') & auth_or_owner_filter)
async def run_bot(client: Client, message: Message):
    await message.delete()
    editable = await message.reply_text("Enter the YouTube Webpage URL And I will extract it into .txt file: ")
    input_msg = await client.listen(editable.chat.id)
    youtube_url = input_msg.text
    await input_
