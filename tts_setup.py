# tts_setup.py
import os
import json
import torch
from pathlib import Path
import asyncio  # For semaphore

from style_bert_vits2.nlp import bert_models
from style_bert_vits2.constants import Languages
from style_bert_vits2.tts_model import TTSModel

import config  # Import our config module

# --- Global TTS Variables (initialized by functions) ---
models = {}
generation_semaphore = asyncio.Semaphore(1)
is_cuda_available = "cuda" if torch.cuda.is_available() else "cpu"
# is_cuda_available = "cpu" # For testing


def load_all_bert_models():
    """Loads all necessary BERT models and tokenizers."""
    print(f"Using device for TTS: {is_cuda_available}")
    os.makedirs(config.BERT_CACHE_PATH, exist_ok=True)
    bert_models.load_model(
        Languages.JP,
        "ku-nlp/deberta-v2-large-japanese-char-wwm",
        str(config.BERT_CACHE_PATH)  # Ensure it's a string
    )
    bert_models.load_tokenizer(
        Languages.JP,
        "ku-nlp/deberta-v2-large-japanese-char-wwm",
        str(config.BERT_CACHE_PATH)
    )
    bert_models.load_model(
        Languages.EN,
        "microsoft/deberta-v3-large",
        str(config.BERT_CACHE_PATH)
    )
    bert_models.load_tokenizer(
        Languages.EN,
        "microsoft/deberta-v3-large",
        str(config.BERT_CACHE_PATH)
    )


def load_tts_models():
    """Loads Style-Bert-VITS2 models based on model_info.json."""
    global models  # Modifying the global models dictionary

    os.makedirs(config.ASSETS_ROOT, exist_ok=True)

    try:
        with open(config.MODEL_INFO_JSON_PATH) as f:
            model_infos_json = json.load(f)
    except FileNotFoundError:
        print(
            f"Error: Model info file not found at {config.MODEL_INFO_JSON_PATH}")
        return
    except json.JSONDecodeError:
        print(
            f"Error: Could not decode JSON from {config.MODEL_INFO_JSON_PATH}")
        return

    for model_name, model_data in model_infos_json.items():
        try:
            model_path = config.ASSETS_ROOT / model_name / model_data["model"]
            config_path = config.ASSETS_ROOT / \
                model_name / model_data["config"]
            style_vec_path = config.ASSETS_ROOT / \
                model_name / model_data["style"]

            if not model_path.exists():
                print(
                    f"Warning: Model file for {model_name} not found at {model_path}")
                continue
            if not config_path.exists():
                print(
                    f"Warning: Config file for {model_name} not found at {config_path}")
                continue
            if not style_vec_path.exists():
                print(
                    f"Warning: Style vector file for {model_name} not found at {style_vec_path}")
                continue

            model_instance = TTSModel(
                model_path=model_path,
                config_path=config_path,
                style_vec_path=style_vec_path,
                device=is_cuda_available,
            )
            models[model_name] = {
                "model": model_instance,
                # Use .get for safety
                "language": model_data.get("language", None)
            }
            print(f"Loaded TTS model: {model_name}")
        except KeyError as e:
            print(
                f"Error loading model {model_name}: Missing key {e} in model_info.json or file structure.")
        except Exception as e:
            print(
                f"An unexpected error occurred while loading model {model_name}: {e}")

    if not models:
        print("Warning: No TTS models were loaded. TTS functionality will be unavailable.")


def get_available_model_names():
    return list(models.keys())

# --- Initialization ---
# These functions should be called once at startup, e.g., in main.py


def initialize_tts_system():
    load_all_bert_models()
    load_tts_models()
