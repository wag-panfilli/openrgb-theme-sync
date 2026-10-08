#!/bin/bash
# Removes the wpanfilli theme. Switch to another theme first: leaving
# wpanfilli lets the theme-set hook restore gtk.css and the libadwaita accent.
set -u
if [[ $(cat "$HOME/.local/state/omarchy/current/theme.name" 2>/dev/null) == wpanfilli ]]; then
    echo "wpanfilli is the active theme -- run 'omarchy theme set <other>' first." >&2
    exit 1
fi
systemctl --user disable --now omarchy-wpanfilli-wallpaper-watch.service 2>/dev/null
rm -f "$HOME/.config/systemd/user/omarchy-wpanfilli-wallpaper-watch.service"
rm -f "$HOME/.local/bin/omarchy-theme-wpanfilli-render" \
      "$HOME/.local/bin/omarchy-wpanfilli-wallpaper-watch" \
      "$HOME/.config/omarchy/hooks/theme-set.d/omarchy-wpanfilli-gtk-sync"
rm -rf "$HOME/.local/share/omarchy-wpanfilli" \
       "$HOME/.config/omarchy/themes/wpanfilli" \
       "$HOME/.local/state/omarchy-wpanfilli" \
       "$HOME/.cache/omarchy-wpanfilli" \
       "$HOME/.local/share/icons/Papirus-Dark-WP-"*
echo "wpanfilli removed."
