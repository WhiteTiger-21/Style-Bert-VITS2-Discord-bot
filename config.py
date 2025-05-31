# config.py
import os
from pathlib import Path
from dotenv import load_dotenv
import nltk
from style_bert_vits2.nlp.japanese.user_dict import update_dict
import json

load_dotenv()

# --- Project Root ---
ROOT_DIR = Path(__file__).resolve().parent

# --- Paths ---
ASSETS_ROOT = ROOT_DIR / "model_assets"
BERT_CACHE_PATH = os.getenv("BERT_CACHE", str(ROOT_DIR / ".bert_cache"))
MODEL_INFO_JSON_PATH = os.getenv(
    "MODEL_INFO_JSON", str(ROOT_DIR / "model_info.json"))
USER_INFO_JSON_PATH = os.getenv(
    "USER_INFO_JSON", str(ROOT_DIR / "user_info.json"))
SERVER_INFO_JSON_PATH = os.getenv(
    "SERVER_INFO_JSON", str(ROOT_DIR / "server_info.json"))
DICT_CSV_PATH = Path(
    os.getenv("DICT_CSV", str(ROOT_DIR / "dict_data/default.csv")))
COMPILED_DICT_PATH = ROOT_DIR / "dict_data/user.dic"

# --- Discord Settings ---
VC_TEXT_CHANNEL_NAME = os.getenv('VC_TEXT_CHANNEL', 'vc-text')
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
AUTO_JOIN_VC_NAME = os.getenv("AUTO_JOIN_VOICE_CHANNEL_NAME")

# --- NLTK ---
try:
    nltk.data.find('taggers/averaged_perceptron_tagger_eng')
except LookupError:
    print("Downloading NLTK's averaged_perceptron_tagger_eng...")
    nltk.download('averaged_perceptron_tagger_eng')

# --- JTalk Dictionary Update ---


def initialize_jtalk_dictionary():
    os.makedirs(DICT_CSV_PATH.parent, exist_ok=True)
    if not DICT_CSV_PATH.exists():
        print(
            f"Warning: Dictionary CSV not found at {DICT_CSV_PATH}, creating an empty one.")
        with open(DICT_CSV_PATH, "w", encoding="utf-8") as f:
            # Optionally write a header if pyopenjtalk expects one for an empty file
            pass

    print(
        f"Updating JTalk dictionary: {DICT_CSV_PATH} -> {COMPILED_DICT_PATH}")
    update_dict(
        default_dict_path=DICT_CSV_PATH,
        compiled_dict_path=COMPILED_DICT_PATH
    )

# --- JSON Load/Save Utilities ---


def load_json_file(file_path_str: str, default_data=None):
    try:
        with open(file_path_str, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default_data if default_data is not None else {}


def save_json_file(file_path_str: str, data):
    try:
        with open(file_path_str, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except IOError as e:
        print(f"Error saving JSON to {file_path_str}: {e}")
