#!/bin/bash
# Installs the "wpanfilli" Omarchy theme: Coppernight recolored from the
# current wallpaper. Safe to re-run (updates scripts/template in place).
#
#   ./install.sh            install + render + `omarchy theme set wpanfilli`
#   ./install.sh --no-set   install + render, keep the current theme
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
SHARE="$HOME/.local/share/omarchy-wpanfilli"
THEME_DIR="$HOME/.config/omarchy/themes/wpanfilli"
BIN="$HOME/.local/bin"
HOOKS="$HOME/.config/omarchy/hooks/theme-set.d"
UNITS="$HOME/.config/systemd/user"

say() { printf '→ %s\n' "$*"; }

# 1. Dependencies (Arch / Omarchy).
missing=()
python3 -c 'import numpy' 2>/dev/null || missing+=(python-numpy)
python3 -c 'import PIL' 2>/dev/null || missing+=(python-pillow)
command -v inotifywait >/dev/null || missing+=(inotify-tools)
[[ -d /usr/share/icons/Papirus-Dark ]] || missing+=(papirus-icon-theme)
if ((${#missing[@]})); then
    say "installing: ${missing[*]}"
    sudo pacman -S --needed --noconfirm "${missing[@]}"
fi

# 2. Pristine Coppernight template (the theme dir is generated from it).
say "template → $SHARE/template"
mkdir -p "$SHARE"
rm -rf "$SHARE/template.new"
cp -a "$REPO/template" "$SHARE/template.new"
rm -rf "$SHARE/template"
mv "$SHARE/template.new" "$SHARE/template"

# 3. Scripts and theme-set hook.
say "scripts → $BIN, hook → $HOOKS"
mkdir -p "$BIN" "$HOOKS"
install -m 755 "$REPO/bin/omarchy-theme-wpanfilli-render" "$BIN/"
install -m 755 "$REPO/bin/omarchy-wpanfilli-wallpaper-watch" "$BIN/"
install -m 755 "$REPO/hooks/omarchy-wpanfilli-gtk-sync" "$HOOKS/"

# 4. Wallpapers (never removes ones you added).
say "backgrounds → $THEME_DIR/backgrounds"
mkdir -p "$THEME_DIR/backgrounds"
cp -n "$REPO/backgrounds/"* "$THEME_DIR/backgrounds/" 2>/dev/null || true

# 5. Nautilus/GTK background: the hook only manages gtk.css files that carry
#    its marker or Coppernight's header, never one you wrote yourself.
for v in 3.0 4.0; do
    css="$HOME/.config/gtk-$v/gtk.css"
    if [[ ! -s $css ]]; then
        mkdir -p "$(dirname "$css")"
        cp "$REPO/template/filemanager-gtk.css" "$css"
    elif ! grep -qF -e "wpanfilli: generated" -e "Coppernight file manager background" "$css"; then
        say "skipping $css (custom file; Nautilus background won't follow the theme)"
    fi
done

# 6. Wallpaper watcher. omarchy-openrgb-wallpaper-watch (openrgb-theme-sync)
#    already calls the renderer, so don't run two watchers.
if systemctl --user is-enabled omarchy-openrgb-wallpaper-watch.service &>/dev/null; then
    say "omarchy-openrgb-wallpaper-watch already re-renders wpanfilli; skipping own watcher"
else
    say "enabling omarchy-wpanfilli-wallpaper-watch.service"
    mkdir -p "$UNITS"
    install -m 644 "$REPO/systemd/omarchy-wpanfilli-wallpaper-watch.service" "$UNITS/"
    systemctl --user daemon-reload
    systemctl --user enable --now omarchy-wpanfilli-wallpaper-watch.service
fi

# 7. First render, then activate.
say "rendering"
"$BIN/omarchy-theme-wpanfilli-render" --force
if [[ ${1:-} != --no-set ]]; then
    say "omarchy theme set wpanfilli"
    omarchy theme set wpanfilli
fi
say "done"
