"""Jetsonから最小スケッチ relay-onoff.ino を操作する（pyserialのみ必要）。

拡張版用ConveyorLinkとは別の明示的な選択。S・センサー・通信 watchdog は使わない。
"""
from __future__ import annotations

import argparse
import fcntl
import os
import signal
import time


class RelayError(Exception):
    """Arduinoとの通信の失敗。呼ぶ側はベルトの状態を分からないものとして扱う。"""


class RelayOnOffLink:
    """各コマンドに対するON/OFF応答を待つ。応答は指令受付であり物理状態ではない。"""

    def __init__(self, port=None, *, ser=None, boot_wait=2.0, timeout=1.5):
        """portを他のプログラムと共有せずに開き、Arduinoの起動を待ってからOFFの応答を確かめる。

        serを渡すと、そのシリアルを使う（テスト用）。開いた後に失敗したら閉じてから例外を出す。
        """
        self.ser = None
        self.fault = False
        self.timeout = timeout
        if timeout <= 0 or boot_wait < 0:
            raise ValueError("timeout must be positive; boot_wait must be nonnegative")
        if ser is None:
            import serial
            ser = serial.Serial(port, 115200, timeout=0.05, write_timeout=1, exclusive=True)
        self.ser = ser
        try:
            time.sleep(boot_wait)
            self.belt_off()  # Sではなく0/OFFで接続を確認。起動時に回さない。
        except BaseException:
            self.close()
            raise

    def _command(self, command, expected):
        """commandを送り、expectedの1行が返るまで待つ。違う応答や時間切れはRelayErrorにし、faultを立てる。"""
        if self.ser is None:
            raise RelayError("シリアル接続が閉じています")
        try:
            self.ser.reset_input_buffer()  # 過去のOFFを今回の成功と扱わない
            self.ser.write(command)
            deadline = time.monotonic() + self.timeout
            buf = bytearray()
            while time.monotonic() < deadline:
                chunk = self.ser.read(1)
                if not chunk:
                    continue
                buf += chunk
                if len(buf) > 256:
                    raise RelayError("Arduinoの応答が長すぎます")
                if chunk == b"\n":
                    line = bytes(buf).strip()
                    buf.clear()
                    if line == expected:
                        return
                    raise RelayError(f"想定外のArduino応答: {line!r}")
            raise RelayError(f"Arduinoから {expected.decode()} が返りません")
        except Exception as exc:
            self.fault = True
            # ON応答を失っても、停止を送る。応答未確認なので成功とは報告しない。
            try:
                self.ser.write(b"0")
            except Exception:
                pass
            if isinstance(exc, RelayError):
                raise
            raise RelayError("Arduinoとの通信に失敗しました") from exc

    def belt_on(self):
        """ベルトを回す。一度でも通信に失敗した接続では回さない（状態が分からないまま回し直さないため）。"""
        if self.fault:
            raise RelayError("通信異常後の再開はできません。接続を作り直してください")
        self._command(b"1", b"ON")

    def belt_off(self):
        """ベルトを止め、OFFの応答を確かめる。"""
        self._command(b"0", b"OFF")

    def close(self):
        """OFFを送ってシリアルを閉じる。OFFの応答を確かめられたらTrue、確かめられなければFalseを返す。"""
        if self.ser is None:
            return True
        confirmed = False
        try:
            self.belt_off()
            confirmed = True
        except Exception:
            pass
        finally:
            try:
                self.ser.close()
            except Exception:
                confirmed = False
            self.ser = None
        return confirmed


def main(argv=None):
    """リレーだけを手で操作する。stopはOFFの確認、manualは1/0を入力してON/OFFする。終了するときは必ずOFFを送る。"""
    parser = argparse.ArgumentParser(description="Jetson用リレー単体操作（最小スケッチ1/0対応）")
    parser.add_argument("--port", required=True, help="Arduinoの/dev/serial/by-id/... パス")
    parser.add_argument("action", choices=["stop", "manual"], help="停止確認、または対話操作")
    args = parser.parse_args(argv)
    if not os.path.exists(args.port):
        parser.error("指定したシリアルポートがありません")

    def interrupted(signum, frame):
        """SIGTERMをCtrl+Cと同じに扱い、終了の前にOFFを送る後片付けを通す。"""
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGTERM, interrupted)
    link = None
    result = 0
    # server.py と同じロック。Arduinoシリアルにもexclusive=Trueを指定。
    lock_path = os.path.join(os.environ.get("XDG_RUNTIME_DIR") or "/tmp", "duck-pick.lock")
    try:
        with open(lock_path, "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                link = RelayOnOffLink(args.port)
                print("OFF応答確認（Arduinoの指令受付。ベルトの実停止は目視確認）", flush=True)
                if args.action == "manual":
                    print("1=ON / 0=OFF / q=停止して終了。通信断の自動停止は最小スケッチにはありません。")
                    while True:
                        command = input("> ").strip()
                        if command == "q":
                            break
                        if command == "1":
                            link.belt_on()
                            print("ON応答確認")
                        elif command == "0":
                            link.belt_off()
                            print("OFF応答確認")
            finally:
                if link is not None and not link.close():
                    print("OFF応答を確認できません。実機のスイッチで停止してください。", flush=True)
                    result = 1
    except (KeyboardInterrupt, EOFError):
        pass
    except (RelayError, OSError) as exc:
        print(f"停止: {exc}", flush=True)
        result = 1
    finally:
        signal.signal(signal.SIGTERM, previous)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
