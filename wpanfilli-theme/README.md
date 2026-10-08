# wpanfilli — tema Omarchy que segue o wallpaper

Tema para [Omarchy](https://omarchy.org) baseado no
[Coppernight](https://github.com/hembramnishant50-glitch/omarchy-coppernight-theme),
recolorido automaticamente a partir do **wallpaper atual**: a cada troca de
fundo, bordas das janelas, barra, terminais, editores, GTK/Nautilus, navegador,
ícones de pasta e cor de destaque do libadwaita passam a usar as cores do
wallpaper.

## Instalação

```bash
git clone https://github.com/wag-panfilli/openrgb-theme-sync.git
cd openrgb-theme-sync/wpanfilli-theme
./install.sh            # instala, renderiza e ativa o tema
./install.sh --no-set   # instala sem trocar o tema atual
```

Dependências (instaladas pelo script via `pacman` se faltarem):
`python-numpy`, `python-pillow`, `inotify-tools`, `papirus-icon-theme`.

> Não use `omarchy-theme-install` com este repositório: o diretório do tema
> é **gerado** pelo renderizador, não é o conteúdo do repo.

Para remover: troque para outro tema e rode `./uninstall.sh`.

O tema funciona sozinho, **sem** OpenRGB. Com o sync de RGB deste repositório
instalado (pasta raiz), LEDs e tema mudam juntos a cada troca de wallpaper.

## Como funciona

| Papel | Substitui no Coppernight | Onde aparece |
|---|---|---|
| Primária | `#fab387` | texto/realces da barra, borda ativa, btop, GTK, editores |
| Secundária | `#c6a0f6` | borda das janelas inativas, realces secundários |
| Terciária | `#ed8796` (só cursor) | cursor, 2ª cor do degradê da borda ativa |
| Neutros | `#11111b`, `#181825`, `#313244`, `#cad3f5`… | fundos de janelas/terminal/menus e textos — re-matizados com o tom da primária, mesma luminosidade |
| Navegador | `chromium.theme` (`r,g,b`) | primária escura e saturada |
| Ícones | pastas laranja do Papirus-Dark | tema de ícones do usuário `Papirus-Dark-WP-<cor>` (cor Papirus mais próxima da primária, sem root) |
| libadwaita | `accent-color` | a mais próxima das 9 cores de destaque do GNOME |

As cores ANSI do terminal (vermelho, amarelo, magenta…) **nunca** mudam —
vermelho continua vermelho no `git diff`.

### Origem das cores

1. `~/.config/omarchy-wpanfilli/wallpaper-overrides.conf` (ou o
   `~/.config/omarchy-openrgb/wallpaper-overrides.conf` do sync de RGB),
   se houver entrada para o wallpaper → primária. Veja
   [`examples/wallpaper-overrides.conf`](examples/wallpaper-overrides.conf).
2. Até 3 matizes vívidos e distintos do wallpaper (≥ 35° de distância, cada
   um com ≥ 10% da área colorida do mais forte); os que faltarem são
   derivados da primária (±40°).
3. Wallpaper quase preto/neutro → prata e cinzas.
4. Sem cor utilizável → as cores originais do Coppernight.

Cada cor é levada à faixa de luminosidade/saturação do acento do Coppernight
para continuar legível no fundo escuro. A análise de cada wallpaper fica em
cache (`~/.cache/omarchy-wpanfilli/palettes.tsv`).

## Estrutura do repositório

| Caminho | Instalado em | O que é |
|---|---|---|
| `template/` | `~/.local/share/omarchy-wpanfilli/template/` | cópia intacta do Coppernight — **edite aqui** |
| `bin/omarchy-theme-wpanfilli-render` | `~/.local/bin/` | analisa o wallpaper e gera `~/.config/omarchy/themes/wpanfilli/` a partir do template; se o tema está ativo, roda `omarchy theme refresh` |
| `bin/omarchy-wpanfilli-wallpaper-watch` | `~/.local/bin/` | observa (inotify) o symlink `current/background` e chama o renderizador |
| `systemd/omarchy-wpanfilli-wallpaper-watch.service` | `~/.config/systemd/user/` | serviço de usuário do watcher |
| `hooks/omarchy-wpanfilli-gtk-sync` | `~/.config/omarchy/hooks/theme-set.d/` | hook `theme-set`: fundo do Nautilus/GTK e accent do libadwaita |
| `backgrounds/` | `~/.config/omarchy/themes/wpanfilli/backgrounds/` | wallpapers do tema |

O diretório `~/.config/omarchy/themes/wpanfilli/` é **regenerado** a cada
troca de wallpaper (exceto `backgrounds/`) — edições feitas nele se perdem.

Uso manual do renderizador:

```bash
omarchy-theme-wpanfilli-render --dry-run   # só mostra a paleta
omarchy-theme-wpanfilli-render --force     # regenera e reaplica
```

### Detalhes

- **Disparo**: o Omarchy não tem hook para `omarchy theme bg next/set` nem
  para o seletor de fundos — eles só reapontam o symlink
  `~/.local/state/omarchy/current/background`. O watcher observa esse
  diretório. Se o sync de RGB ([`../scripts/`](../scripts/))
  estiver instalado, o watcher dele já chama o renderizador (depois dos LEDs)
  e o `install.sh` não instala um segundo watcher.
- **Custo**: ~1,6 s por troca de wallpaper (quase todo no
  `omarchy theme refresh`, que mantém o fundo atual, sem loop de eventos).
- **Nautilus/GTK**: o fundo das janelas vem de `~/.config/gtk-{3,4}.0/gtk.css`.
  Com o wpanfilli ativo, o hook escreve ali o `filemanager-gtk.css`
  renderizado; ao trocar de tema, devolve o original do Coppernight. Só mexe
  em arquivos com o marcador dele ou o cabeçalho do Coppernight. O GTK lê o
  CSS só ao iniciar e o Nautilus fica residente (`--gapplication-service`),
  então o hook deixa um "waiter" que encerra o serviço (`nautilus -q`) assim
  que não houver janela aberta — nunca fecha janelas.
- **Chromium**: o Omarchy grava `chromium.theme` na policy em
  `/etc/chromium/policies/managed/` e atualiza o navegador aberto.

## Créditos

- Licença: MIT (a do repositório).
- Tema base: [Coppernight](https://github.com/hembramnishant50-glitch/omarchy-coppernight-theme) (MIT).
- Wallpapers em `backgrounds/` pertencem aos respectivos autores.
