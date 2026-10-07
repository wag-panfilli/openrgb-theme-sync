#!/usr/bin/env python3
"""
Reads an Omarchy theme's RGB color -- keyboard.rgb (the theme author's
hardware color) first, else colors.toml's accent -- and prints the color to send to the RGB
hardware, as shell variable assignments for omarchy-openrgb-theme-sync:

    THEME_COLOR=RRGGBB   the theme's color exactly as written (for the log)
    THEME_SOURCE=<src>   where it came from (keyboard.rgb, accent, or a fallback)
    PRIMARY=RRGGBB       the same color corrected for LEDs (what gets sent)

Why a correction step: theme hex values are sRGB, i.e. gamma-encoded for a
monitor. LEDs are driven linearly (PWM duty = value/255), so a raw sRGB value
lights the weaker channels far too bright -- pastel accents come out washed
out and drift towards white, and the hue lands "almost right but off". Steps:

  1. sRGB -> linear light (the standard sRGB transfer curve).
  2. White balance: RGB LEDs' green die is much brighter than red/blue, so
     equal values look greenish/cyan rather than white. Scale per channel.
  3. Normalize so the strongest channel is 255: the hardware brightness is
     set by the device, and dim PWM values (e.g. a #686868 gray accent) look
     muddy and tint-shifted on LEDs. The hue/saturation is what we preserve.

Tunables via environment (defaults are FastLED's "typical LED strip"
correction, a sane starting point for WS2812-style ARGB + DRAM LEDs):

    OPENRGB_LED_CORRECTION=0        send the theme color untouched
    OPENRGB_LED_GAMMA=2.2           number, or "srgb" (default) for the
                                    exact piecewise sRGB curve
    OPENRGB_LED_WHITE_BALANCE=FFB0F0  per-channel max (R G B), FFFFFF = off

Usage:
    omarchy-openrgb-pick-colors.py <colors.toml>
    omarchy-openrgb-pick-colors.py --hex <RRGGBB>   # preview a correction
    omarchy-openrgb-pick-colors.py --image <file>   # preview a wallpaper

Color source (OPENRGB_COLOR_SOURCE in led.conf):
    theme      keyboard.rgb, else colors.toml accent (default)
    wallpaper  dominant vivid color of the current background
               (~/.local/state/omarchy/current/background), falling back
               to the theme color for grayscale wallpapers
"""
import os
import re
import shlex
import sys

# colors.toml key priority, used only when keyboard.rgb is unusable: accent; if a theme forgot it (seen with the
# git-installed "Mapquest" theme), fall back to the theme's blue / ANSI
# color4, which is what Omarchy's own accent derivation uses.
KEY_PRIORITY = ("accent", "blue", "color4", "bright_blue", "color12")

# key = value, tolerant of: single or double quotes, no quotes, trailing
# comments, `#RGB`, `#RRGGBB`, `#RRGGBBAA`, `0xRRGGBB`, rgb()/rgba().
LINE_RE = re.compile(r"""^\s*([A-Za-z0-9_]+)\s*=\s*(.+?)\s*$""")
HEX_RE = re.compile(r"""^["']?\s*(?:#|0x)?([0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![0-9a-fA-F])\s*["']?""")
RGB_FN_RE = re.compile(
    r"""^["']?\s*rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})""")


def parse_color(raw):
    """Returns 'RRGGBB' (upper case) or None."""
    raw = raw.strip()
    m = HEX_RE.match(raw)
    if m:
        h = m.group(1)
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return h[:6].upper()  # drop alpha of #RRGGBBAA
    m = RGB_FN_RE.match(raw)
    if m:
        r, g, b = (min(int(v), 255) for v in m.groups())
        return f"{r:02X}{g:02X}{b:02X}"
    return None


def emit(color, source, raw=False):
    """Prints the result as shell assignments for `eval` in the sync script.
    Values are shell-quoted: wallpaper file names can contain spaces.
    raw=True sends the color to the LEDs as-is, skipping LED correction."""
    print(f"THEME_COLOR={color}")
    print(f"THEME_SOURCE={shlex.quote(source)}")
    print(f"PRIMARY={color if raw else correct_for_leds(color)}")


def read_palette(path):
    palette = {}
    in_table = False
    with open(path, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("["):
                # Only top-level keys are the palette; ignore [sections].
                in_table = True
                continue
            if in_table:
                continue
            m = LINE_RE.match(line)
            if not m:
                continue
            key, value = m.group(1), m.group(2)
            color = parse_color(value)
            # First definition wins, like a real TOML file would reject dupes.
            if color and key not in palette:
                palette[key] = color
    return palette


def read_keyboard_rgb(path):
    """First color in keyboard.rgb, or None if missing/empty/unparseable."""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    return parse_color(line)
    except OSError:
        pass
    return None


# v2: entries may hold DARK_NEUTRAL instead of a hex (v1 cached "" there).
WALLPAPER_CACHE = os.path.expanduser("~/.cache/omarchy-openrgb/wallpaper-colors-v2.tsv")

# Sentinel from read_wallpaper_color() for "mostly black, the rest white/gray"
# wallpapers. Cached as-is, not as a hex, so changing the configured color
# (OPENRGB_DARK_WALLPAPER_COLOR) needs no cache flush.
DARK_NEUTRAL = "DARK"
# Pure white, sent to the LEDs as-is (no LED correction): it's a hardware
# color picked by eye, not a theme color to translate. An off-white run
# through the correction (F5F0E6 -> FFA8D0) looked bluish on this rig, and the
# user preferred plain FFFFFF over tuning a warmer tint (2026-10-04).
DEFAULT_DARK_WALLPAPER_COLOR = "FFFFFF"


def cached_wallpaper_color(path):
    """read_wallpaper_color() memoized on disk by real path + size + mtime:
    decoding a big wallpaper (e.g. an 18MB 5K PNG) takes ~0.5s, and the same
    few backgrounds get cycled through over and over."""
    try:
        real = os.path.realpath(path)
        st = os.stat(real)
    except OSError:
        return read_wallpaper_color(path)
    key = f"{real}\t{st.st_size}\t{int(st.st_mtime)}"

    entries = {}
    try:
        with open(WALLPAPER_CACHE, encoding="utf-8") as f:
            for line in f:
                k, _, v = line.rstrip("\n").rpartition("\t")
                entries[k] = v
    except OSError:
        pass
    if key in entries:
        return entries[key] or None  # "" = cached "no vivid color"

    color = read_wallpaper_color(real)
    entries[key] = color or ""
    try:
        os.makedirs(os.path.dirname(WALLPAPER_CACHE), exist_ok=True)
        tmp = WALLPAPER_CACHE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for k, v in list(entries.items())[-500:]:
                f.write(f"{k}\t{v}\n")
        os.replace(tmp, WALLPAPER_CACHE)
    except OSError:
        pass
    return color


def read_wallpaper_color(path):
    """Dominant *vivid* color of an image as 'RRGGBB', DARK_NEUTRAL, or None.

    The literal most-common pixel of a wallpaper is usually a near-black or
    gray (sky, shadows, dark UI-friendly backgrounds), which on LEDs -- once
    normalized to full brightness -- turns into plain white. So pixels are
    weighted by saturation * value: the hue that covers the most *colorful*
    area wins. Within that hue band, the weighted average color is returned.
    Returns DARK_NEUTRAL when the image is mostly black (> 60% of pixels at
    or below 20% brightness) and what's left is white/gray, with only specks
    of color (< 10% of the non-black pixels vivid) -- e.g. a dark artwork
    with a few small red highlights. Those specks are too small to stand for
    the image, and the theme-color fallback below made the LEDs look stuck
    on the previous color, so the caller applies an off-white instead.
    Returns None for other (near) grayscale images so the caller can fall
    back to the theme color.
    """
    try:
        import numpy as np
        from PIL import Image
    except ImportError as e:
        print(f"Wallpaper analysis needs numpy + Pillow ({e})", file=sys.stderr)
        return None

    try:
        with Image.open(path) as img:
            img = img.convert("RGB")
            img.thumbnail((256, 256))
            rgb = np.asarray(img, dtype=np.float64).reshape(-1, 3) / 255
    except OSError as e:
        print(f"Cannot read wallpaper {path}: {e}", file=sys.stderr)
        return None

    mx = rgb.max(axis=1)
    mn = rgb.min(axis=1)
    delta = mx - mn
    sat = np.where(mx > 0, delta / np.maximum(mx, 1e-9), 0)
    val = mx

    r, g, b = rgb.T
    d = np.maximum(delta, 1e-9)
    hue = np.select(
        [mx == r, mx == g],
        [((g - b) / d) % 6, (b - r) / d + 2],
        (r - g) / d + 4,
    ) * 60  # degrees

    # Ignore near-gray and near-black pixels outright; weight the rest.
    vivid = (sat > 0.20) & (val > 0.15)
    weight = np.where(vivid, sat * val, 0)
    dark = val <= 0.20
    if dark.mean() > 0.60:
        rest = ~dark
        if vivid.sum() < 0.10 * max(rest.sum(), 1):
            return DARK_NEUTRAL
    if vivid.mean() < 0.03:
        return None  # essentially grayscale wallpaper

    bins = 36  # 10 degrees each
    hist = np.bincount((hue // (360 / bins)).astype(int) % bins,
                       weights=weight, minlength=bins)
    # Circular smoothing so a hue straddling two bins isn't split in half.
    hist = hist + 0.5 * (np.roll(hist, 1) + np.roll(hist, -1))
    peak_hue = (hist.argmax() + 0.5) * (360 / bins)

    dist = np.abs((hue - peak_hue + 180) % 360 - 180)
    sel = vivid & (dist <= 20)
    w = weight[sel]
    avg = (rgb[sel] * w[:, None]).sum(axis=0) / w.sum()
    return "".join(f"{round(c * 255):02X}" for c in avg)


OVERRIDES_FILE = os.path.expanduser("~/.config/omarchy-openrgb/wallpaper-overrides.conf")


def wallpaper_override(name):
    """Per-wallpaper color from OVERRIDES_FILE, matched by file name (not
    path: the theme's backgrounds are re-copied on every theme switch).
    Lines are `<file name> = RRGGBB`; '#' starts a comment line.
    Returns 'RRGGBB' or None."""
    try:
        with open(OVERRIDES_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.rpartition("=")
                if key.strip() == name:
                    return parse_color(value.strip())
    except OSError:
        pass
    return None


def dark_wallpaper_color():
    """Color for DARK_NEUTRAL wallpapers: OPENRGB_DARK_WALLPAPER_COLOR, or
    the default off-white."""
    return (parse_color(os.environ.get("OPENRGB_DARK_WALLPAPER_COLOR", ""))
            or DEFAULT_DARK_WALLPAPER_COLOR)


def srgb_to_linear(c, gamma):
    if gamma == "srgb":
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return c ** gamma


def correct_for_leds(hex_color):
    if os.environ.get("OPENRGB_LED_CORRECTION", "1") == "0":
        return hex_color

    gamma_env = os.environ.get("OPENRGB_LED_GAMMA", "srgb").strip().lower()
    gamma = "srgb" if gamma_env == "srgb" else float(gamma_env)
    wb_hex = parse_color(os.environ.get("OPENRGB_LED_WHITE_BALANCE", "FFB0F0"))
    if not wb_hex:
        wb_hex = "FFFFFF"
    wb = [int(wb_hex[i:i + 2], 16) / 255 for i in (0, 2, 4)]

    rgb = [int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [srgb_to_linear(c, gamma) * w for c, w in zip(rgb, wb)]

    peak = max(lin)
    if peak <= 1e-6:
        # Black accent: nothing sensible to normalize, keep it off.
        return "000000"

    out = [round(255 * c / peak) for c in lin]
    # Below ~2/255 a channel is invisible but can still add a faint tint on
    # some controllers' low-res PWM; snap it to 0.
    out = [0 if v < 2 else v for v in out]
    return "".join(f"{v:02X}" for v in out)


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--hex":
        color = parse_color(sys.argv[2])
        if not color:
            print(f"Invalid color: {sys.argv[2]}", file=sys.stderr)
            sys.exit(1)
        emit(color, "cli")
        return

    if len(sys.argv) == 3 and sys.argv[1] == "--image":
        color = read_wallpaper_color(sys.argv[2])
        if not color:
            print("No dominant vivid color (grayscale image?)", file=sys.stderr)
            sys.exit(1)
        if color == DARK_NEUTRAL:
            emit(dark_wallpaper_color(), "image-dark", raw=True)
            return
        emit(color, "image")
        return

    if len(sys.argv) != 2:
        print("Usage: omarchy-openrgb-pick-colors.py <colors.toml> | --hex <RRGGBB> | --image <file>",
              file=sys.stderr)
        sys.exit(1)

    # OPENRGB_COLOR_SOURCE=wallpaper (led.conf): the current background's
    # dominant vivid color wins; a grayscale/unreadable wallpaper falls
    # through to the theme color below.
    if os.environ.get("OPENRGB_COLOR_SOURCE", "theme").strip().lower() == "wallpaper":
        bg = os.environ.get("OPENRGB_WALLPAPER",
                            os.path.expanduser("~/.local/state/omarchy/current/background"))
        name = os.path.basename(os.path.realpath(bg))
        # A hand-picked color for this exact wallpaper beats any analysis,
        # and is sent as-is (e.g. a dark red must stay dark; LED correction
        # would normalize it to full-brightness red).
        override = wallpaper_override(name)
        if override:
            emit(override, f"wallpaper-override:{name}", raw=True)
            return
        color = cached_wallpaper_color(bg)
        if color == DARK_NEUTRAL:
            emit(dark_wallpaper_color(), f"wallpaper-dark:{name}", raw=True)
            return
        if color:
            emit(color, f"wallpaper:{name}")
            return
        print("Wallpaper has no dominant vivid color, using the theme color",
              file=sys.stderr)

    # The theme author's hardware RGB color wins: Omarchy writes
    # keyboard.rgb next to colors.toml -- the theme's own file if it ships
    # one (e.g. stock tokyo-night uses ff00ff, not its blue accent), else
    # rendered from the `{{ accent }}` template. Same file Omarchy's own
    # ASUS/Framework keyboard scripts read.
    color = read_keyboard_rgb(os.path.join(os.path.dirname(sys.argv[1]), "keyboard.rgb"))
    if color:
        emit(color, "keyboard.rgb")
        return

    palette = read_palette(sys.argv[1])
    for key in KEY_PRIORITY:
        if key in palette:
            if key != "accent":
                print(f"No usable 'accent' in colors.toml, falling back to '{key}'",
                      file=sys.stderr)
            emit(palette[key], key)
            return

    print("No 'accent' (nor blue/color4 fallback) found in colors.toml",
          file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
