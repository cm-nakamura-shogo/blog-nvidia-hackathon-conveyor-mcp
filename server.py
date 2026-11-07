"""orin-nano-2 のコンベア MCP サーバー。Arduino の relay-onoff ファームウェアを、占有したシリアルポートで操作する。"""
import argparse
import fcntl
import logging
import os
import secrets
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import uvicorn
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from starlette.responses import PlainTextResponse

from relay_onoff import RelayOnOffLink

logger = logging.getLogger("conveyor_mcp")


class Conveyor:
    """コンベアのリレーの ON / OFF と、最後に Arduino が受け付けた指令の記録。

    状態は指令の記録で、ベルトの動きを測った値ではない。指令に失敗したら fault を残し、
    サービスを再起動するまで開始を拒否する（原因を確かめずに回し直さないため）。
    """

    def __init__(self, port=None, simulate=False, link_factory=RelayOnOffLink):
        """simulate なら USB を開かない。実機では開いた時点で OFF を送り、OFF の応答を確かめる。"""
        self.simulate = simulate
        self.lock = threading.RLock()
        self.link = None
        self.acknowledged_running = None
        self.acknowledged_at = None
        self.fault = None
        self.closed = False
        if not simulate:
            self.link = link_factory(port)  # 起動しただけでベルトが回らないよう、開いた時点で OFF を送り、応答を確かめる
        self._ack(False)

    def _ack(self, running):
        self.acknowledged_running = running
        self.acknowledged_at = datetime.now(timezone.utc).isoformat()

    def status(self):
        """最後に受け付けた指令などの状態を返す。シリアルには書かない。"""
        with self.lock:
            return {"simulation": self.simulate,
                    "last_acknowledged_running": self.acknowledged_running,
                    "last_acknowledged_at": self.acknowledged_at,
                    "fault": self.fault, "closed": self.closed,
                    "note": "Last Arduino command acknowledgement only, not current or physical belt state. "
                            "Minimal firmware has no disconnect watchdog. Client disconnect does not stop belt."}

    def _set(self, running):
        with self.lock:
            if self.closed:
                raise RuntimeError("Serial connection is closed")
            if running and self.fault:
                raise RuntimeError("Conveyor fault; inspect hardware and restart service before starting")
            try:
                if self.link:
                    if running:
                        self.link.belt_on()
                    else:
                        self.link.belt_off()
                self._ack(running)
                logger.info("relay_ack running=%s simulation=%s", running, self.simulate)
            except Exception as exc:
                self.acknowledged_running = None
                self.acknowledged_at = None
                self.fault = type(exc).__name__
                logger.error("relay_failed operation=%s error_type=%s", "start" if running else "stop", self.fault)
                raise RuntimeError("Arduino acknowledgement failed; use physical stop and inspect connection") from exc
            return self.status()

    def start(self):
        """ベルトを回す。fault があれば拒否し、Arduino の応答がなければ fault を残して例外を出す。"""
        return self._set(True)

    def stop(self):
        """ベルトを止める（リレーを OFF にし、Arduino の応答を待つ）。"""
        return self._set(False)

    def close(self):
        """OFF を送ってシリアルを閉じる。OFF を確かめられなければ fault に残す（物理スイッチで止める必要がある）。"""
        with self.lock:
            if self.closed:
                return
            try:
                if self.link and not self.link.close():
                    self.acknowledged_running = None
                    self.acknowledged_at = None
                    self.fault = "ShutdownStopUnconfirmed"
                    logger.error("shutdown_stop_unconfirmed use_physical_stop=true")
                else:
                    self._ack(False)
            finally:
                self.closed = True


# エージェントに渡る tool の説明。schemas/conveyor-mcp-tools.json と一字も変えない。
# LLM が読む文なので英語で書き、docstring とは分ける（Python 3.13 以降は docstring の字下げが消え、説明が変わるため）。
# START_CONVEYOR_DESCRIPTION の改行の後の空白は、3.12 の docstring から書き出したときのもの。I/F を変えないため残す
GET_CONVEYOR_STATUS_DESCRIPTION = 'Return cached last Arduino acknowledgement. No serial writes; NOT measured belt state.'
START_CONVEYOR_DESCRIPTION = (
    'Physically start conveyor via Arduino relay D7. Keeps running after client disconnect.\n'
    '\n'
    '        Invoke only following an explicit operator command or approved control decision.\n'
    '        '
)
STOP_CONVEYOR_DESCRIPTION = 'Send relay OFF and await Arduino acknowledgement. Does not measure physical stopping.'


def make_server(conveyor):
    """conveyor の状態の読み取り、開始、停止の 3 つのツールを登録した MCP サーバーを作る。"""
    @asynccontextmanager
    async def lifespan(_):
        try:
            yield {}
        finally:
            conveyor.close()

    mcp = MCPServer("orin-nano-2-conveyor", lifespan=lifespan)

    @mcp.tool(description=GET_CONVEYOR_STATUS_DESCRIPTION, annotations=ToolAnnotations(readOnlyHint=True))
    def get_conveyor_status() -> dict:
        """Arduino が最後に受け付けた指令を返す。シリアルには書かず、ベルトの動きを測った値でもない。"""
        return conveyor.status()

    @mcp.tool(description=START_CONVEYOR_DESCRIPTION,
              annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True))
    def start_conveyor() -> dict:
        """リレー（D7）でベルトを回す。クライアントが切れても回り続ける。"""
        return conveyor.start()

    @mcp.tool(description=STOP_CONVEYOR_DESCRIPTION,
              annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True))
    def stop_conveyor() -> dict:
        """リレーを OFF にし、Arduino の応答を待つ。ベルトが止まったことは測らない。"""
        return conveyor.stop()

    return mcp


class BearerGate:
    """HTTP の要求ごとに Bearer トークンを確かめる ASGI のミドルウェア。違えば 401 を返す。"""

    def __init__(self, app, token):
        self.app = app
        self.expected = f"Bearer {token}".encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            auth = dict(scope.get("headers", [])).get(b"authorization", b"")
            # 比べる時間からトークンを推測されないよう、一定時間で比べる
            if not secrets.compare_digest(auth, self.expected):
                response = PlainTextResponse("Unauthorized", status_code=401,
                                             headers={"WWW-Authenticate": "Bearer"})
                return await response(scope, receive, send)
        await self.app(scope, receive, send)


def main():
    """引数と環境変数を確かめ、シリアルの鍵を取ってから MCP サーバーを起動する。"""
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--serial-port", default=os.environ.get("CONVEYOR_SERIAL_PORT"))
    parser.add_argument("--lock-file", default=os.path.join(
        os.environ.get("XDG_RUNTIME_DIR") or "/tmp", "duck-pick.lock"))
    args = parser.parse_args()
    token = os.environ.get("CONVEYOR_MCP_TOKEN", "")
    if len(token) < 32:
        parser.error("CONVEYOR_MCP_TOKEN must contain at least 32 random characters")
    if not args.simulate and not args.serial_port:
        parser.error("Set CONVEYOR_SERIAL_PORT or --serial-port")
    # 認証のほかに Host と Origin も制限する（ブラウザ経由の DNS リバインディングで LAN の外から叩かれないため）
    hosts = [f"{args.host}:{args.port}", f"127.0.0.1:{args.port}", f"localhost:{args.port}"]
    security = TransportSecuritySettings(allowed_hosts=hosts,
                                         allowed_origins=[f"http://{h}" for h in hosts])
    # 鍵のファイルは /tmp に置くので、シンボリックリンクに差し替えられても追わない
    flags = os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW
    with os.fdopen(os.open(args.lock_file, flags, 0o600), "w") as lock:
        # 同じ Arduino を開く別のプログラム（relay_onoff.py など）と、二重に起動しない
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        conveyor = Conveyor(args.serial_port, args.simulate)
        try:
            mcp = make_server(conveyor)
            app = mcp.streamable_http_app(stateless_http=True, json_response=True,
                                         transport_security=security)
            # シリアルを開くのは 1 つのプロセスだけにする（複数の worker が同じ USB を取り合わないため）
            uvicorn.run(BearerGate(app, token), host=args.host, port=args.port, workers=1)
        finally:
            conveyor.close()


if __name__ == "__main__":
    main()
