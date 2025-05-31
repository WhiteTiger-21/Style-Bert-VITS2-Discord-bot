# bot_commands.py
import discord
import csv
from pathlib import Path

import config # For file paths, JSON helpers
import tts_setup # For models list
import tts_processing # For to_fullwidth (used in set_dict)
from style_bert_vits2.nlp.japanese.user_dict import update_dict # Direct import for updating dict


async def handle_join_command(message: discord.Message):
    """Handles the !join command."""

    server_info = config.load_json_file(config.SERVER_INFO_JSON_PATH, {})
    server_id = str(message.guild.id)
    if server_id not in server_info:
        server_info[server_id] = {}
    server_info[server_id]["auto_join"] = True
    config.save_json_file(
        config.SERVER_INFO_JSON_PATH,
        server_info
    )
    if not message.author.voice:
        await message.channel.send("ボイスチャンネルに参加してからコマンドを実行してください。")
        return
    
    channel = message.author.voice.channel
    if not isinstance(channel, discord.VoiceChannel):
        await message.channel.send("有効なボイスチャンネルに接続していません。")
        return

    if message.guild.voice_client and message.guild.voice_client.is_connected():
        if message.guild.voice_client.channel == channel:
            await message.channel.send(f"既にボイスチャンネル `{channel.name}` に参加しています。")
        else:
            await message.guild.voice_client.move_to(channel)
            await message.channel.send(f"ボイスチャンネル `{channel.name}` に移動しました。")
    else:
        try:
            await channel.connect()
            await message.channel.send(f"ボイスチャンネル `{channel.name}` に参加しました。")
        except discord.ClientException as e:
            await message.channel.send(f"ボイスチャンネルへの参加に失敗しました: {e}")
        except Exception as e:
            await message.channel.send(f"予期せぬエラーで参加に失敗しました: {e}")


async def handle_leave_command(message: discord.Message):
    """Handles the !leave command."""

    server_info = config.load_json_file(config.SERVER_INFO_JSON_PATH, {})
    server_id = str(message.guild.id)
    if server_id not in server_info:
        server_info[server_id] = {}
    
    server_info[server_id]["auto_join"] = False  # Disable auto-join
    config.save_json_file(
        config.SERVER_INFO_JSON_PATH,
        server_info
    )
    if message.guild.voice_client and message.guild.voice_client.is_connected():
        await message.guild.voice_client.disconnect()
        await message.channel.send("ボイスチャンネルから退出しました。")
    else:
        await message.channel.send("ボイスチャンネルに参加していません。")


async def _set_user_preference(user_id: str, key: str, value):
    """Helper to update user preferences in USER_INFO_JSON."""
    user_info = config.load_json_file(config.USER_INFO_JSON_PATH, {})
    if user_id not in user_info:
        user_info[user_id] = {}
    user_info[user_id][key] = value
    config.save_json_file(config.USER_INFO_JSON_PATH, user_info)


async def handle_set_dict_command(message: discord.Message, key: str, value: str):
    """Handles !set dict <key> <value>."""
    if not key or not value:
        await message.channel.send(";キーとバリューを両方指定してください。(例: !set dict 単語 ヨミ)")
        return

    if not all('\u30A0' <= char <= '\u30FF' for char in value): # Value must be Katakana
        await message.channel.send(";バリューは全角カタカナで入力してください。")
        return
        
    key_fw = tts_processing.to_fullwidth(key)
    try:
        # Ensure the CSV file exists and is writable
        dict_p = config.DICT_CSV_PATH
        dict_p.parent.mkdir(parents=True, exist_ok=True)

        with open(dict_p, 'a', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            # surface,left_id,right_id,cost,pos1,pos2,pos3,pos4,pos5,pos6,surface_form,yomi,pron,accent_type,mora_len
            # This structure matches common user dictionary formats for pyopenjtalk.
            writer.writerow([
                key_fw, '', '', '8609', '名詞', '固有名詞', '一般', '*', '*', '*',
                key_fw, value, value, '0/0', '*' # Default accent, mora length can be auto
            ])
        
        update_dict(
            default_dict_path=dict_p,
            compiled_dict_path=config.COMPILED_DICT_PATH
        )
        await message.channel.send(f";辞書に `{key_fw}`: `{value}` を追加しました。")
    except Exception as e:
        await message.channel.send(f";辞書への追加中にエラーが発生しました: {e}")
        print(f"Error updating dictionary: {e}")


async def handle_set_voice_command(message: discord.Message, model_name_to_set: str):
    """Handles !set voice <model_name>."""
    if not model_name_to_set:
        await message.channel.send(";`!set voice` コマンドにはモデル名が必要です。")
        return

    available_models = tts_setup.get_available_model_names()
    if model_name_to_set in available_models:
        await _set_user_preference(str(message.author.id), "model", model_name_to_set)
        await message.channel.send(f";あなたのボイスモデルを `{model_name_to_set}` に設定しました。")
    else:
        if not available_models:
            await message.channel.send(";現在利用可能なボイスモデルがありません。")
        else:
            voice_output = ";指定されたモデルが見つかりません。利用可能なボイスモデル:\n" + "\n".join(
                [f";  `{m}`" for m in available_models]
            )
            await message.channel.send(voice_output)


async def handle_set_call_command(message: discord.Message, call_setting_str: str):
    """Handles !set call <true|false>."""
    if not call_setting_str:
        await message.channel.send(";`!set call` コマンドには true または false が必要です。")
        return
    
    call_setting_lower = call_setting_str.lower()
    if call_setting_lower not in ['true', 'false']:
        await message.channel.send(";`!set call` コマンドには true または false を指定してください。")
        return
        
    await _set_user_preference(str(message.author.id), "call", call_setting_lower == 'true')
    await message.channel.send(f";あなたの名前の読み上げ設定を `{call_setting_lower}` に設定しました。")


async def handle_set_nickname_command(message: discord.Message, nickname_to_set: str):
    """Handles !set nickname <str>."""
    if not nickname_to_set:
        await message.channel.send(";`!set nkackname` コマンドには nickname (str) が必要です。")
        return
        
    await _set_user_preference(str(message.author.id), "nickname", nickname_to_set)
    await message.channel.send(f";あなたの名前の読み上げ設定を `{nickname_to_set}` に設定しました。")


async def handle_set_talk_command(message: discord.Message, talk_setting_str: str):
    """Handles !set talking <true|false>."""
    if not talk_setting_str:
        await message.channel.send(";`!set talking` コマンドには true または false が必要です。")
        return

    talk_setting_lower = talk_setting_str.lower()
    if talk_setting_lower not in ['true', 'false']:
        await message.channel.send(";`!set talking` コマンドには true または false を指定してください。")
        return

    guild_id = message.guild.id
    
    server_info = config.load_json_file(config.SERVER_INFO_JSON_PATH, {})
    server_id = str(guild_id)
    if server_id not in server_info:
        server_info[server_id] = {}
    server_info[server_id]["talking"] = talk_setting_lower == 'true'
    config.save_json_file(
        config.SERVER_INFO_JSON_PATH,
        server_info
    )
    await message.channel.send(f";発話設定を `{talk_setting_lower}` に設定しました。")


async def handle_get_dict_command(message: discord.Message):
    """Handles !get dict."""
    current_dictionary = {}
    try:
        with open(config.DICT_CSV_PATH, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 12: # surface (idx 0) and yomi (idx 11)
                    current_dictionary[row[0]] = row[11]
    except FileNotFoundError:
        await message.channel.send(";辞書ファイルが見つかりません。")
        return
    except Exception as e:
        await message.channel.send(f";辞書の読み込み中にエラーが発生しました: {e}")
        return

    if not current_dictionary:
        await message.channel.send(";辞書は空です。")
        return

    dict_output_lines = [";現在の辞書内容:"]
    for k, v in current_dictionary.items():
        dict_output_lines.append(f";  `{k}`: `{v}`")
    
    response = ""
    for line in dict_output_lines:
        if len(response) + len(line) + 1 > 2000: # Discord message limit
            await message.channel.send(response)
            response = ""
        response += line + "\n"
    if response:
            await message.channel.send(response)


async def handle_get_nickname_command(message: discord.Message):
    """Handles !get nickname."""
    user_nickname = config.load_json_file(config.USER_INFO_JSON_PATH, {}).get(str(message.author.id), {}).get("nickname",None)
    if user_nickname:
        await message.channel.send(f";あなたのニックネームは `{user_nickname}` です。")
    else:
        await message.channel.send(";現在あなたのニックネームは設定されていません。")


async def handle_get_voice_command(message: discord.Message):
    """Handles !get voice."""
    available_models = tts_setup.get_available_model_names()
    if available_models:
        voice_output = ";利用可能なボイスモデル:\n" + "\n".join(
            [f";  `{m}`" for m in available_models]
        )
        await message.channel.send(voice_output)
    else:
        await message.channel.send(";現在利用可能なボイスモデルはありません。")


async def process_command(message: discord.Message, command_string: str):
    """Main dispatcher for all bot commands."""
    parts = command_string.split(maxsplit=1)
    command_name = parts[0].lower()
    args_str = parts[1] if len(parts) > 1 else ""

    if command_name == 'join':
        await handle_join_command(message)
    elif command_name == 'leave':
        await handle_leave_command(message)
    elif command_name == 'set':
        set_parts = args_str.split(maxsplit=2)
        if len(set_parts) < 1:
            await message.channel.send(";`!set` コマンドにはターゲットを指定してください (dict, voice, call, nickname, talking)。")
            return
        target = set_parts[0].lower()
        key = set_parts[1] if len(set_parts) > 1 else ""
        value = set_parts[2] if len(set_parts) > 2 else ""

        if target == 'dict':
            await handle_set_dict_command(message, key, value)
        elif target == 'voice':
            await handle_set_voice_command(message, key) # key is model_name
        elif target == 'call':
            await handle_set_call_command(message, key) # key is 'true'/'false'
        elif target == 'nickname':
            await handle_set_nickname_command(message, key) # key is nickname
        elif target == 'talking':
            await handle_set_talk_command(message, key) # key is 'true'/'false'
        else:
            await message.channel.send(f";不明な設定ターゲット `{target}` です。")
            
    elif command_name == 'get':
        get_parts = args_str.split(maxsplit=0) # No args needed after 'get <target>'
        if not args_str or not get_parts : # target is args_str itself
             await message.channel.send(";`!get` コマンドにはターゲットを指定してください (dict, voice)。")
             return
        target = args_str.lower() # The first word after 'get' is the target

        if target == 'dict':
            await handle_get_dict_command(message)
        elif target == 'voice':
            await handle_get_voice_command(message)
        elif target == 'nickname':
            await handle_get_nickname_command(message)
        else:
            await message.channel.send(f";不明な取得ターゲット `{target}` です。")
    else:
        await message.channel.send(f";不明なコマンド `{command_name}` です。")