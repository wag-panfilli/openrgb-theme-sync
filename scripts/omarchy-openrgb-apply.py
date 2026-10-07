#!/usr/bin/env python3
"""
Applies one color to every OpenRGB device over the SDK protocol directly
(openrgb-python), instead of through the `openrgb --client` CLI.

Why: the CLI costs ~1.7s per call no matter what -- ~0.7s to connect and
fetch the controller list, plus a fixed ~1s pause after applying -- and the
theme sync needed two calls. Talking the protocol directly takes ~10ms.

The other half of the speedup is undoing Nagle + delayed-ACK stalls. Both
ends write each packet as two segments (header, then body); Nagle holds the
second until the first is ACKed, and Linux delays that ACK by 40ms. Every
request therefore stalled ~40ms each way (count + 7 devices + a refetch after
each mode/resize change = over a second). TCP_NODELAY fixes our sends;
TCP_QUICKACK, re-armed before each recv, makes us ACK the server's header at
once so its body isn't held either.

Run with the venv that has openrgb-python:
    ~/.local/share/omarchy-openrgb/venv/bin/python omarchy-openrgb-apply.py RRGGBB

Exit codes: 0 applied, 1 failed (server/devices not ready, protocol error),
2 openrgb-python unavailable. On non-zero, omarchy-openrgb-theme-sync falls
back to the CLI path. Keep the device map below in sync with that script's.
"""
import socket
import sys
import time

QUICKACK = getattr(socket, "TCP_QUICKACK", 12)
_recv, _recv_into = socket.socket.recv, socket.socket.recv_into


def _quickack(sock):
    try:
        sock.setsockopt(socket.IPPROTO_TCP, QUICKACK, 1)
    except OSError:
        pass


_connect = socket.socket.connect


def _connect_nodelay(self, *a, **k):
    _connect(self, *a, **k)
    if self.family in (socket.AF_INET, socket.AF_INET6):
        self.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)


socket.socket.connect = _connect_nodelay
# Re-arm quick ACK before every read (the kernel drops back to delayed ACKs).
socket.socket.recv = lambda self, *a, **k: (_quickack(self), _recv(self, *a, **k))[1]
socket.socket.recv_into = lambda self, *a, **k: (_quickack(self), _recv_into(self, *a, **k))[1]

try:
    from openrgb import OpenRGBClient
    from openrgb.utils import RGBColor
except ImportError as e:
    print(f"openrgb-python not available: {e}")
    sys.exit(2)

HOST, PORT = "127.0.0.1", 6742
EXPECTED_DEVICES = 7
WAIT_SECONDS = 20
# Generous upper bound for the ARGB fan hub chain (zones 1/2 of the mobo).
ARGB_ZONE_SIZE = 120


def connect():
    """Connect, waiting for the server to come up (post-boot) -- up to 20s."""
    deadline = time.monotonic() + WAIT_SECONDS
    while True:
        try:
            return OpenRGBClient(HOST, PORT, "omarchy-openrgb-theme-sync")
        except (ConnectionError, OSError, TimeoutError):
            if time.monotonic() > deadline:
                raise
            time.sleep(0.25)


def wait_for_devices(client):
    """The port opens before hardware detection finishes (seen on real
    reboots: 2 of 7 controllers at first), so wait for the full count."""
    deadline = time.monotonic() + WAIT_SECONDS
    while len(client.devices) < EXPECTED_DEVICES:
        if time.monotonic() > deadline:
            return False
        time.sleep(0.25)
        client.update()
    return True


def main():
    if len(sys.argv) != 2:
        print("Usage: omarchy-openrgb-apply.py RRGGBB")
        return 1
    color = RGBColor.fromHEX(sys.argv[1].lstrip("#"))
    black = RGBColor(0, 0, 0)

    start = time.monotonic()
    try:
        client = connect()
    except Exception as e:  # noqa: BLE001 - any failure -> CLI fallback
        print(f"SDK connect failed: {e}")
        return 1

    try:
        if not wait_for_devices(client):
            print(f"Only {len(client.devices)}/{EXPECTED_DEVICES} controllers "
                  f"detected after {WAIT_SECONDS}s")
            return 1

        for dev in client.devices:
            name = dev.name
            if "RTX 3070" in name:
                # LEDs burned out; no "Off" mode, so black in Direct.
                dev.set_mode("direct")
                dev.set_color(black)
            elif name in ("ENE DRAM", "Sinowealth Wireless Keyboard"):
                dev.set_mode("direct")
                dev.set_color(color)
            elif name == "Redragon M711 Cobra":
                # No Direct mode; its Static mode is per-LED colored, so it
                # is driven like Direct (mode, then LED color).
                dev.set_mode("static")
                dev.set_color(color)
            elif name == "B550 AORUS PRO":
                dev.set_mode("direct")
                # ARGB headers feeding the fan hub default to 1 LED and the
                # server forgets sizes on restart: resize every run.
                for z in (1, 2):
                    if len(dev.zones[z].leds) != ARGB_ZONE_SIZE:
                        dev.zones[z].resize(ARGB_ZONE_SIZE)
                dev.set_color(color)
            else:
                print(f"Unknown device '{name}' (index {dev.id}), leaving it alone")
    except Exception as e:  # noqa: BLE001
        print(f"SDK apply failed: {type(e).__name__}: {e}")
        return 1
    finally:
        try:
            client.disconnect()
        except Exception:  # noqa: BLE001
            pass

    print(f"Applied via SDK in {(time.monotonic() - start) * 1000:.0f}ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
