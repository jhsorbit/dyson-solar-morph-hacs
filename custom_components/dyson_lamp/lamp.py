"""BLE control of Dyson Lightcycle Morph lamps for Home Assistant.

Logic ported from the reverse-engineered CLI tool (dyson/lamp.py).
The LampClient manages a ``bleak`` connection/authentication and issues
raw GATT writes to control power, brightness, color temperature, sensors
and preset modes.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import math
import os
import struct
import time
import uuid
from typing import Callable, Optional

from bleak import BleakScanner

try:
    from bleak_retry_connector import establish_connection as _establish_connection
    _HAS_BRC = True
except Exception:  # pragma: no cover
    _HAS_BRC = False


# Dyson BLE UUIDs
AUTH_SERVICE = "2dd10010-1c37-452d-8979-d1b4a787d0a4"
CHAR_AUTH_WRITE = "2dd10011-1c37-452d-8979-d1b4a787d0a4"
CHAR_AUTH_NOTIFY = "2dd10011-1c37-452d-8979-d1b4a787d0a4"

CMD_SERVICE = "2dd10020-1c37-452d-8979-d1b4a787d0a4"
CHAR_CMD_WRITE = "2dd10021-1c37-452d-8979-d1b4a787d0a4"

LIGHT_SERVICE = "2dd1fff0-1c37-452d-8979-d1b4a787d0a4"
CHAR_POWER = "2dd11005-1c37-452d-8979-d1b4a787d0a4"
CHAR_BRIGHTNESS = "2dd11009-1c37-452d-8979-d1b4a787d0a4"
CHAR_COLOR_TEMP = "2dd11001-1c37-452d-8979-d1b4a787d0a4"
CHAR_AUTO_BRIGHTNESS = "2dd11006-1c37-452d-8979-d1b4a787d0a4"
CHAR_MOVEMENT_SENSOR = "2dd11007-1c37-452d-8979-d1b4a787d0a4"

USER_AUTH_AES_INFO = b"USER_AUTH_AES\x00\x00\x00"

PRESET_MODE_PACKETS = {
    "SYNCHRONISED": bytes.fromhex("80931320010001"),
    "SYNC": bytes.fromhex("80931320010001"),
    "STUDY": bytes.fromhex("80931e20010001"),
    "RELAX": bytes.fromhex("80931f20010001"),
    "PRECISION": bytes.fromhex("80932120010001"),
}

ATTR_LAT = bytes([3, 32])
ATTR_LON = bytes([4, 32])
ATTR_TZ = bytes([26, 32])
ATTR_TIME = bytes([37, 32])

BRIGHT_MIN = 100
BRIGHT_MAX = 1000
COLOR_TEMP_MIN = 2700
COLOR_TEMP_MAX = 6500


def derive_session_key(ltk_bytes: bytes) -> bytes:
    prk = hmac.new(b"\x00" * 32, ltk_bytes, hashlib.sha256).digest()
    return hmac.new(prk, USER_AUTH_AES_INFO + b"\x01", hashlib.sha256).digest()[:16]


def user_id_to_bytes(uid_str: str) -> bytes:
    u = uuid.UUID(uid_str)
    return struct.pack(">QQ", (u.int >> 64) & 0xFFFFFFFFFFFFFFFF, u.int & 0xFFFFFFFFFFFFFFFF)


def aes_cbc_decrypt(key: bytes, iv: bytes, ct: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    dec = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    return dec.update(ct) + dec.finalize()


def aes_cbc_encrypt(key: bytes, iv: bytes, pt: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    enc = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    return enc.update(pt) + enc.finalize()


def aead_seal(key: bytes, plaintext: bytes) -> bytes:
    iv = os.urandom(16)
    ct = aes_cbc_encrypt(key, iv, plaintext)
    mac = hmac.new(key, ct, hashlib.sha256).digest()
    return iv + ct + mac


def build_payload(key: bytes, plaintext: bytes, prefix: bytes | None = None) -> bytes:
    padding = b"\x00\x00"
    aead = aead_seal(key, plaintext)
    out = bytearray()
    if prefix:
        out.extend(prefix)
    out.extend(padding)
    out.extend(aead)
    return bytes(out)


def fragment_message(payload: bytes, type_id: int, capacity: int = 20) -> list[bytes]:
    chunk_size = capacity - 1
    d = bytes([type_id]) + payload
    total_additional = math.ceil(len(d) / chunk_size) - 1
    frags = []
    for idx in range(total_additional + 1):
        hdr = (0x80 | (total_additional & 0x7F)) if idx == 0 else (idx & 0x7F)
        offset = idx * chunk_size
        frags.append(bytes([hdr]) + d[offset : offset + chunk_size])
    return frags


class MessageReassembler:
    def __init__(self) -> None:
        self.buffer = bytearray()
        self.expected = 0
        self.received = 0
        self.type_id = 0

    def feed(self, data: bytes):
        if len(data) < 2 and (data[0] & 0x80):
            return None
        b0 = data[0]
        if (b0 & 0x80) != 0:
            self.expected = (b0 & 0x7F) + 1
            self.type_id = data[1]
            self.received = 1
            self.buffer = bytearray(data[2:])
        else:
            self.received = (b0 & 0x7F) + 1
            self.buffer.extend(data[1:])
        if self.received == self.expected and self.expected > 0:
            res = bytes(self.buffer)
            tid = self.type_id
            self.buffer = bytearray()
            self.expected = 0
            self.received = 0
            return tid, res
        return None


class LampState:
    def __init__(
        self,
        is_on: bool,
        brightness: int,
        color_temp: int,
        auto_brightness: bool = False,
        movement_sensor: bool = False,
        effect: Optional[str] = None,
    ) -> None:
        self.is_on = is_on
        self.brightness = brightness
        self.color_temp = color_temp
        self.auto_brightness = auto_brightness
        self.movement_sensor = movement_sensor
        self.effect = effect


class DysconnError(Exception):
    """Raised when the lamp cannot be connected/authenticated."""


class LampClient:
    """Async client managing a persistent BLE connection to one lamp."""

    def __init__(self, address: str, user_id: str, ltk_hex: str) -> None:
        self.address = address
        self.user_id = user_id
        self.ltk = bytes.fromhex(ltk_hex)
        self.session_key = derive_session_key(self.ltk)
        self.user_bytes = user_id_to_bytes(user_id)
        self.client = None
        self._reassembler = MessageReassembler()
        self._payload_b_future: Optional[asyncio.Future] = None
        self._auth_ack_future: Optional[asyncio.Future] = None

    async def connect(self, timeout: float = 15.0) -> None:
        if self.client and self.client.is_connected:
            return

        address = await self._resolve_address()
        from bleak import BleakClient

        self.client = BleakClient(address, timeout=timeout)
        await self.client.connect()
        await self._authenticate()

    async def _resolve_address(self) -> str:
        if "-" in self.address and len(self.address) >= 18:
            return self.address
        # Address is a serial/name -> scan for it
        devs = await BleakScanner.discover(timeout=5.0)
        for d in devs:
            if d.name == self.address or (d.name and self.address in d.name):
                return d.address
        raise DysconnError(f"Lamp '{self.address}' not found via BLE scan")

    async def disconnect(self) -> None:
        if self.client:
            try:
                if self.client.is_connected:
                    await self.client.disconnect()
            except Exception:
                pass
            self.client = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()

    def _on_notify(self, _sender, data) -> None:
        msg = self._reassembler.feed(data)
        if not msg:
            return
        tid, body = msg
        if tid == 7 and self._payload_b_future and not self._payload_b_future.done():
            self._payload_b_future.set_result(body)
        elif tid == 38 and self._auth_ack_future and not self._auth_ack_future.done():
            self._auth_ack_future.set_result(body)

    async def _authenticate(self) -> None:
        loop = asyncio.get_running_loop()
        self._payload_b_future = loop.create_future()
        self._auth_ack_future = loop.create_future()

        await self.client.start_notify(CHAR_AUTH_NOTIFY, self._on_notify)
        await asyncio.sleep(0.4)

        # Step 1: Product info request
        await self.client.write_gatt_char(CHAR_AUTH_WRITE, b"\x80\x0a", response=False)
        await asyncio.sleep(0.5)

        # Step 2: Authorize with App Challenge + User ID
        app_challenge = os.urandom(16)
        payload_a = build_payload(self.session_key, app_challenge, prefix=self.user_bytes)
        for f in fragment_message(payload_a, type_id=6, capacity=20):
            await self.client.write_gatt_char(CHAR_AUTH_WRITE, f, response=False)
            await asyncio.sleep(0.04)

        # Step 3: Wait for Payload B (contains lamp challenge)
        body_b = await asyncio.wait_for(self._payload_b_future, timeout=8.0)
        pt = aes_cbc_decrypt(self.session_key, body_b[2:18], body_b[18:50])
        lamp_challenge = pt[16:32]

        # Step 4: Reply to lamp challenge
        payload_reply = build_payload(self.session_key, lamp_challenge, prefix=None)
        for f in fragment_message(payload_reply, type_id=8, capacity=20):
            await self.client.write_gatt_char(CHAR_AUTH_WRITE, f, response=False)
            await asyncio.sleep(0.04)

        # Step 5: Wait for ACK (best effort)
        try:
            await asyncio.wait_for(self._auth_ack_future, timeout=8.0)
        except asyncio.TimeoutError:
            pass
        await asyncio.sleep(0.2)

    async def get_state(self) -> LampState:
        pwr = await self.client.read_gatt_char(CHAR_POWER)
        br = await self.client.read_gatt_char(CHAR_BRIGHTNESS)
        ct = await self.client.read_gatt_char(CHAR_COLOR_TEMP)

        auto_br = False
        try:
            ab = await self.client.read_gatt_char(CHAR_AUTO_BRIGHTNESS)
            auto_br = ab[0] == 1
        except Exception:
            pass

        movement = False
        try:
            mv = await self.client.read_gatt_char(CHAR_MOVEMENT_SENSOR)
            movement = mv[0] == 1
        except Exception:
            pass

        return LampState(
            is_on=pwr[0] == 1,
            brightness=struct.unpack("<H", br)[0],
            color_temp=struct.unpack("<H", ct)[0],
            auto_brightness=auto_br,
            movement_sensor=movement,
        )

    async def set_power(self, on: bool) -> None:
        await self.client.write_gatt_char(CHAR_POWER, b"\x01" if on else b"\x00", response=False)

    async def set_brightness(self, lumens: int) -> None:
        lumens = max(BRIGHT_MIN, min(BRIGHT_MAX, int(lumens)))
        await self.client.write_gatt_char(CHAR_BRIGHTNESS, struct.pack("<H", lumens), response=False)

    async def set_color_temp(self, kelvin: int) -> None:
        kelvin = max(COLOR_TEMP_MIN, min(COLOR_TEMP_MAX, int(kelvin)))
        await self.client.write_gatt_char(CHAR_COLOR_TEMP, struct.pack("<H", kelvin), response=False)

    async def set_auto_brightness(self, enabled: bool) -> None:
        await self.client.write_gatt_char(CHAR_AUTO_BRIGHTNESS, b"\x01" if enabled else b"\x00", response=False)

    async def set_movement_sensor(self, enabled: bool) -> None:
        await self.client.write_gatt_char(CHAR_MOVEMENT_SENSOR, b"\x01" if enabled else b"\x00", response=False)

    async def set_mode(self, mode_name: str) -> None:
        key = mode_name.upper().strip()
        pkt = PRESET_MODE_PACKETS.get(key)
        if not pkt:
            raise ValueError(f"Unknown preset mode '{mode_name}'")
        await self.set_power(True)
        await asyncio.sleep(0.3)
        await self.client.write_gatt_char(CHAR_CMD_WRITE, pkt, response=False)
        await asyncio.sleep(0.5)

    async def sync_solar_location(
        self, latitude: float, longitude: float, timezone_str: str = "Europe/Berlin"
    ) -> None:
        async def _send_attr(attr_bytes, length_int, value_bytes) -> None:
            payload = bytearray()
            payload.extend(attr_bytes)
            payload.extend(struct.pack("<H", length_int))
            payload.extend(value_bytes)
            frags = fragment_message(bytes(payload), type_id=0x93, capacity=20)
            for f in frags:
                await self.client.write_gatt_char(CHAR_CMD_WRITE, f, response=False)
                await asyncio.sleep(0.04)
            await asyncio.sleep(0.3)

        await _send_attr(ATTR_LAT, 8, struct.pack("<d", float(latitude)))
        await _send_attr(ATTR_LON, 8, struct.pack("<d", float(longitude)))
        tz_bytes = timezone_str.encode("utf-8").ljust(64, b"\x00")
        await _send_attr(ATTR_TZ, 64, tz_bytes)
        await _send_attr(ATTR_TIME, 4, struct.pack("<I", int(time.time())))

    async def run_wakeup(
        self,
        duration_sec: int = 1800,
        target_lumens: int = 800,
        target_kelvin: int = 4800,
        callback: Optional[Callable] = None,
    ) -> None:
        start_lumens = 100
        start_kelvin = 2700
        steps = max(10, min(100, duration_sec // 5))
        interval = duration_sec / steps

        await self.set_brightness(start_lumens)
        await asyncio.sleep(0.3)
        await self.set_color_temp(start_kelvin)
        await asyncio.sleep(0.3)
        await self.set_power(True)

        start_time = time.time()
        for i in range(1, steps + 1):
            elapsed = time.time() - start_time
            progress = min(1.0, elapsed / duration_sec)
            cur_lumens = int(round(start_lumens + (target_lumens - start_lumens) * (progress**1.5)))
            cur_kelvin = int(round(start_kelvin + (target_kelvin - start_kelvin) * progress))

            await self.set_brightness(cur_lumens)
            await asyncio.sleep(0.3)
            await self.set_color_temp(cur_kelvin)
            if callback:
                callback(i, steps, progress, cur_lumens, cur_kelvin)
            await asyncio.sleep(interval)
