# tts_processing.py
import io
import asyncio
import numpy as np
import soundfile as sf
import torch
import discord
import csv

from style_bert_vits2.constants import Languages
from style_bert_vits2.tts_model import TTSModel # For type hinting

import tts_setup # To access generation_semaphore, is_cuda_available, models
import config # To access DICT_CSV_PATH

# --- Queues (managed per guild in main.py) ---
# These will be populated by main.py: playback_queues[guild_id], play_queues[guild_id]

# --- Text Analysis & Language Determination ---
def to_fullwidth(s: str) -> str:
    """Converts ASCII alphabet to fullwidth for dictionary matching."""
    result = ""
    for char_val in s:
        if 'A' <= char_val <= 'Z':
            result += chr(ord(char_val) - ord('A') + ord('Ａ'))
        elif 'a' <= char_val <= 'z':
            result += chr(ord(char_val) - ord('a') + ord('ａ'))
        else:
            result += char_val
    return result

async def _is_text_in_custom_dict(text: str) -> bool:
    """Checks if any part of the text (converted to fullwidth) is in the custom dictionary."""
    try:
        # This is a synchronous file read. For very large dictionaries or high frequency,
        # consider async file reading or caching the dictionary in memory.
        with open(config.DICT_CSV_PATH, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            text_fw = to_fullwidth(text)
            for row in reader:
                if row and row[0] in text_fw: # row[0] is the surface form
                    return True
    except FileNotFoundError:
        # print(f"Warning: Dictionary file not found at {config.DICT_CSV_PATH} for language check.")
        pass # Fall through if dict not found
    except Exception as e:
        print(f"Error reading dictionary for language check: {e}")
    return False

async def determine_language_for_tts(text: str, model_lang_preference: str = None) -> Languages:
    """
    Determines the language for TTS.
    Priority:
    1. Model's explicit JP preference.
    2. Text found in custom (JP) dictionary.
    3. Heuristic for English vs. Japanese.
    """
    if model_lang_preference == "JP":
        return Languages.JP

    if await _is_text_in_custom_dict(text):
        return Languages.JP
    
    # Basic heuristic: if it contains non-ASCII (excluding common symbols), assume JP.
    # Otherwise, assume EN. This is a simplification.
    is_likely_english = all(ord(c) < 128 for c in text) and \
                        all(c.isalnum() or c in "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~ " for c in text)

    return Languages.EN if is_likely_english else Languages.JP

# --- Audio Generation and Playback ---
async def generate_audio_buffer(text: str, language: Languages, tts_model_instance: TTSModel):
    """Generates audio and returns it as a BytesIO buffer. Runs inference in an executor."""
    loop = asyncio.get_event_loop()
    # text_speed_val = 1.5 # Consider making this configurable per user or model
    
    # Get text speed from model instance if available, else default
    text_speed_val = getattr(tts_model_instance, 'default_length_scale', 1.0)


    def _blocking_generate_and_process():
        # This function contains CPU/GPU-bound operations
        sr, audio_data = tts_model_instance.infer(
            text=text, language=language, length=text_speed_val
        )
        
        # Ensure audio is int16
        if audio_data.dtype != np.int16:
            audio_data_int16 = (audio_data * 32767).astype(np.int16)
        else:
            audio_data_int16 = audio_data
        
        _buffer = io.BytesIO()
        sf.write(_buffer, audio_data_int16, samplerate=sr, format='WAV', subtype='PCM_16')
        _buffer.seek(0)
        
        if tts_setup.is_cuda_available == "cuda":
            torch.cuda.empty_cache() # Clear cache after inference
        return _buffer, sr

    # Use the global generation_semaphore from tts_setup
    async with tts_setup.generation_semaphore:
        buffer, sr = await loop.run_in_executor(
            None, _blocking_generate_and_process # None uses default ThreadPoolExecutor
        )
    return buffer, sr

async def play_audio_from_buffer(buffer: io.BytesIO, sr: int, voice_client: discord.VoiceClient):
    """Plays audio from a BytesIO buffer in a voice channel."""
    if not voice_client or not voice_client.is_connected():
        print("Error: Voice client not connected, cannot play audio.")
        buffer.close() # Ensure buffer is closed if not used
        return

    # Wait if bot is already playing something
    while voice_client.is_playing():
        await asyncio.sleep(0.1)

    audio_source = discord.FFmpegPCMAudio(
        buffer, 
        pipe=True, 
        options=f'-hide_banner -loglevel error -f s16le -ar {sr} -ac 2' # Forcing mono, common for TTS
    )
    
    def after_playing_handler(error):
        if error:
            print(f'Player error: {error}')
        buffer.close() # Close the buffer after playback is done or on error

    voice_client.play(audio_source, after=after_playing_handler)

    # Wait for playback to finish before this function returns,
    # ensuring sequential playback from the play_queue.
    while voice_client.is_playing():
         await asyncio.sleep(0.1)


async def tts_queue_processor(guild_id: int, bot_playback_queues: dict, bot_play_queues: dict):
    """Processes TTS requests from the playback_queue for a guild."""
    gen_queue = bot_playback_queues.get(guild_id)
    play_q = bot_play_queues.get(guild_id)

    if not gen_queue or not play_q:
        print(f"Error: Queues not found for guild {guild_id} in tts_queue_processor.")
        return

    while True:
        try:
            item = await gen_queue.get()
            # print(f"TTS Gen Q (Guild {guild_id}): Processing '{item['text']}'")
            
            buffer, sr = await generate_audio_buffer(
                item["text"], item["language"], item["model_instance"]
            )
            
            await play_q.put({
                "buffer": buffer,
                "sr": sr,
                "voice_client": item["voice_client"]
            })
            # print(f"TTS Gen Q (Guild {guild_id}): Added '{item['text']}' to play queue.")
        except asyncio.CancelledError:
            print(f"TTS generation task for guild {guild_id} cancelled.")
            break # Exit loop if task is cancelled
        except Exception as e:
            print(f"TTS generation error in queue for guild {guild_id}, item '{item.get('text', 'N/A')}': {e}")
        finally:
            if 'gen_queue' in locals() and gen_queue: # Check if gen_queue is defined
                 gen_queue.task_done() # Mark task as done even on error


async def play_queue_processor(guild_id: int, bot_play_queues: dict):
    """Processes audio playback requests from the play_queue for a guild."""
    play_q = bot_play_queues.get(guild_id)

    if not play_q:
        print(f"Error: Play queue not found for guild {guild_id} in play_queue_processor.")
        return

    while True:
        try:
            item = await play_q.get()
            # print(f"Play Q (Guild {guild_id}): Playing audio.")
            await play_audio_from_buffer(item["buffer"], item["sr"], item["voice_client"])
        except asyncio.CancelledError:
            print(f"Audio playback task for guild {guild_id} cancelled.")
            break # Exit loop if task is cancelled
        except discord.errors.ClientException as e:
            print(f"Discord client error during playback for guild {guild_id}: {e}")
            # If buffer is part of item and needs closing on error:
            if 'buffer' in item and hasattr(item['buffer'], 'close'):
                item['buffer'].close()
        except Exception as e:
            print(f"TTS playback error in queue for guild {guild_id}: {e}")
            if 'buffer' in item and hasattr(item['buffer'], 'close'):
                item['buffer'].close()
        finally:
            if 'play_q' in locals() and play_q: # Check if play_q is defined
                play_q.task_done()