# blog-jetson-conveyor-mcp

外部制御端子のない市販のベルトコンベアを、リレーと Arduino UNO を挟んで Jetson から回す・止めるできるようにし、MCP サーバーとして公開するサンプルです。

ブログ記事: <!-- TODO: 記事のURL -->

## 構成

```
MCP クライアント
  └─ HTTP（Bearer 認証）→ Jetson（server.py）
       └─ USB シリアル '1' / '0' → Arduino UNO（relay-onoff.ino）
            └─ D7 → Grove - Relay → 12V ラインを入り切り → モーター
```

| ファイル | 内容 |
| --- | --- |
| `server.py` | MCP サーバー本体（Streamable HTTP、Bearer 認証） |
| `relay_onoff.py` | Arduino とのシリアル通信。単体で手動操作もできる |
| `firmware/relay-onoff/relay-onoff.ino` | Arduino のスケッチ。`1` / `0` を受けてリレーを入り切りし、`ON` / `OFF` を返す |
| `test_server.py`, `test_relay_onoff.py` | テスト（模擬シリアルで動き、実機には接続しない） |
| `schemas/conveyor-mcp-tools.json` | 公開しているツール定義のスナップショット |
| `deploy/` | systemd のユニットファイルと導入スクリプト |

## ツール

| ツール | 動作 |
| --- | --- |
| `start_conveyor()` | `1` を送り、`ON` の応答を確認する。物理的にベルトが動く |
| `stop_conveyor()` | `0` を送り、`OFF` の応答を確認する |
| `get_conveyor_status()` | 最後に受け付けた指令と時刻、fault を返す。シリアル通信はしない |

## セットアップ

1. Arduino に `firmware/relay-onoff/relay-onoff.ino` を書き込む
2. このフォルダを Jetson の `~/conveyor-mcp` に置く
3. `deploy/conveyor-mcp.service` の `<USER>` と `<JETSON_IP>` を書き換える
4. Jetson 上で一般ユーザーとして導入スクリプトを実行する（シリアルポートを使うため、ユーザーは `dialout` グループに入っている必要がある）

```bash
cd ~/conveyor-mcp
bash deploy/install.sh /dev/serial/by-id/<Arduinoの名前>
```

導入スクリプトは venv の作成、依存のインストール、トークンの生成、systemd への登録と起動を行います。

## テスト

```bash
uv run --no-project --python 3.12 --with-requirements requirements.txt --with pytest python -m pytest -q
```

## 注意

- `ON` / `OFF` の応答は Arduino が指令を受け付けたことを示すだけで、ベルトの動きは測っていません
- ファームウェアに通信途絶で止める仕組み（watchdog）はありません。MCP クライアントの切断、USB の抜線、サーバーの強制終了ではベルトは止まらないので、物理スイッチで止められる状態で使ってください
- 認証は固定の Bearer トークンです。信頼できる LAN / VPN の中だけで使ってください
