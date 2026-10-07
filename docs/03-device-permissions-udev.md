# 3. Permissões de Dispositivo (domínio udev)

**Objetivo:** deixar o OpenRGB, rodando como usuário normal (não-root), ler e escrever nos nós de dispositivo `hidraw` do dongle do teclado AULA.

## O problema

O dongle se enumera como duas interfaces HID:
```
$ cat /sys/class/hidraw/hidraw2/device/uevent
HID_ID=0003:00003554:0000FA09
HID_NAME=Compx 2.4G Wireless Receiver

$ ls -la /dev/hidraw2 /dev/hidraw3
crw------- 1 root root 243, 2 ... /dev/hidraw2
crw------- 1 root root 243, 3 ... /dev/hidraw3
```
Os dois nós são `root`-only por padrão, sem ACL (sem `+` nos bits de permissão) — diferente dos outros periféricos HID da máquina (mouse, controlador da placa-mãe), que já tinham um `+` de uma regra udev existente. Sem uma regra concedendo acesso, o OpenRGB (rodando como o usuário do desktop) consegue abrir o dispositivo, mas qualquer handshake de leitura/escrita ou falha completamente ou trava.

O OpenRGB upstream traz um arquivo de regras udev (`60-openrgb.rules`) com uma linha por dispositivo conhecido, no formato:
```
SUBSYSTEMS=="usb|hidraw", ATTRS{idVendor}=="XXXX", ATTRS{idProduct}=="YYYY", TAG+="uaccess", TAG+="SomeDeviceName"
```
Como esse dongle AULA ainda não está em nenhuma versão oficial do OpenRGB (ver doc 02), o VID:PID dele não está nesse arquivo. Uma regra customizada precisa ser adicionada.

## A regra

`/etc/udev/rules.d/61-openrgb-aula-f99.rules` (cópia também mantida em `scripts/61-openrgb-aula-f99.rules` neste projeto):
```
# AULA F99/F75 wireless keyboard dongle (Sinowealth) - grants user access for OpenRGB.
# Not yet in upstream openrgb's udev rules (pending MR !3027). Must load before
# /usr/lib/udev/rules.d/73-seat-late.rules (priority 73) for the uaccess builtin to apply.
SUBSYSTEMS=="usb|hidraw", ATTRS{idVendor}=="3554", ATTRS{idProduct}=="fa09", TAG+="uaccess", TAG+="AULA_F99_F75"
```

## A pegadinha que custou tempo de debug de verdade: ordem das regras

A tag `uaccess` sozinha **não faz nada** por si só — é só um marcador. O que de fato concede a ACL é um comando builtin disparado por uma regra *diferente*, vinda do systemd:
```
# /usr/lib/udev/rules.d/73-seat-late.rules
TAG=="uaccess|xaccess-*", ENV{MAJOR}!="", RUN{builtin}+="uaccess"
```
O udev processa os arquivos de regra em ordem alfabética de nome de arquivo, mesclando `/etc/udev/rules.d/` e `/usr/lib/udev/rules.d/` numa única sequência ordenada. **Uma regra que define `TAG+="uaccess"` só funciona se for processada *antes* de `73-seat-late.rules` rodar o builtin que lê essa tag.**

A primeira tentativa dessa regra se chamava `99-openrgb-aula-f99-test.rules`. Como `99 > 73`, ela carregava *depois* de `73-seat-late.rules` já ter rodado — a tag era definida, mas tarde demais pra qualquer coisa agir sobre ela. Sintoma: o `udevadm test` mostrava a regra batendo e a tag sendo aplicada, mas o `getfacl /dev/hidraw2` não mostrava nenhuma entrada de ACL, e o dispositivo continuava `root`-only não importava quantas vezes se rodasse `udevadm control --reload-rules && udevadm trigger`.

**Correção:** renomear o arquivo pra ordenar antes de `73-`. Escolhi `61-` pra bater com a convenção do `60-openrgb.rules` upstream (ou seja, regras "próximas ao openrgb" se agrupam em torno de 60-61).

## Como verificar uma regra udev assim, corretamente

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger --action=add /sys/class/hidraw/hidrawN   # rode de novo para cada nó afetado

getfacl /dev/hidrawN
# Resultado correto inclui uma linha tipo: user:<seuusuario>:rw-
# (não só o padrão user::rw- / group::--- / other::---)
```
O `udevadm test /sys/class/hidraw/hidrawN` é útil pra confirmar que uma regra *bate* e *iria* definir a tag, mas ele **não** aplica ACLs de verdade (é um dry-run) — não confie só nele pra confirmar que a correção funcionou; sempre siga com uma checagem real de `getfacl` depois de um trigger de verdade.

## Notas de portabilidade

- O VID:PID (`3554:fa09`) é específico do dongle AULA F99/F75. Pra um dispositivo diferente, pegue os valores via `lsusb` e/ou `cat /sys/class/hidraw/hidrawN/device/uevent` (campo `HID_ID`, formato `barramento:vendor:product` em hex).
- A restrição "precisa ordenar antes de `73-seat-late.rules`" é uma propriedade das regras que o systemd-udevd já traz, não do OpenRGB nem deste dispositivo específico — ela se aplica a *qualquer* regra `uaccess` customizada num sistema Linux baseado em systemd. Sempre numere regras udev customizadas que concedem acesso na faixa 50-72 (batendo ou logo depois do `60-openrgb.rules` upstream), nunca 90+.
- Se a versão do systemd da distro alvo reestruturar esses números de regra, rode `grep -rn uaccess /usr/lib/udev/rules.d/*seat*` pra achar o arquivo/prioridade real que roda o builtin, e numere a regra customizada abaixo disso.
