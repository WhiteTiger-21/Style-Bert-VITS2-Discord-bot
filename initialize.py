from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent

import argparse
import argparse

parser = argparse.ArgumentParser(description='Initialize the TTS bot')
parser.add_argument(
    '-n', '--skip_model_dl',
    help='Skip downloading the default model (useful if you already have the model and want to avoid installing extra libraries)',
    action='store_true'
)
args = parser.parse_args()

if args.skip_model_dl:
    print("Skip model download")
    from huggingface_hub import hf_hub_download


    model_file = "jvnv-F1-jp/jvnv-F1-jp_e160_s14000.safetensors"
    config_file = "jvnv-F1-jp/config.json"
    style_file = "jvnv-F1-jp/style_vectors.npy"

    for file in [model_file, config_file, style_file]:
        print(file)
        hf_hub_download("litagin/style_bert_vits2_jvnv", file, local_dir="model_assets")


with open(f"{ROOT_DIR}/.env", mode='w') as f:
    settings = [
        "DISCORD_TOKEN=GET_YOUR_BOT_TOKEN",
        "VC_TEXT_CHANNEL=vc-text",
        "MODEL_INFO_JSON=./model_info.json",
        "PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True",
        "DICT_CSV=./dict_data/default.csv",
        "USER_INFO_JSON=./user_setting.json",
        "BERT_CACHE=./.bert_cache",
        "AUTO_JOIN_VOICE_CHANNEL_NAME=General"
        ]    
    f.write("\n".join(settings))


import json

model_info = {"jvnv-F1-jp":
              {"model": "jvnv-F1-jp_e160_s14000.safetensors",
               "config": "config.json",
               "style": "style_vector.npy",
               "language": "JP"}
                }

with open(f"{ROOT_DIR}/model_info.json", 'w', encoding='utf-8') as f:
    json.dump(model_info, f, indent=4, ensure_ascii=False)