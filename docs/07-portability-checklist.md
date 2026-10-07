# 7. Checklist de Portabilidade e Ideias Futuras

Este doc resume o que refazer versus o que reaproveitar diretamente ao levar este projeto pra outra máquina, e dá um caminho pra transformar isso num software de verdade em vez de uma pilha de scripts pessoais.

## Checklist pra uma nova máquina

Siga os docs 1-6 nesta ordem; cada item abaixo diz o que é específico desta máquina (precisa ser redescoberto) versus o que é genérico (pode ser copiado como está).

| Passo | Específico desta máquina — redescobrir | Genérico — reaproveitar direto |
|---|---|---|
| 1. RAM/I2C (doc 01) | Se o problema existe (depende do chipset/placa-mãe); qual bootloader está em uso e como editar a cmdline dele | O parâmetro `acpi_enforce_resources=lax` em si; o método de diagnóstico (`i2cdetect -l` antes/depois) |
| 2. Build do OpenRGB (doc 02) | Se o teclado alvo precisa de uma build customizada (verifique o VID:PID e o status da MR primeiro); se as peculiaridades do `mbedtls3` se aplicam nessa distro | Os passos de build do qmake; a lógica do wrapper `LD_LIBRARY_PATH` |
| 3. Permissões udev (doc 03) | O VID:PID exato do dispositivo alvo | A regra em si (trocando VID:PID); a restrição de numeração "antes de `73-seat-late.rules`" |
| 4. Modelo servidor/cliente (doc 04) | Nada — esse desenho é hardware-agnóstico | Tudo: usar `--server` + `--client --nodetect`, encadear dispositivos numa chamada só |
| 5. Persistência de boot (doc 05) | Se o compositor/DE alvo tem autostart XDG de verdade (Hyprland/Omarchy não tem) | A estrutura geral (lançar servidor no login + reaplicar cor pouco depois do boot); o polling de espera pelo servidor via `/dev/tcp` |
| 6. Sincronização de cor (doc 06) | **Toda** a tabela de índice de dispositivo (GPU, RAM, mouse, teclado, placa-mãe — refaça `--list-devices` do zero); o caminho/schema do `colors.toml` se o sistema de temas não for o Omarchy | O script seletor de cor (só a leitura do arquivo de entrada muda); a estrutura do script de sincronização |

## Perguntas a fazer logo no início numa máquina nova

1. **O OpenRGB stock já detecta tudo?** Rode `openrgb --list-devices --noautoconnect` antes de tocar em qualquer coisa. Se RAM, GPU, mouse e teclado já aparecem todos, os docs 01-03 provavelmente não se aplicam — pule direto pros docs 04-06.
2. **Existe suporte oficial pro teclado agora?** Busque o VID:PID do dongle (via `lsusb`) nas issues/MRs do GitLab do OpenRGB antes de compilar do zero. A MR rastreada por este projeto pode já ter sido mesclada.
3. **O compositor/DE alvo tem autostart XDG de verdade?** Não assuma que `--autostart-enable` funciona — teste com um `.desktop` trivial primeiro (ver doc 05).
4. **Quais dispositivos têm entradas fantasma/duplicadas, e quais modos cada um suporta?** Sempre reconstrua a tabela do doc 06 do zero; nunca copie os números de índice.

## Riscos conhecidos / itens em aberto (deste projeto, nesta máquina)

- Persistência a reboot foi verificada por **simulação**, não por um reboot de verdade (ver doc 05). Vale confirmar com uma reinicialização real assim que for conveniente.
- O RGB por tecla do teclado depende de uma issue upstream ainda aberta (#4232, "AULA F75 Keyboard"). Revisitar a build periodicamente.
- A entrada de GPU "fantasma" (índice 2) é ignorada, não removida/desabilitada — se uma atualização futura do OpenRGB mudar a ordem de detecção, reconfirme qual índice é o real antes de reusar a tabela do doc 06.
- O algoritmo de cor "secundária" (distância de matiz) foi escrito e testado, mas está desativado nesta máquina por causa de LEDs desgastados — está preservado no doc 06 caso valha a pena reativar numa máquina com hardware mais novo.

## Ideias pra transformar isso num software de verdade

O que existe hoje é uma pilha de scripts pessoais, específicos desta máquina e deste ambiente de desktop. Um caminho razoável pra generalizar, em ordem crescente de esforço:

1. **Configuração externalizada.** Mover a tabela de índice de dispositivo do doc 06 (hoje hardcoded no script bash) pra um arquivo de config declarativo (YAML/TOML/JSON): `{device: 0, mode: direct}`, `{device: 6, mode: direct, zones: [all]}`, etc. Isso sozinho já tornaria o script de sincronização reusável em qualquer máquina só trocando um arquivo de config, sem editar bash.
2. **Auto-descoberta de dispositivo fantasma.** Em vez de descobrir manualmente qual índice de GPU é o "de verdade" (testando cores e observando), escrever uma rotina de calibração que aplica uma cor de teste em cada dispositivo candidato, pergunta ao usuário qual mudou (ou, mais ambicioso, tenta inferir via alguma característica do dispositivo), e salva o resultado na config.
3. **Abstração da fonte de tema.** Trocar a leitura direta do `colors.toml` do Omarchy por um adaptador plugável — um "provedor de cor" que pode ser Omarchy hoje, e GTK/KDE/pywal/uma cor fixa definida manualmente amanhã, todos implementando a mesma interface simples "retorne uma cor primária (e opcionalmente secundária)".
4. **Wrapper de instalação.** Um script único (`install.sh`) que: detecta a distro e ajusta nomes de pacote; detecta se um teclado AULA sem suporte está presente e oferece compilar a MR automaticamente; detecta o compositor/DE e escolhe entre `autostart.lua`, `exec-once` do Hyprland puro, ou uma unit `systemd --user`; gera a regra udev a partir do VID:PID detectado; e por fim registra os hooks (ou os `exec-once`/units equivalentes).
5. **Interface mínima.** Uma vez que a config está externalizada (item 1), uma pequena TUI ou app de bandeja poderia listar os dispositivos detectados, deixar o usuário escolher visualmente o mapeamento cor→dispositivo (inclusive reativando o modo de duas cores do doc 06 com um toggle), e persistir isso — sem precisar editar nenhum script à mão.
6. **Reempacotamento como pacote real.** Se isso amadurecer o bastante, embrulhar como um pacote AUR (ou um `.deb`/`.rpm` equivalente) que instala os scripts, a regra udev, e um hook de instalação pós-pacote que faz as perguntas do item 4 — tornando "outra máquina" uma questão de `pacman -S` em vez de seguir estes sete documentos manualmente.

Nenhum desses passos é urgente enquanto o projeto serve só esta máquina — mas cada um reduz o quanto dos docs 01-06 precisaria ser refeito manualmente na próxima vez.
