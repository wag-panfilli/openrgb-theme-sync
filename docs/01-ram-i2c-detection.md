# 1. Detecção da RAM via I2C (domínio kernel / ACPI)

**Objetivo:** fazer os controladores RGB embutidos na RAM aparecerem pro OpenRGB. Sem essa correção, o OpenRGB detecta GPU, mouse e placa-mãe normalmente, mas nenhum dispositivo DRAM aparece no `--list-devices`, não importa qual software seja usado.

## Causa raiz

Pentes de RAM RGB em placas AM4/AM5 expõem seu controlador (geralmente um chip ENE) via **SMBus** da placa-mãe, que o driver de kernel `i2c_piix4` acessa. Nesta placa (Gigabyte B550 AORUS PRO, controlador SMBus da AMD FCH, PCI ID `1022:790b`):

- O `lspci` mostra o controlador SMBus presente.
- O `i2c_piix4` carrega como driver.
- ...mas nunca registra um adaptador I2C funcional. O `i2cdetect -l` só lista os adaptadores I2C da NVIDIA (GPU) — nada do chipset AMD.

Esse é o clássico **conflito de recursos entre ACPI e SMBus**, visto em várias placas AMD/Gigabyte: as tabelas ACPI do firmware reservam a mesma região de I/O que o controlador SMBus precisa, e o Linux se recusa a deixar um driver reivindicar uma região que a ACPI já reservou, a menos que seja instruído a permitir isso.

## Correção

Adicionar `acpi_enforce_resources=lax` à linha de comando do kernel. Isso diz ao kernel pra permitir que drivers reivindiquem regiões de I/O que a ACPI reservou, em vez de recusar e registrar um conflito.

**Como a cmdline do kernel é definida de fato depende do bootloader** — errar aqui faz o parâmetro não surtir efeito nenhum, silenciosamente:

- **Limine sem Unified Kernel Image** (`ENABLE_UKI=no` em `/etc/default/limine`): a fonte de verdade real é a variável `KERNEL_CMDLINE[default]` em `/etc/default/limine`. Um alvo de edição comumente sugerido, `/etc/kernel/cmdline`, existe nesses sistemas mas **não é usado** — editá-lo não tem efeito nenhum.
  ```bash
  # /etc/default/limine
  KERNEL_CMDLINE[default]="... parâmetros existentes ... acpi_enforce_resources=lax"
  ```
  Depois, regenere a config de boot e confirme que o novo parâmetro entrou:
  ```bash
  sudo limine-mkinitcpio
  grep acpi_enforce /boot/limine.conf   # confirma que está na linha cmdline: gerada
  ```
- **GRUB**: edite `GRUB_CMDLINE_LINUX_DEFAULT` em `/etc/default/grub`, depois `sudo grub-mkconfig -o /boot/grub/grub.cfg`.
- **systemd-boot / Limine com UKI**: edite a cmdline do kernel na entrada `.conf` relevante em `/boot/loader/entries/` (ou onde quer que a UKI seja construída), depois reconstrua a UKI.

É necessário reiniciar — este é um parâmetro de kernel definido em tempo de boot, nada menos que isso o aplica.

## Verificando a correção

```bash
cat /proc/cmdline | grep -o acpi_enforce_resources=lax   # confirma que está ativo

i2cdetect -l
# Antes: só linhas "NVIDIA i2c adapter N"
# Depois: também 3 linhas "SMBus PIIX4 adapter port N"

openrgb --list-devices --noautoconnect
# Antes: nenhum dispositivo DRAM
# Depois: dois dispositivos "ENE DRAM", 8 LEDs cada, em um dos novos adaptadores SMBus
```

## Notas de portabilidade

- Essa correção é específica pro chipset **AMD/Gigabyte** na sua manifestação exata, mas o problema de fundo ("ACPI reserva a região de I/O do SMBus") é comum o bastante em outras placas AMD (e ocasionalmente Intel) pra valer a pena tentar primeiro se a RAM RGB não aparecer.
- Se a máquina de destino inicializa via GRUB ou systemd-boot em vez de Limine, ajuste o passo "como editar a cmdline" adequadamente — o parâmetro de kernel em si (`acpi_enforce_resources=lax`) é agnóstico ao bootloader.
- Se a RAM ainda não aparecer depois disso, e o `i2cdetect -l` ainda não mostrar nenhum adaptador SMBus do chipset, a próxima coisa a tentar é forçar o driver a se vincular com um ID explícito: `i2c-piix4.force_id=0x790b` (ou o PCI ID relevante pro chipset), adicionado da mesma forma.
- Esse passo é pré-requisito pro OpenRGB detectar RAM de forma alguma — não é específico da build customizada pro teclado AULA descrita no doc 02, e se aplica igualmente ao OpenRGB stock/upstream.
