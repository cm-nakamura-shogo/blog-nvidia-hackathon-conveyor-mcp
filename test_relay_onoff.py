import pytest

from relay_onoff import RelayError, RelayOnOffLink


class MinimalSerial:
    def __init__(self):
        self.rx = []
        self.buffer = bytearray()
        self.belt = False
        self.reply = True
        self.closed = False

    def reset_input_buffer(self):
        self.buffer.clear()

    def write(self, data):
        self.rx.append(data)
        if data in (b"0", b"1"):
            self.belt = data == b"1"
            if self.reply:
                self.buffer.extend(b"ON\n" if self.belt else b"OFF\n")
        return len(data)

    def read(self, n):
        result = bytes(self.buffer[:n])
        del self.buffer[:n]
        return result

    def close(self):
        self.closed = True


def connect(ser):
    return RelayOnOffLink(ser=ser, boot_wait=0, timeout=0.01)


def test_minimal_sketch_on_off_and_close():
    ser = MinimalSerial()
    link = connect(ser)
    assert ser.rx == [b"0"]
    link.belt_on()
    assert ser.belt
    link.belt_off()
    assert not ser.belt
    link.belt_on()
    assert link.close()
    assert not ser.belt and ser.closed
    assert b"S" not in ser.rx


def test_no_reply_fails_connection_and_closes():
    ser = MinimalSerial()
    ser.reply = False
    with pytest.raises(RelayError, match="返りません"):
        connect(ser)
    assert ser.closed
    assert b"1" not in ser.rx


def test_lost_on_ack_stops_and_latches_fault():
    ser = MinimalSerial()
    link = connect(ser)
    ser.reply = False
    with pytest.raises(RelayError):
        link.belt_on()
    assert not ser.belt
    ser.reply = True
    link.belt_off()
    with pytest.raises(RelayError, match="再開"):
        link.belt_on()
    assert link.close()


def test_stale_off_does_not_confirm_stop():
    ser = MinimalSerial()
    link = connect(ser)
    ser.buffer.extend(b"OFF\n")
    ser.reply = False
    assert not link.close()
    assert ser.closed


def test_unknown_response_is_not_success():
    ser = MinimalSerial()
    link = connect(ser)
    original = ser.write
    def write(data):
        original(data)
        ser.buffer[:] = b"READY\n"
    ser.write = write
    with pytest.raises(RelayError, match="想定外"):
        link.belt_on()
    assert link.fault
    assert not link.close()
