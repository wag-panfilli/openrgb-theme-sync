# 6. Sincronização de Cor com o Tema (domínio de lógica de aplicação)

**Objetivo:** sempre que o tema ativo do desktop Omarchy mudar (ou a máquina iniciar), ler a cor predominante desse tema e aplicá-la em todo dispositivo RGB via o servidor SDK (doc 04).

## Onde o Omarchy guarda as cores do tema ativo

Todo diretório de tema do Omarchy contém um `colors.toml` — uma paleta plana de chave/valor. A cópia resolvida do tema **atualmente ativo** sempre mora num caminho fixo, independente do nome do tema:
```
~/.local/state/omarchy/current/theme/colors.toml
```
(Ao lado: `~/.local/state/omarchy/current/theme.name`, o slug do tema atual — não necessário por este projeto já que o script de sincronização sempre relê o arquivo de cores diretamente, mas útil pra debug/log.)

O schema é consistente em todo tema stock verificado (`catppuccin`, `nord`, `tokyo-night`, `rose-pine`, `gruvbox`, o próprio tema customizado "Event Horizon Full" da máquina, etc.), mesmo que alguns temas carreguem campos extras além deste conjunto comum:
```toml
mode = "dark"                  # ou "light"
accent = "#26BBD9"
selection = "#..."
muted = "#..."
background = "#..."
foreground = "#..."
red = "#..."
yellow = "#..."
orange = "#..."
green = "#..."
cyan = "#..."
blue = "#..."
magenta = "#..."
```
`accent` é o único campo garantidamente presente e semanticamente estável em todo tema (é o que o Hyprland usa pra borda da janela ativa, etc.) — a escolha natural pra "cor predominante deste tema."

## O script seletor de cor

`scripts/omarchy-openrgb-pick-colors.py` (instalado em `~/.local/bin/`). Reescrito em 2026-10-03 para ficar mais robusto e para **corrigir a cor para LED** — antes ele mandava o hex do tema cru, e o resultado "errava por pouco".

Saída (consumida via `eval`):
```
THEME_COLOR=686868   # cor do tema como escrita (só pro log)
THEME_SOURCE=keyboard.rgb  # de onde veio (keyboard.rgb, accent ou fallback)
PRIMARY=FFB0F0       # cor corrigida para LED — é esta que vai pro hardware
```

### Captação da cor (parsing)

Ainda sem depender de pacote `toml`, mas agora tolera tudo que já quebrou ou pode quebrar:
- aspas simples, duplas ou nenhuma; comentário no fim da linha (o bug do tema mono de 2026-09-24);
- `#RGB`, `#RRGGBB`, `#RRGGBBAA` (alfa descartado), `0xRRGGBB`, `rgb()`/`rgba()`;
- só chaves de nível superior (ignora `[seções]`); primeira definição vence;
- **fallback** quando o tema não tem `accent` (caso "Mapquest"): `blue` → `color4` → `bright_blue` → `color12`, avisando no log. Antes o sync simplesmente não rodava.

O arquivo lido continua sendo a cópia *resolvida* em `~/.local/state/omarchy/current/theme/colors.toml`.

**Fonte da cor (desde 2026-10-03): a escolha do autor do tema.** O picker lê primeiro `current/theme/keyboard.rgb`, a cor "de hardware RGB" do Omarchy (a mesma que os scripts oficiais de teclado ASUS/Framework usam). Se o tema traz o próprio `keyboard.rgb`, esse arquivo vence (ex.: o `tokyo-night` stock define `ff00ff`, magenta, em vez do azul `7AA2F7` do `accent`); senão o Omarchy o gera a partir do template `{{ accent }}`. Só se esse arquivo faltar ou estiver vazio/inválido o picker cai para o `colors.toml` (`accent` → fallbacks acima). `THEME_SOURCE` no log diz de onde a cor veio.

### Correção de cor para LED (por que "errava por pouco")

Os hex de tema são **sRGB**, codificados com gama para monitor. LED é PWM **linear** (brilho ∝ valor/255). Mandar o hex cru acende demais os canais fracos: acentos pastel saem lavados/esbranquiçados e a matiz desvia — "quase certo, mas não". Além disso, o die verde de um LED RGB é bem mais forte que o vermelho/azul, puxando tudo para verde/ciano. A correção, em ordem:

1. **sRGB → luz linear** (curva sRGB exata, ou gama numérica).
2. **Balanço de branco** por canal (padrão `FFB0F0`, a correção "typical LED strip" do FastLED: G×0,69, B×0,94).
3. **Normalização** para o canal mais forte = 255: preserva matiz/saturação e deixa o brilho a cargo do dispositivo (valores PWM baixos, ex. o acento cinza `#686868`, ficam turvos e com tinta).

Exemplos: Tokyo Night `7AA2F7` → `3949FF`; Event Horizon `26BBD9` → `0886FF`; Matte Black `E68E0D` → `FF3C00`; temas cinza (`white`, `vantablack`, `hinterlands`) → `FFB0F0` (branco calibrado).

Ajustes em `~/.config/omarchy-openrgb/led.conf` (cópia em `scripts/led.conf`; arquivo porque hooks não herdam o env do shell):

| Variável | Padrão | Efeito |
|---|---|---|
| `OPENRGB_LED_CORRECTION` | `1` | `0` = manda o hex cru (comportamento antigo) |
| `OPENRGB_LED_GAMMA` | `srgb` | número menor (1.8) = mais lavado; maior (2.6) = mais profundo |
| `OPENRGB_LED_WHITE_BALANCE` | `FFB0F0` | máx. por canal R G B; `FFFFFF` desliga |

**Calibração:** aplique um tema cinza (`omarchy theme set white`) e olhe os LEDs: branco esverdeado/ciano → baixe o byte do meio (G); azulado/roxo → baixe o último (B); rosado → baixe o primeiro (R). Depois rode `omarchy-openrgb-theme-sync`. Para pré-visualizar sem aplicar: `omarchy-openrgb-pick-colors.py --hex 7AA2F7`.

### Concorrência

O `omarchy-theme-set` libera seu próprio lock **antes** de chamar os hooks, então duas trocas de tema rápidas podiam rodar o sync em paralelo — e quem terminasse por último ganhava, às vezes deixando a cor do tema **anterior**. O sync agora pega um `flock` (`$XDG_RUNTIME_DIR/omarchy-openrgb-theme-sync.lock`) e só lê o `colors.toml` depois de obtê-lo.

## Um desenho anterior, mais rico (substituído, mantido como referência)

A primeira versão funcional calculava **duas** cores em vez de uma: `accent` como "primária", mais qualquer cor ANSI nomeada do tema (`red`/`orange`/`yellow`/`green`/`cyan`/`blue`/`magenta`) que tivesse a maior distância de matiz em relação ao matiz da primária (via `colorsys.rgb_to_hsv`), como "secundária". A ideia era aplicar a primária na GPU/RAM/mouse/teclado e a secundária nas zonas de fita de LED da placa-mãe, pra um visual ambiente de dois tons — e funcionava, produzindo pares complementares agradáveis automaticamente pra todo tema testado (ex.: Tokyo Night → primária `#7AA2F7` azul, secundária `#E0AF68` laranja).

Foi abandonada em favor de uma cor uniforme única depois de testes ao vivo em várias trocas de tema nesta máquina específica: os LEDs RGB da máquina são antigos e desgastados, e renderizam cor de forma inconsistente o bastante (matizes visivelmente diferentes pro que deveria ser a mesma cor nominal, entre GPU/RAM/teclado/mouse) que misturar uma *segunda* matiz, deliberadamente diferente, por cima dessa inconsistência por LED parecia mais que algo estava quebrado do que proposital. Numa máquina com LEDs mais novos/precisos em cor, a abordagem de duas cores vale a pena reviver — o algoritmo de distância de matiz acima é um ponto de partida completo e funcional.

## O script de sincronização

`scripts/omarchy-openrgb-theme-sync` (instalado em `~/.local/bin/`, e instalado tanto como hook `theme-set.d` quanto `post-boot.d` do Omarchy — ver doc 05):

1. Espera a porta do servidor SDK ficar alcançável (até 20s) — necessário pro caso de post-boot, overhead inofensivo pro caso de theme-set (doc 05 explica o porquê).
2. Pega o lock, carrega `led.conf` e lê `PRIMARY` (já corrigida para LED) do script seletor acima.
3. Envia **uma** chamada combinada de `openrgb-mr3027 --client --nodetect`, encadeando todo dispositivo (doc 04 explica por que uma chamada combinada em vez de um processo por dispositivo).
4. Registra tudo (timestamp, cor calculada, saída completa do comando) em `~/.local/state/omarchy-openrgb-theme-sync.log` pra debug posterior.

## Mapeamento dispositivo → cor nesta máquina

Desde 2026-10-03 o script **não usa mais índices fixos**: ele lê a saída de `openrgb-mr3027 --client --nodetect --list-devices` (que já é chamada na espera pela enumeração) e decide modo/cor **pelo nome** de cada dispositivo. Motivo: a troca dos fans/hub reordenou a detecção (placa-mãe passou de 6 → 4, teclado de 4 → 6). Por sorte os dois usavam `direct`, mas qualquer troca envolvendo o mouse (`static`) teria quebrado em silêncio. Dispositivo com nome desconhecido é registrado no log ("Unknown device ...") e deixado em paz.

| Nome em `--list-devices` | Modo usado | Observação |
|---|---|---|
| `ENE DRAM` (x2) | `direct` | 2 pentes de RAM |
| `Gigabyte GeForce RTX 3070 MASTER` (x2) | `direct` + `000000` (**desligado**) | Desde 2026-10-03 os LEDs da GPU estão **queimados**, então ela é forçada a preto em toda execução (boot e troca de tema), nunca recebe a cor do tema. A GPU não tem modo `Off`; preto em `direct` é o "desligar". Uma das duas entradas é **fantasma** (2º adaptador I2C) — as duas recebem preto, inofensivo. Para religar no futuro: voltar o `*"RTX 3070"*` para o grupo `direct` com `$PRIMARY` no `case` do script. |
| `Sinowealth Wireless Keyboard` | `direct` | Dongle AULA, só cor sólida (doc 02) |
| `Redragon M711 Cobra` | `static` | Não tem modo `direct` — confira sempre a linha `Modes:` |
| `B550 AORUS PRO` | `direct` | Zonas: 0=`12V RGB Strips`, 1=`D_LED1 Bottom`, 2=`D_LED2 Top`, 3=`Motherboard`. Primeiro aplica em todas as zonas (sem `--zone`), depois **redimensiona as zonas 1 e 2 para `ARGB_ZONE_SIZE` (120)** e reaplica a cor nelas. |

### Zonas ARGB e o hub de fans (correção de 2026-10-03)

Após instalar um **hub ARGB com vários fans** num header `D_LED` da placa-mãe, o sintoma foi: **só o primeiro LED** do hub pegava a cor do tema; o resto ficava no efeito padrão. Causa: as zonas ARGB (endereçáveis, 5V) da IT5702 são *redimensionáveis* e o OpenRGB as cria com **1 LED** — o comando de cor só escreve nesse um. Headers 12V (não endereçáveis) não têm esse problema.

Correção:
- `--device <mobo> --zone N --size 120 --mode direct --color <hex>` para as zonas 1 e 2. O `--size` **precisa** vir no mesmo bloco que `--mode`/`--color`; sozinho o CLI aborta com "neither mode nor color given".
- O tamanho é refeito **a cada execução**, porque o servidor `--server` não persiste tamanhos de zona entre reinícios (o `sizes.ors` só é gravado pela GUI) — num boot as zonas voltariam para 1 LED.
- 120 é um teto folgado: LEDs "virtuais" além do fim físico da cadeia são ignorados pelo hardware e, para cor sólida única, não causam efeito colateral. Se um dia quiser efeitos por LED, conte os LEDs reais (soma dos fans do hub) e use o valor exato.

Verificado: servidor reiniciado (zonas de volta a 1 LED) → script rodou em ~6s → `--list-devices` mostrou 120 LEDs em `D_LED1 Bottom`, e todos os fans do hub ficaram na cor do tema.

## Notas de portabilidade

- O caminho e o schema do `colors.toml` são específicos do Omarchy. Portar isso pra um sistema de temas que não seja Omarchy significa substituir a fonte de entrada do script seletor por o que quer que esse sistema exponha (um arquivo de esquema de cor do GTK/KDE, uma paleta gerada pelo `pywal`, uma config fixa por tema, etc.) — o resto do pipeline (chamada de cliente SDK, hooks, conexão de boot) é agnóstico à fonte do tema.
- O `case` por nome no script precisa ser refeito em qualquer outra máquina, via a própria saída de `openrgb-mr3027 --list-devices` dessa máquina. Atenção especialmente a:
  - **Entradas fantasma/duplicadas**, especialmente em GPUs NVIDIA expondo o mesmo controlador RGB via múltiplos adaptadores I2C — diagnostique definindo índices candidatos pra cores visivelmente diferentes e observando qual de fato acende.
  - **Suporte a modo por dispositivo** — nem todo dispositivo suporta `direct`; confira a linha `Modes:` e use `static` (ou o que quer que esteja `[entre colchetes]` como ativo/padrão) onde `direct` não estiver listado.
  - **Contagem de zonas** em dispositivos multi-zona (placas-mãe especialmente) — decida se todas as zonas devem ter a mesma cor (como aqui) ou ser divididas, e se `--zone` precisa ser especificado por zona ou pode ser omitido para "todas as zonas".
  - **Zonas ARGB redimensionáveis** — headers endereçáveis (ARGB/D_LED) nascem com tamanho 1 no OpenRGB; se só o 1º LED de uma fita/hub muda de cor, é isso. Redimensione com `--zone N --size M` a cada sincronização.

## Cor a partir do wallpaper (2026-10-04)

Desde 2026-10-04 a cor padrão vem do **wallpaper atual**, não mais do tema
(`OPENRGB_COLOR_SOURCE=wallpaper` em `~/.config/omarchy-openrgb/led.conf`;
`theme` volta ao comportamento antigo).

**Algoritmo** (`read_wallpaper_color` em `omarchy-openrgb-pick-colors.py`):
a imagem é reduzida para 256px, convertida para HSV e cada pixel recebe peso
`saturação × brilho` (pixels com S ≤ 0,20 ou V ≤ 0,15 são ignorados). A cor
literalmente mais comum de um wallpaper costuma ser preto/cinza, que nos LEDs
(normalizados para brilho máximo) vira branco — por isso vence o **matiz que
cobre a maior área colorida**. Histograma de 36 faixas de 10° com suavização
circular; a cor final é a média ponderada dos pixels a ±20° do pico. Se menos
de 3% dos pixels forem "vívidos" (wallpaper em tons de cinza), usa a cor do
tema (`keyboard.rgb` / `accent`). Depois passa pela mesma correção de LED.

**Gatilho**: o Omarchy não dispara hook ao trocar só o wallpaper
(`omarchy theme bg next/set`, seletor de fundo) — esses comandos apenas
reapontam o symlink `~/.local/state/omarchy/current/background`. O serviço
systemd de usuário `omarchy-openrgb-wallpaper-watch.service` roda
`omarchy-openrgb-wallpaper-watch`, que observa esse diretório com
`inotifywait` e chama `omarchy-openrgb-theme-sync` quando o alvo muda. Os
hooks `theme-set` e `post-boot` continuam instalados; o `flock` do script de
sync serializa execuções simultâneas.

**Pré-visualizar**: `omarchy-openrgb-pick-colors.py --image <arquivo>`.

**Backup do estado anterior**: `backups/2026-10-04-antes-wallpaper/`
(instruções em `RESTAURAR.md`).

## Otimização de latência (2026-10-04)

Medido antes: ~5,1s por sincronização (+ ~1,5s de debounce do watcher).
Depois: **~0,3s** da troca do wallpaper até os LEDs (aplicação em ~12ms).

| Gargalo | Causa | Correção |
|---|---|---|
| ~1,7s por chamada `openrgb --client` (2 chamadas) | ~0,7s para conectar e baixar os controladores + `sleep` fixo de ~1s após aplicar, embutido no CLI | `omarchy-openrgb-apply.py`: fala o protocolo SDK direto via `openrgb-python` (venv em `~/.local/share/omarchy-openrgb/venv`) |
| ~40ms por pacote do protocolo | Servidor e cliente mandam cabeçalho e corpo em 2 `send`; Nagle segura o 2º até o ACK, e o Linux atrasa o ACK em 40ms | `TCP_NODELAY` no cliente + `TCP_QUICKACK` rearmado antes de cada `recv` |
| "Connection attempt failed" + 1s | Autoconnect do CLI usa `localhost` → `::1`, mas o servidor só escutava em IPv4 | Servidor com `--server-host ::` (dual-stack) no `autostart.lua`; CLI com `127.0.0.1:6742` explícito |
| Debounce de ~1,5s no watcher | `sleep 0.5` + `inotifywait -t 1` | `inotifywait -m` + drenagem de 0,15s |
| ~0,1–0,5s para analisar wallpapers grandes | Decodificar JPG/PNG 5K | Cache em `~/.cache/omarchy-openrgb/wallpaper-colors.tsv` (caminho+tamanho+mtime) |

O caminho pelo CLI continua como **fallback** (venv quebrado após upgrade do
Python, erro de protocolo), com a lista de dispositivos em cache por instância
do servidor (`$XDG_RUNTIME_DIR/omarchy-openrgb/`). O mapa de dispositivos
existe nos dois lugares — manter sincronizado.

Execuções duplicadas (troca de tema dispara hook `theme-set` **e** o watcher)
são descartadas se a mesma cor foi aplicada ao mesmo servidor há < 15s.

Bug corrigido junto: nomes de wallpaper com espaço quebravam o `eval` da saída
do picker (agora os valores saem com `shlex.quote`); o picker roda com
`timeout 20` para nunca segurar o lock.

## Wallpapers escuros → off-white (2026-10-04)

Caso que motivou: "Girl with Hannya Mask" — 89% dos pixels com brilho ≤ 20%,
o resto cinza/branco, e só 0,14% de pixels coloridos (pontinhos vermelhos).
Ficava abaixo do mínimo de 3% de pixels vívidos, caía no fallback da cor do
tema (coppernight, `FAB387` → `FF533D`) — quase idêntica ao vermelho do
wallpaper anterior, então o RGB *parecia* não ter mudado.

Regra nova, avaliada antes do fallback: se **> 60% dos pixels têm brilho
≤ 0,20** e os pixels vívidos são **< 10% dos não-pretos**, o picker devolve
`DARK` e aplica `OPENRGB_DARK_WALLPAPER_COLOR` (padrão off-white `F5F0E6`, que
após a correção de LED vira `FFA8D0`). Um wallpaper escuro com uma área
colorida relevante (ex.: neon ocupando boa parte do que não é preto) continua
pegando a cor. Dos 97 wallpapers do sistema, caem nessa regra: Hannya Mask e
os escuros dos temas Vantablack e Matte Black. O cache passou a
`wallpaper-colors-v2.tsv` (guarda `DARK`, não o hex, para a cor ser
configurável sem limpar o cache).

**Ajuste no mesmo dia:** o off-white `F5F0E6` (→ `FFA8D0` após correção)
ficou azulado nos LEDs; a pedido do usuário, a cor dos wallpapers escuros
passou a ser **branco puro `FFFFFF`, enviado sem correção de LED**
(`OPENRGB_DARK_WALLPAPER_COLOR` vai direto para o hardware).

## Cor fixa por wallpaper (2026-10-04)

`~/.config/omarchy-openrgb/wallpaper-overrides.conf` — linhas
`<nome do arquivo> = RRGGBB`, casadas pelo **nome do arquivo** (não pelo
caminho: os backgrounds do tema são recopiados a cada troca de tema). Tem
prioridade sobre a análise do wallpaper e é enviada **sem correção de LED**,
para cores escuras continuarem escuras. Primeiro uso: "Girl with Hannya
Mask.jpeg" = `8B0000` (vermelho escuro).

## Tema "wpanfilli" (2026-10-04)

Clone do Coppernight cuja cor de destaque segue o wallpaper (UI + LEDs
coerentes). Detalhes em `~/.local/share/omarchy-wpanfilli/README.md`. O
watcher chama `omarchy-theme-wpanfilli-render` depois do sync de RGB quando
o tema ativo é `wpanfilli`; o re-tema leva ~1,6s (custo do
`omarchy theme refresh`), o RGB continua ~0,3s.
