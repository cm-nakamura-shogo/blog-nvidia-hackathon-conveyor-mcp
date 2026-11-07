#!/usr/bin/env bash
set -euo pipefail
# Jetson 上で、このフォルダを ~/conveyor-mcp に置いてから一般ユーザー（sudo なし）で実行する。
# 先に deploy/conveyor-mcp.service の <USER> と <JETSON_IP> を自分の環境に合わせて書き換えておく。
if [[ $(id -u) == 0 ]]; then
  echo 'Run this script as a normal user (not sudo).'; exit 1
fi
if [[ $# != 1 || ! -c "$1" ]]; then
  echo 'Usage: bash deploy/install.sh /dev/serial/by-id/<Arduino>'; exit 1
fi
conveyor_dir="$(cd -- "$(dirname -- "$0")/.." && pwd)"
if [[ "$conveyor_dir" != "$HOME/conveyor-mcp" ]]; then
  echo 'Place this folder at ~/conveyor-mcp first.'; exit 1
fi
cd "$conveyor_dir"
if grep -q -e '<USER>' -e '<JETSON_IP>' deploy/conveyor-mcp.service; then
  echo 'Replace <USER> and <JETSON_IP> in deploy/conveyor-mcp.service first.'; exit 1
fi
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
# 再導入しても同じトークンを使う。トークンは表示しない。
(umask 077; .venv/bin/python - <<'PY'
from pathlib import Path
import secrets
p = Path('.token')
if not p.exists():
    p.write_text(secrets.token_urlsafe(32) + '\n')
p.chmod(0o600)
PY
)
sudo install -d -m 700 /etc/conveyor-mcp
# systemd の EnvironmentFile に書けない文字を含むパスは受け付けない。
if [[ "$1" == *'"'* || "$1" == *$'\n'* || "$1" == *'\'* || "$1" == *'`'* || "$1" == *'$'* ]]; then
  echo 'Unsupported serial path'; exit 1
fi
{
  printf 'CONVEYOR_MCP_TOKEN=%s\n' "$(cat .token)"
  printf 'CONVEYOR_SERIAL_PORT="%s"\n' "$1"
} | sudo sh -c 'umask 077; cat > /etc/conveyor-mcp/environment'
sudo install -m 644 deploy/conveyor-mcp.service /etc/systemd/system/conveyor-mcp.service
sudo systemctl daemon-reload
sudo systemctl enable conveyor-mcp
sudo systemctl restart conveyor-mcp
sudo systemctl status conveyor-mcp --no-pager
