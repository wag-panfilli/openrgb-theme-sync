# 2. Build Customizada do OpenRGB pro Teclado AULA

**Objetivo:** fazer o OpenRGB reconhecer e controlar o dongle wireless 2.4GHz de um teclado RGB AULA, que a versão stock/upstream do OpenRGB não suporta.

## Por que uma build customizada é necessária

O `lsusb` mostra o dongle como:
```
ID 3554:fa09 Compx 2.4G Wireless Receiver
```
Esse par VID:PID pertence a um controlador de teclado wireless baseado em Sinowealth, usado por vários modelos AULA. No momento em que isso foi escrito, o suporte a ele existe só como uma **merge request em draft, não mesclada** no GitLab:

- Issue: [#5166 "AULA F99 Keyboard"](https://gitlab.com/CalcProgrammer1/OpenRGB/-/issues/5166) e a relacionada [#4232 "AULA F75 Keyboard"](https://gitlab.com/CalcProgrammer1/OpenRGB/-/issues/4232)
- MR: [!3027 "Add support for Aula F99 wireless dongle"](https://gitlab.com/CalcProgrammer1/OpenRGB/-/merge_requests/3027) — depende da !3026 (suporte genérico a teclado wireless)

Nenhuma das duas está em versão lançada, então a única forma de ter esse hardware funcionando hoje é compilar o OpenRGB a partir dessa branch.

Antes de gastar tempo nisso, verifique se a MR já foi mesclada: busque no `gitlab.com/CalcProgrammer1/OpenRGB` por issues "AULA F75"/"AULA F99", ou simplesmente tente atualizar o pacote stock do `openrgb` da distro e rodar `--list-devices` de novo.

## Passos da build (Arch Linux; adapte os nomes de pacote pra outras distros)

```bash
# 1. Dependências de build (nomes de pacote específicos do Arch)
sudo pacman -S --needed git make gcc qt5-base qt5-tools libusb hidapi mbedtls3 pkgconf

# 2. Clonar e mudar pra branch da MR
git clone https://gitlab.com/CalcProgrammer1/OpenRGB.git
cd OpenRGB
git fetch origin merge-requests/3027/head:mr-3027
git checkout mr-3027
# Confirme que já inclui os commits da !3026 (suporte genérico a teclado wireless) —
# incluía, no commit a partir do qual isso foi compilado; se não incluir, busque e
# mescle essa MR também.

# 3. Configurar com qmake (Qt5, não Qt6 — a build de release depende do qt5-base)
qmake-qt5 OpenRGB.pro

# 4. Compilar
make -j$(nproc)
```

## Duas falhas de build específicas do Arch, e suas correções

Essas são **peculiaridades de empacotamento do pacote `mbedtls3` do Arch**, não bugs do OpenRGB upstream, então podem não se aplicar em outras distros — mas vale reconhecer a assinatura das falhas caso apareçam.

### a) Header faltando: `mbedtls/ctr_drbg.h`
```
dependencies/hueplusplus-1.2.0/src/EntertainmentMode.cpp:24:10: fatal error:
mbedtls/ctr_drbg.h: Arquivo ou diretório inexistente
```
O pacote `mbedtls3` do Arch instala os headers em `/usr/include/mbedtls3/mbedtls/`, não no caminho clássico `/usr/include/mbedtls/` que o `.pro` do OpenRGB espera (e não existe um pacote de compatibilidade `mbedtls2` que forneça o caminho clássico nesse sistema). O próprio OpenRGB traz junto uma cópia do código-fonte do mbedtls 3.2.1 com headers no caminho correto — aponte o compilador pra ela em vez de remendar o project file:
```bash
CPATH="$PWD/dependencies/mbedtls-3.2.1/include" make -j$(nproc)
```

### b) Ferramenta faltando: `lrelease`
```
/bin/sh: linha 1: /usr/bin/lrelease: Arquivo ou diretório inexistente
make: *** [Makefile:3912: .qm/OpenRGB_it_IT.qm] Error 127
```
O `qt5-base` não traz as ferramentas Qt Linguist. Instale o `qt5-tools` (fornece o `lrelease`) e rode o make de novo.

### c) Bibliotecas faltando na hora de linkar: `-lmbedtls`, `-lmbedcrypto`, `-lmbedx509`
```
/usr/bin/ld: não foi possível localizar -lmbedx509
/usr/bin/ld: não foi possível localizar -lmbedtls
/usr/bin/ld: não foi possível localizar -lmbedcrypto
```
Mesma causa raiz do item (a), mas pra bibliotecas: o `mbedtls3` do Arch só expõe os symlinks `.so` sem versão (os que o linker procura via `-lmbedtls` etc.) em `/usr/lib/mbedtls3/`, fora do caminho de busca padrão do linker `/usr/lib/`. Aponte o linker pra lá também:
```bash
LIBRARY_PATH=/usr/lib/mbedtls3 make -j$(nproc)
```

### Juntando tudo
O comando de build completo e funcional no Arch:
```bash
CPATH="$PWD/dependencies/mbedtls-3.2.1/include" LIBRARY_PATH=/usr/lib/mbedtls3 make -j$(nproc)
```
Isso produz um binário `openrgb` na raiz do repositório (~9,4 MB).

## Requisito de runtime: `LD_LIBRARY_PATH`

Como o binário linka contra essas mesmas bibliotecas mbedtls3 fora do caminho padrão, ele também precisa de `LD_LIBRARY_PATH=/usr/lib/mbedtls3` definido **toda vez que roda**, ou falha ao iniciar com um erro de carregamento de biblioteca compartilhada. Em vez de exigir que todo chamador lembre disso, encapsule:

`scripts/openrgb-mr3027` (instalado em `~/.local/bin/openrgb-mr3027`):
```sh
#!/bin/sh
exec env LD_LIBRARY_PATH=/usr/lib/mbedtls3 "$HOME/.local/share/openrgb-aula-build/openrgb" "$@"
```
Tudo mais neste projeto — hooks, autostart, testes manuais — chama `openrgb-mr3027`, nunca o caminho do binário cru, então essa correção é aplicada de forma uniforme.

## Estrutura instalada nesta máquina

```
~/.local/share/openrgb-aula-build/
├── openrgb        # o binário compilado (~9,4 MB)
├── COMMIT.txt      # hash exato do commit git compilado, para reprodutibilidade
└── README.txt      # as mesmas instruções de rebuild deste doc, mantidas junto do binário
~/.local/bin/openrgb-mr3027   # o wrapper de LD_LIBRARY_PATH acima
```
O clone git completo de ~2,6GB (histórico + artefatos de build) **não** é mantido — só o binário final, o hash do commit, e as instruções pra recompilar se necessário.

## O que você ganha, e o que não ganha

Uma vez rodando, `openrgb-mr3027 --list-devices` mostra o dongle como um `Sinowealth Wireless Keyboard`, com uma única zona `Keyboard`, modo `Direct`, um LED. Isso dá controle total de **cor sólida** (`--mode direct --color RRGGBB` muda o teclado inteiro pra uma cor, confirmado funcionando de ponta a ponta).

**RGB por tecla não está disponível pra todo modelo AULA.** O mapa de matriz de LEDs por tecla da MR (`SinowealthWirelessFullColorDevices.cpp`) só tem uma entrada pro model ID `0xA4` ("AULA F99"):
```cpp
const sinowealth_device_map sinowealth_wireless_keyboards{
    { 0xA4, { "AULA F99", aula_f99_layout } }
};
```
Um modelo AULA diferente, reportando um model ID diferente (consultado via o handshake `GetModelId()` do dispositivo, registrado no log ao iniciar como algo tipo `Model ID 0xcd not recognized`), cai automaticamente no controlador genérico de cor sólida de zona única (`RGBController_SinowealthWirelessKeyboardSolid`) — que foi exatamente o que aconteceu com o AULA F75 nesta máquina (model ID `0xCD`). Isso é um fallback correto e proposital, não um crash: o teclado continua totalmente utilizável pra sincronização de tema em cor sólida, só não por tecla.

**Peculiaridade de firmware importante de saber**: o firmware do dongle wireless só mantém uma cor em "modo Direct" enquanto continua recebendo um fluxo constante de pacotes — veja o próprio comentário do driver:
```cpp
/*---------------------------------------------------------*\
| The Sinowealth Wireless Keyboard requires a steady stream |
| of packets in order to not revert out of direct mode.     |
| Start a thread to continuously refresh the device         |
\*---------------------------------------------------------*/
```
O OpenRGB roda uma thread de keepalive em segundo plano por instância de controlador de teclado exatamente por esse motivo. **Isso significa que a cor se perde no instante em que o processo do OpenRGB que segura essa conexão termina** — por isso o processo precisa ficar rodando de forma persistente em vez de ser chamado uma vez e fechado; ver docs 04 e 05.

## Notas de portabilidade

- Reverifique o status da MR/issue antes de recompilar em uma máquina nova — se já foi mesclada, pule este doc inteiro e use o pacote stock do OpenRGB da distro.
- As peculiaridades de empacotamento do `mbedtls3` (itens a, c acima) são específicas do Arch. Em outras distros, se pacotes `mbedtls`/`mbedtls-dev` ou similares instalarem nos caminhos padrão, a build via qmake pode simplesmente funcionar sem as sobreposições de `CPATH`/`LIBRARY_PATH`.
- Confirme o VID:PID exato do teclado alvo via `lsusb` primeiro — `3554:fa09` é especificamente o dongle wireless do AULA F99/F75; um modelo AULA diferente (ou uma conexão com fio em vez do dongle 2.4G) vai reportar de forma diferente e pode precisar de um caminho de código diferente, ou nenhum.
- Se o teclado alvo reportar model ID `0xA4` (um AULA F99 de verdade), ele vai ganhar RGB por tecla completo nessa mesma build — o fallback descrito acima só se aplica a model IDs não mapeados, como o F75 desta máquina.
