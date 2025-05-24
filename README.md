# Style-Bert-VITS2-Discord-bot
A Discord TTS bot powered by Style-Bert-VITS2

このリポジトリは、Style-Bert-VITS2を利用したDiscord向けのTTS（音声読み上げ）Botです。

利用の際は必ず、使用ライブラリおよびデフォルトモデルに関する[お願い](/TERMS_OF_USE.md)をお読みください。

このリポジトリは [Style-Bert-VITS2](https://github.com/litagin02/Style-Bert-VITS2/tree/master) と [discord.py](https://github.com/Rapptz/discord.py) を利用しています。  
Style-Bert-VITS2 は、 [Bert-VITS2](https://github.com/fishaudio/Bert-VITS2) および [VOICEVOX](https://github.com/VOICEVOX/voicevox_engine) を基盤としたライブラリです。

このbotを起動するにはrequirements.txtのライブラリをインストールし、initialize.pyで初期設定を行ってからmain.pyを実行してください。

`initialize.py` を実行すると、以下のファイルが自動生成されます：

- `.env`：環境変数（例：Discord Botのトークンなど）を記載するファイル
- `model_assets/`：Style-Bert-VITS2で使用されるモデルファイル
- `model_info.json`：各モデルに関する情報を記載したファイル

.envにはご自身の環境にあった環境変数(Discord botのTOKENなど)をご記載ください。

Dockerを利用する場合も、`initialize.py` による初期設定が必要です。  
ただし、以下のオプションを付けることで、`requirements.txt` に記載されたライブラリのインストールをスキップできます（モデルは手動で用意してください）：

**しかし、モデルのダウンロードが行われないため、ご自身でダウンロードをお願いします。**

``` sh
python initialize.py --skip_model_dl
```

Dockerのimage構築はご自身でお願いします(約6GBくらいのサイズ)。

``` sh
docker buildx build --network=host -t discord-sbv2 .
```

コンテナの起動はこのディレクトリで以下のコマンドを実行してください。

``` sh
docker run -it --name discord_tts_bot -v ./:/app discord-sbv2
```

---
## References

In addition to the original reference (written below), I used the following repositories:

- Bert-VITS2
- EasyBertVits2

The pretrained model and JP-Extra version is essentially taken from the original base model of Bert-VITS2 v2.1 and JP-Extra pretrained model of Bert-VITS2, so all the credits go to the original author (Fish Audio):

In addition, text/user_dict/ module is based on the following repositories:

- voicevox_engine and the license of this module is LGPL v3.

---
## LICENSE

This repository is licensed under the GNU Affero General Public License v3.0, the same as the original Bert-VITS2 repository. For more details, see LICENSE.

In addition, `style_bert_vits2.nlp.japanese.user_dict` module is licensed under the GNU Lesser General Public License v3.0, inherited from the original VOICEVOX engine repository. For more details, see LGPL_LICENSE.