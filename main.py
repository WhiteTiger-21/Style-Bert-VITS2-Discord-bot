# main.py
import discord
from discord.ext import commands
import asyncio
import os # For getenv if DISCORD_TOKEN is not in config for some reason

# --- Project specific imports ---
import config
import tts_setup
import tts_processing
import bot_commands
from style_bert_vits2.constants import Languages # For direct use in handle_tts_message

# --- Bot Setup ---
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True # Essential for on_voice_state_update

bot = commands.Bot(command_prefix='!', intents=intents)

# --- Global state for queues (managed by guild ID) ---
# These dictionaries will hold asyncio.Queue objects for each guild
playback_queues = {} # For TTS generation tasks
play_queues = {}     # For audio playback tasks
guild_tts_tasks = {} # To keep track of running queue processor tasks

def ensure_guild_queues_and_tasks(guild: discord.Guild):
    """Initializes queues and processing tasks for a guild if not already present."""
    guild_id = guild.id
    if guild_id not in playback_queues:
        playback_queues[guild_id] = asyncio.Queue()
        play_queues[guild_id] = asyncio.Queue()
        
        # Start processor tasks for this guild
        # Store tasks to potentially manage them later (e.g., on bot shutdown or guild leave)
        gen_task = bot.loop.create_task(tts_processing.tts_queue_processor(guild_id, playback_queues, play_queues))
        play_task = bot.loop.create_task(tts_processing.play_queue_processor(guild_id, play_queues))
        guild_tts_tasks[guild_id] = (gen_task, play_task)
        print(f"Initialized TTS queues and tasks for guild: {guild.name} ({guild_id})")


# --- Event Handlers ---
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} ({bot.user.id})')
    print(f"Discord.py version: {discord.__version__}")
    print(f"Connected to {len(bot.guilds)} guild(s).")
    
    if not tts_setup.models: # Check if models are loaded
        print("TTS system not yet initialized. Initializing now...")
        tts_setup.initialize_tts_system() # Load BERT, VITS models, and JTalk dict
    else:
        print("TTS system already initialized.")

    for guild in bot.guilds:
        ensure_guild_queues_and_tasks(guild)
    print("Bot is ready and listening.")

@bot.event
async def on_guild_join(guild: discord.Guild):
    """Handles when the bot joins a new guild after it's already running."""
    print(f"Joined new guild: {guild.name} ({guild.id})")
    ensure_guild_queues_and_tasks(guild)

@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    if member.id == bot.user.id: # Ignore bot's own state changes
        return

    voice_client = member.guild.voice_client
    guild = member.guild
    
    designated_channel = discord.utils.get(guild.voice_channels, name=config.AUTO_JOIN_VC_NAME)
    if not designated_channel: # discord.utils.get for voice_channels already ensures it's a VoiceChannel
        print(f"DEBUG: Voice channel named '{config.AUTO_JOIN_VC_NAME}' not found in guild {guild.name}.")
    
    # User leaves a voice channel the bot is in
    if before.channel and not after.channel: # User disconnected from a channel

        if before.channel.members.__len__() == 0:  # If no members left in the channel
            server_info = config.load_json_file(config.SERVER_INFO_JSON_PATH, {})
            server_id = str(guild.id)
            if server_id not in server_info:
                server_info[server_id] = {}
            server_info[server_id]["auto_join"] = True # Set auto-join to True
            server_info[server_id]["talking"] = True # Set talking to True
            config.save_json_file(config.SERVER_INFO_JSON_PATH, server_info)

        if voice_client and voice_client.channel == before.channel:
            # Check if bot is alone in the channel
            # Non-bot members in the channel:
            human_members = [m for m in before.channel.members if not m.bot]
            if not human_members: # If list is empty, bot is alone
                print(f"Last user left {before.channel.name}. Disconnecting bot.")
                await voice_client.disconnect()
                # Note: Queues and tasks for this guild are not stopped/cleared here.
                # They will persist and resume if the bot rejoins a VC.
                # If you want to clear/stop them, that logic would go here.

    auto_joined = config.load_json_file(config.SERVER_INFO_JSON_PATH, {}).get(str(guild.id), {}).get("auto_join", True) == True
    # Auto-join logic (optional, can be complex to get right)
    # This is a very simple auto-join if a user enters a channel and the bot is not connected.
    # Consider making this configurable or command-driven.
    if auto_joined:
        if after.channel and not voice_client:  # User joined a channel, bot is not in any VC
            if after.channel.id == designated_channel.id and isinstance(after.channel, discord.VoiceChannel) and any(not m.bot for m in after.channel.members):
                try:
                    print(f"User {member.display_name} joined {after.channel.name}. Bot auto-joining.")
                    await after.channel.connect()
                except discord.ClientException as e:
                    print(f"Error auto-joining voice channel: {e}")

    vc = member.guild.voice_client
    if not tts_setup.models:
        print("TTS models not loaded, cannot process TTS message.")
        return
    user_prefs = config.load_json_file(config.USER_INFO_JSON_PATH, {}).get(str(member.id), {})
    member_name = user_prefs.get("nickname", member.display_name)
    # Determine model for the user
    model_name = user_prefs.get("model")
    if not model_name or model_name not in tts_setup.models:
        available_models = tts_setup.get_available_model_names()
        if available_models:
            model_name = available_models[0] # Default to first available
        else:
            print("No TTS models available to process message.")
            return

    selected_model_data = tts_setup.models[model_name]
    tts_model_instance = selected_model_data["model"]
    model_lang_pref = selected_model_data.get("language") # e.g. "JP"

    is_talking = config.load_json_file(config.SERVER_INFO_JSON_PATH, {}).get(str(member.guild.id), {}).get("talking", True)
    if is_talking and vc:
        if before.channel is None and after.channel is not None:
            lang_for_name = await tts_processing.determine_language_for_tts(member_name, model_lang_pref)
            playback_queues[member.guild.id].put_nowait({
                "text": member_name, "language": lang_for_name,
                "voice_client": vc, "model_instance": tts_model_instance
            })
            segment = "が入室しました。"
            lang_for_segment = await tts_processing.determine_language_for_tts(segment, model_lang_pref)
            playback_queues[member.guild.id].put_nowait({
                "text": segment, "language": lang_for_segment,
                "voice_client": vc, "model_instance": tts_model_instance
            })
        elif before.channel is not None and after.channel is None:
            lang_for_name = await tts_processing.determine_language_for_tts(member_name, model_lang_pref)
            playback_queues[member.guild.id].put_nowait({
                "text": member_name, "language": lang_for_name,
                "voice_client": vc, "model_instance": tts_model_instance
            })
            segment = "が退室しました。"
            lang_for_segment = await tts_processing.determine_language_for_tts(segment, model_lang_pref)
            playback_queues[member.guild.id].put_nowait({
                "text": segment, "language": lang_for_segment,
                "voice_client": vc, "model_instance": tts_model_instance
            })


@bot.event
async def on_message(message: discord.Message):
    """Handles incoming messages for commands and TTS submissions."""

    is_talking = config.load_json_file(config.SERVER_INFO_JSON_PATH, {}).get(str(message.author.guild.id), {}).get("talking", True)

    if message.author.bot:
        return

    # TTS processing only for configured channel, commands can be from anywhere (or also restricted)
    is_tts_channel = (message.channel.name == config.VC_TEXT_CHANNEL_NAME)
    content = message.content.strip()

    if content.startswith(';'): # Original ignore prefix
        return

    if content.startswith(bot.command_prefix):
        command_string = content[len(bot.command_prefix):]
        await bot_commands.process_command(message, command_string)
    elif is_tts_channel and is_talking:  # Only process non-commands for TTS if in the designated channel
        await handle_tts_submission(message, content)


async def handle_tts_submission(message: discord.Message, text_content: str):
    """Handles non-command messages for TTS submission to the queue."""
    vc = message.guild.voice_client
    if not vc or not vc.is_connected():
        # Silently ignore or send a message:
        # await message.channel.send("ボイスチャンネルに接続していません。", delete_after=10)
        return

    if not tts_setup.models:
        print("TTS models not loaded, cannot process TTS message.")
        return

    user_prefs = config.load_json_file(config.USER_INFO_JSON_PATH, {}).get(str(message.author.id), {})
    
    # Determine model for the user
    model_name = user_prefs.get("model")
    if not model_name or model_name not in tts_setup.models:
        available_models = tts_setup.get_available_model_names()
        if available_models:
            model_name = available_models[0] # Default to first available
        else:
            print("No TTS models available to process message.")
            return

    selected_model_data = tts_setup.models[model_name]
    tts_model_instance = selected_model_data["model"]
    model_lang_pref = selected_model_data.get("language", None) # e.g. "JP"

    # Read user's name?
    if user_prefs.get("call", True): # Default to true if not set
        author_name = user_prefs.get("nickname", message.author.display_name)
        
        lang_for_name = await tts_processing.determine_language_for_tts(author_name, model_lang_pref)
        playback_queues[message.guild.id].put_nowait({
            "text": author_name, "language": lang_for_name,
            "voice_client": vc, "model_instance": tts_model_instance
        })

    # Process message content: URL, length limits, splitting
    is_url = "http://" in text_content or "https://" in text_content
    
    segments_to_say = []
    is_omitted = False

    if is_url:
        segments_to_say.append("URL")
        model_lang_pref = Languages.JP # Default to Japanese for URLs
    else:
        remaining_text = text_content
        
        # --- Truncation (Overall 140 chars limit) ---
        if len(remaining_text) > 140:
            # Find a good cut point around 100-140 for truncation
            # This truncation happens *before* further splitting.
            # If you want splitting first, then truncation of the total, the logic would differ.
            # Current logic: truncate the whole message if it's very long.
            trunc_cut_point = -1
            # Prefer sentence/clause enders for truncation
            for sep in ['。', '。', '\n', '.', '!', '?', '、', ',', ' ','　']: # Added more separators
                # Search in a reasonable range from the end of 140 chars, e.g., 100-140
                idx = remaining_text.rfind(sep, 100, 140) 
                if idx != -1:
                    # Ensure we take the separator as well if it makes sense
                    trunc_cut_point = max(trunc_cut_point, idx + len(sep)) 
            
            if trunc_cut_point == -1 and len(remaining_text) > 140: # Force cut if no good separator
                trunc_cut_point = 140
            
            if trunc_cut_point > 0 and trunc_cut_point < len(remaining_text):
                remaining_text = remaining_text[:trunc_cut_point].strip()
                is_omitted = True
            elif len(remaining_text) > 140: # If rfind didn't find anything or cut point is too large
                remaining_text = remaining_text[:140].strip()
                is_omitted = True


        # --- Splitting into segments of approx. 30-50 characters ---
        # Target length for segments
        TARGET_SEGMENT_LENGTH = 35 # Around 30-40
        MIN_SEGMENT_LENGTH = 20    # Minimum length to look for a separator
        MAX_SEGMENT_LENGTH = 50    # Maximum length if no good separator

        while len(remaining_text) > 0:
            if len(remaining_text) <= MAX_SEGMENT_LENGTH: # If remaining text is short enough
                segments_to_say.append(remaining_text.strip())
                break # Done with splitting

            split_point = -1
            # Try to find a natural break point
            # Search range: MIN_SEGMENT_LENGTH to MAX_SEGMENT_LENGTH
            # Prioritize sentence enders, then clause enders, then spaces
            separators = ['。', '。\n', '\n', '.', '!', '?', '、', ',', ' ', '　'] 
            
            best_sep_point = -1
            # Iterate from right to left within the preferred segment length range
            for i in range(min(len(remaining_text) -1, MAX_SEGMENT_LENGTH -1), MIN_SEGMENT_LENGTH -2, -1):
                char_and_potential_sep = remaining_text[i:i+2] # Check for two-char seps like '。\n'
                if char_and_potential_sep in separators:
                    best_sep_point = i + len(char_and_potential_sep)
                    break
                elif remaining_text[i] in separators:
                    best_sep_point = i + 1
                    break
            
            if best_sep_point != -1:
                segment = remaining_text[:best_sep_point].strip()
                if segment: # Ensure segment is not empty after strip
                    segments_to_say.append(segment)
                remaining_text = remaining_text[best_sep_point:].strip()
            else:
                # No good separator found, force split at MAX_SEGMENT_LENGTH
                # or just take the rest if it's shorter than TARGET but longer than what's left
                segment_to_add = remaining_text[:MAX_SEGMENT_LENGTH].strip()
                if segment_to_add:
                    segments_to_say.append(segment_to_add)
                remaining_text = remaining_text[MAX_SEGMENT_LENGTH:].strip()
        
        # Filter out any empty strings that might have been added
        segments_to_say = [s for s in segments_to_say if s]

    # Add segments to queue
    for segment in segments_to_say:
        if not segment: continue # Should be caught by filter above, but good to double check
        lang_for_segment = await tts_processing.determine_language_for_tts(segment, model_lang_pref)
        playback_queues[message.guild.id].put_nowait({
            "text": segment, "language": lang_for_segment,
            "voice_client": vc, "model_instance": tts_model_instance
        })

    if is_omitted:
        playback_queues[message.guild.id].put_nowait({
            "text": "以下略", "language": Languages.JP,
            "voice_client": vc, "model_instance": tts_model_instance
        })


# --- Bot Run ---
if __name__ == "__main__":
    if not config.DISCORD_TOKEN:
        print("Error: DISCORD_TOKEN environment variable not set or found in config.")
    else:
        try:
            # It's often better to initialize heavy systems like TTS before bot.run()
            # if on_ready initialization has race conditions or isn't guaranteed early enough.
            # However, on_ready is fine if model loading isn't instant and you want the bot
            # to appear online sooner.
            # tts_setup.initialize_tts_system() # Alternative: load models before connecting
            
            print("Starting bot...")
            bot.run(config.DISCORD_TOKEN)
        except discord.PrivilegedIntentsRequired:
            print("Error: Privileged intents (Message Content, Voice States) are not enabled for the bot in the Discord Developer Portal.")
        except Exception as e:
            print(f"An error occurred while running the bot: {e}")
            import traceback
            traceback.print_exc()