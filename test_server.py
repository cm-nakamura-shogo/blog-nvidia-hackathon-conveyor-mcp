from pathlib import Path
import pytest
from server import Conveyor

def test_http_auth_host_and_mcp(tmp_path):
    import json
    import os
    import socket
    import subprocess
    import sys
    import time
    import urllib.request
    from urllib.error import HTTPError, URLError
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    token = "test-only-token-" + "x" * 32
    log_file = (tmp_path / "server.log").open("w")
    process = subprocess.Popen(
        [sys.executable, str(Path(__file__).with_name("server.py")), "--simulate", "--port", str(port),
         "--lock-file", str(tmp_path / "server.lock")],
        env={**os.environ, "CONVEYOR_MCP_TOKEN": token},
        stdout=subprocess.DEVNULL, stderr=log_file,
    )

    def request(method, params=None, auth=True, host=None):
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   "MCP-Protocol-Version": "2025-11-25"}
        if auth:
            headers["Authorization"] = "Bearer " + token
        if host:
            headers["Host"] = host
        data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                           "params": params or {}}).encode()
        req = urllib.request.Request(f"http://127.0.0.1:{port}/mcp", data=data, headers=headers)
        with urllib.request.urlopen(req, timeout=3) as response:
            return json.load(response)

    try:
        for _ in range(50):
            try:
                request("tools/list", auth=False)
            except HTTPError as error:
                assert error.code == 401
                break
            except URLError:
                time.sleep(0.1)
        else:
            pytest.fail("HTTP server did not start")
        with pytest.raises(HTTPError) as error:
            request("tools/list", host="unexpected.example")
        assert error.value.code == 421
        result = request("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                                        "clientInfo": {"name": "test", "version": "1"}})
        assert "result" in result
        result = request("tools/list")
        assert {tool["name"] for tool in result["result"]["tools"]} == {
            "start_conveyor", "get_conveyor_status", "stop_conveyor"}
        result = request("tools/call", {"name": "start_conveyor", "arguments": {}})
        assert not result["result"].get("isError", False)
        result = request("tools/call", {"name": "stop_conveyor", "arguments": {}})
        assert not result["result"].get("isError", False)
    finally:
        process.terminate()
        process.wait(timeout=10)
        log_file.close()
    logs = (tmp_path / "server.log").read_text()
    assert token not in logs

class FakeLink:
    def __init__(self, port):
        self.commands = ["0"]
        self.fail = False

    def belt_on(self):
        self.commands.append("1")
        if self.fail:
            raise OSError("private error")

    def belt_off(self):
        self.commands.append("0")
        if self.fail:
            raise OSError("private error")

    def close(self):
        self.commands.append("0")
        return not self.fail


def test_startup_status_and_shutdown():
    c = Conveyor("unused", link_factory=FakeLink)
    assert c.status()["last_acknowledged_running"] is False
    assert c.link.commands == ["0"]
    c.start()
    assert c.status()["last_acknowledged_running"] is True
    assert c.link.commands == ["0", "1"]  # status is read-only
    c.stop()
    c.close()
    assert c.link.commands == ["0", "1", "0", "0"]
    with pytest.raises(RuntimeError):
        c.start()


def test_fault_latches_even_after_successful_stop():
    c = Conveyor("unused", link_factory=FakeLink)
    c.link.fail = True
    with pytest.raises(RuntimeError):
        c.start()
    assert c.status()["last_acknowledged_running"] is None
    assert c.status()["fault"]
    c.link.fail = False
    c.stop()
    assert c.status()["last_acknowledged_running"] is False
    with pytest.raises(RuntimeError, match="fault"):
        c.start()
    c.close()


def test_unconfirmed_shutdown_is_unknown():
    c = Conveyor("unused", link_factory=FakeLink)
    c.start()
    c.link.fail = True
    c.close()
    assert c.status()["last_acknowledged_running"] is None
    assert c.status()["fault"] == "ShutdownStopUnconfirmed"


def test_tool_schema_matches_export():
    import asyncio
    import json
    from server import make_server
    conveyor = Conveyor(simulate=True)
    try:
        tools = asyncio.run(make_server(conveyor).list_tools())
        actual = {'tools': [tool.model_dump(mode='json', exclude_none=True) for tool in tools]}
        path = Path(__file__).resolve().parent / 'schemas' / 'conveyor-mcp-tools.json'
        assert actual == json.loads(path.read_text())
    finally:
        conveyor.close()
