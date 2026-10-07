# 5. Persistência a Reboot (domínio de sessão / init)

**Objetivo:** o servidor OpenRGB (doc 04) precisa estar rodando, e todo dispositivo já precisa refletir a cor do tema atual, sem nenhuma ação manual, toda vez que a máquina inicia.

## Primeira tentativa (errada): XDG autostart

A abordagem óbvia — e a ferramenta embutida do próprio OpenRGB pra isso — é:
```bash
openrgb-mr3027 --autostart-enable --startminimized
```
Isso escreve uma entrada XDG autostart padrão em `~/.config/autostart/OpenRGB.desktop`, que é como o autostart funciona no GNOME, KDE, XFCE, e na maioria dos outros ambientes desktop que rodam um daemon de autostart compatível com XDG.

**Isso não faz nada no Hyprland/Omarchy.** Não há nenhum daemon de autostart XDG (nenhum `dex`, nenhum equivalente) processando `~/.config/autostart/*.desktop` nessa configuração — confirmado buscando em toda a árvore de código-fonte do Omarchy (`/usr/share/omarchy/`) por qualquer referência a esse diretório e não encontrando nenhuma. O arquivo ficava lá, inerte, e nunca teria disparado num reboot de verdade. (Outros arquivos `.desktop` avulsos foram encontrados nesse mesmo diretório, sobras de instalações de pacotes não relacionados — a presença deles não é evidência de que o diretório é lido; são igualmente inertes, lançados de outra forma, se é que são lançados.) Isso foi percebido e corrigido antes de depender disso de verdade.

## O que o Omarchy/Hyprland de fato usa

A sequência de inicialização do Hyprland é uma lista fixa de comandos rodados no evento `hyprland.start`, definida em `/usr/share/omarchy/default/hypr/autostart.lua`:
```lua
hl.on("hyprland.start", function()
  hl.exec_cmd("systemctl --user import-environment $(env | cut -d'=' -f 1)")
  hl.exec_cmd("dbus-update-activation-environment --systemd --all")
  hl.exec_cmd("omarchy-launch-shell")
  hl.exec_cmd("omarchy-provision-first-run")
  hl.exec_cmd("omarchy-powerprofiles-init")
  hl.exec_cmd(o.launch("omarchy-hyprland-monitor-watch"))
  hl.exec_cmd(o.launch("udiskie --automount --no-notify --no-tray"))
  hl.exec_cmd("sleep 2 && omarchy-hook post-boot")
end)
```
Duas coisas importam aqui:

1. **Extensões de nível de usuário** vão em `~/.config/hypr/autostart.lua`, que a config padrão do Omarchy já dá `require`. O helper `o.launch_on_start(command)` (definido em `/usr/share/omarchy/default/hypr/helpers.lua`) registra o mesmo tipo de handler de `hyprland.start`, envolvendo o comando em `uwsm-app --` (o lançador de apps do Universal Wayland Session Manager, pra contabilização correta de escopo/cgroup do systemd) — o mesmo mecanismo que o próprio Omarchy usa pro `udiskie` acima, por exemplo.
2. **`omarchy-hook post-boot`** roda um `sleep 2` depois que o Hyprland inicia, e então executa todo script em `~/.config/omarchy/hooks/post-boot.d/` (ver `hooks.md` na skill do Omarchy, ou `omarchy hook install --help`). Esse é o mecanismo de "rodar algo uma vez, logo depois que o desktop sobe" — análogo a uma unit oneshot do `systemd --user`, mas nativo do Omarchy.

## As duas peças que este projeto adiciona

### a) Lançar o servidor: `~/.config/hypr/autostart.lua`
```lua
o.launch_on_start("openrgb-mr3027 --startminimized --server")
```
(mantido neste projeto em `scripts/autostart.lua.snippet`.) Isso dispara na inicialização do Hyprland, lançando o servidor persistente descrito no doc 04, minimizado na bandeja do sistema.

### b) Reaplicar a cor do tema: um hook `post-boot.d`
O mesmo script exato usado pra sincronizar em troca de tema (doc 06) é instalado como um **segundo** hook, além de sua instalação em `theme-set.d`:
```bash
omarchy hook install post-boot ~/.local/bin/omarchy-openrgb-theme-sync
```
As duas instalações copiam o arquivo do script pra `~/.config/omarchy/hooks/<tipo>.d/` — **hooks são cópias, não symlinks**. Rode os dois comandos `omarchy hook install` de novo depois de qualquer edição no script de origem, ou as cópias instaladas ficam desatualizadas silenciosamente.

## Por que o script de sincronização precisa da própria lógica de espera pelo servidor

O `omarchy-hook post-boot` dispara só 2 segundos depois que o Hyprland inicia. Isso muitas vezes *não* é tempo suficiente pro OpenRGB terminar a inicialização do Qt e a detecção de hardware (enumeração USB, varredura de barramento I2C, handshakes HID) antes de algo tentar falar com o servidor SDK dele na porta 6742. Se o script de sincronização só tentasse conectar uma vez e desistisse, ele silenciosamente não faria nada num boot frio de verdade (esse é um risco real, cronometrado empiricamente, não hipotético) — a própria espera de conexão de cliente da CLI do OpenRGB é um máximo fixo de 1 segundo (`for(int timeout = 0; timeout < 100; timeout++) { ...; sleep 10ms; }` no `cli.cpp`) antes de prosseguir de qualquer forma, tenha conectado ou não.

Então o script de sincronização mesmo faz polling na porta do servidor antes de fazer qualquer outra coisa:
```bash
server_up=false
for _ in $(seq 1 40); do
    if (exec 3<>"/dev/tcp/127.0.0.1/6742") 2>/dev/null; then
        exec 3>&- 3<&-
        server_up=true
        break
    fi
    sleep 0.5
done
```
Até 20 segundos de polling (40 × 0,5s), usando o pseudo-dispositivo embutido `/dev/tcp` do bash em vez de depender de uma ferramenta externa como o `nc`. Essa mesma espera é overhead inofensivo numa execução de `theme-set` (o servidor já está de pé há muito tempo, então a primeiríssima checagem já tem sucesso e o loop encerra na hora) — um único script atende os dois hooks sem precisar de duas variantes.

## Verificando isso sem esperar por um reboot de verdade

Simule a sequência exata que o Hyprland rodaria, em ordem, com timing real:
```bash
# 1. Mata qualquer instância rodando (simulando "antes do boot")
pkill -f "openrgb-aula-build/openrgb"

# 2. Lança o servidor exatamente como o o.launch_on_start do autostart.lua faria
uwsm-app -- openrgb-mr3027 --startminimized --server &
disown

# 3. Espera os mesmos 2s que a própria sequência de inicialização do Hyprland espera, depois dispara o hook
sleep 2 && omarchy-hook post-boot

# 4. Confere o log
tail -n 20 ~/.local/state/omarchy-openrgb-theme-sync.log
```
Essa simulação rodou e pareceu funcionar de ponta a ponta — mas um reboot de verdade (feito por outro motivo, uma atualização de sistema, em 2026-09-16) expôs um bug real que a simulação não pegou: o hook `post-boot` disparou ~23s depois do boot, a porta 6742 já estava aberta, mas o servidor só tinha enumerado 2 dos 7 controladores (só a RAM — GPU, placa-mãe, mouse e teclado ainda não tinham sido detectados). O script encadeia `--device 6 ...` (placa-mãe) num único comando; como o controlador 6 ainda não existia, a CLI do OpenRGB abortou com `Error: Empty device ID` **antes de aplicar qualquer cor**, então esse boot específico não recolori nada, apesar do polling da porta ter "funcionado".

**Causa raiz**: a porta aceitar conexão só significa que o processo do servidor está vivo — não que ele terminou de detectar o hardware. Numa reinicialização de verdade, com mais contenção de I/O e outros serviços subindo ao mesmo tempo, a enumeração de hardware pode demorar bem mais do que num restart manual a quente do servidor (onde os 7 controladores apareceram em menos de 1s nos testes).

**Correção aplicada**: depois da espera pela porta, o script agora também faz polling em `openrgb-mr3027 --client --nodetect --list-devices`, contando linhas que casam com `^[0-9]+:`, até ver os 7 controladores esperados (até 20s, mesmo orçamento de tempo do polling da porta) — só então envia os comandos de cor. Se depois de 20s ainda não viu os 7, desiste e loga em vez de mandar um comando quebrado. Essa correção foi verificada com um restart a quente do servidor (fluxo completo funcionando), mas ainda não foi comprovada num **novo** reboot de verdade — vale conferir na próxima vez que a máquina reiniciar.

## Notas de portabilidade

- **Verifique se o compositor/DE da máquina alvo implementa mesmo XDG autostart antes de assumir que `--autostart-enable` vai funcionar.** GNOME/KDE/XFCE/etc. geralmente implementam; Hyprland puro, Sway, ou outros compositores Wayland minimalistas geralmente não, a menos que algo como `dex` esteja explicitamente configurado. Na dúvida, verifique empiricamente: crie um `.desktop` de teste trivial que toca um arquivo marcador, faça logout/login (ou reboot), e confira se o marcador apareceu.
- Se a máquina alvo também roda Omarchy, a abordagem exata deste projeto de `autostart.lua` + hook `post-boot.d` se transfere diretamente.
- Se a máquina alvo roda Hyprland puro sem Omarchy, use a diretiva nativa `exec-once = ...` do Hyprland em `hyprland.conf` em vez de `autostart.lua`/`o.launch_on_start`, e substitua o hook `post-boot.d` por um simples `exec-once = sleep 5 && ~/.local/bin/omarchy-openrgb-theme-sync` (ajustando o sleep, ou confiando no próprio polling de espera pelo servidor do script, que não precisa de nenhum mecanismo específico do Omarchy — só o caminho do arquivo de cores do tema no doc 06 é específico do Omarchy).
- Se o gerenciador de sessão alvo for baseado em systemd (por exemplo, se uma unit `systemd --user` for preferível a um hook de compositor), uma unit `.service` com `WantedBy=default.target` e `ExecStart=/home/<usuario>/.local/bin/openrgb-mr3027 --startminimized --server` seria uma alternativa mais portável ao `autostart.lua` — não usada aqui só porque os primitivos de hook/autostart do próprio Omarchy já encaixavam bem.
