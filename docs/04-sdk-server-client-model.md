# 4. Modelo Servidor/Cliente SDK (domínio de arquitetura de aplicação)

**Objetivo:** deixar múltiplos gatilhos independentes (uma troca de tema, um evento de boot, um futuro terceiro script) definirem cores de dispositivo, sem nenhum deles brigar por acesso direto ao hardware.

## Por que não simplesmente chamar `openrgb-mr3027 --device N --color X` direto, toda vez?

Dois problemas descartam essa abordagem:

1. **O teclado precisa de uma conexão persistente.** Como visto no doc 02, o firmware do dongle AULA só mantém uma cor sólida enquanto continua recebendo um fluxo constante de pacotes de "modo Direct"; o OpenRGB modela isso com uma thread de keepalive em segundo plano atrelada ao ciclo de vida do processo que abriu o dispositivo. Se cada troca de cor disparasse um processo `openrgb-mr3027` novinho, que abre o dispositivo, define uma cor e encerra, **a cor do teclado voltaria ao estado anterior no instante em que esse processo fechasse** — que foi exatamente o que se observou na primeira tentativa (fechar o app depois de definir uma cor fazia o teclado voltar imediatamente pro efeito próprio dele).
2. **Múltiplos processos independentes abrindo o mesmo hardware competem entre si.** Mesmo para dispositivos que não precisam de thread de keepalive, ter vários processos efêmeros redetectando e escrevendo independentemente nos mesmos dispositivos I2C/HID convida ao tipo de condição de corrida/queda silenciosa de escrita que este projeto encontrou durante o desenvolvimento da sincronização de tema (ver doc 06).

## O modelo: um servidor persistente, muitos clientes efêmeros

O OpenRGB tem um modo cliente/servidor embutido feito exatamente pra isso: `--server` inicia um pequeno servidor TCP (porta padrão `6742`) que é dono de todo o hardware detectado e o mantém sob controle contínuo (incluindo rodar a thread de keepalive do teclado); `--client` faz uma dada chamada agir como um proxy fino, encaminhando `--device`/`--mode`/`--color` etc. pro servidor a que se conecta, em vez de tocar o hardware diretamente.

```
um processo de vida longa:  openrgb-mr3027 --startminimized --server
                             (dono de todo dispositivo, roda pra sempre, minimizado na bandeja)

várias chamadas efêmeras:   openrgb-mr3027 --client --nodetect --device N --color X ...
                             (conecta via TCP em localhost:6742, envia o comando,
                             encerra — nunca toca /dev/hidrawN ou /dev/i2c-N diretamente)
```

`--nodetect` é passado em toda chamada de cliente pra o processo efêmero não perder tempo (e arriscar conflito) redetectando hardware que o servidor já detectou.

É por isso que o servidor **precisa** estar rodando antes de qualquer coisa tentar mudar cores, e por que ele precisa sobreviver a reboots — ver doc 05.

## Armadilha de performance: um processo cliente por dispositivo é muito mais lento do que parece

Uma versão inicial do script de sincronização de tema (doc 06) disparava uma chamada `openrgb-mr3027 --client` separada por dispositivo, com receio de que encadear múltiplos blocos `--device` numa única chamada fosse causar corrida (um teste anterior de chamada combinada pareceu descartar silenciosamente as atualizações de RAM/GPU). Essa abordagem "um processo por dispositivo" funcionava, mas uma sincronização completa de 6 dispositivos levava **~15-18 segundos** — claramente lento demais pra algo que deveria parecer instantâneo depois de uma troca de tema.

Cronometrar uma única chamada de cliente revelou o motivo:
```bash
$ time openrgb-mr3027 --client --nodetect --device 0 --mode direct --color FF00FF
real    0m2.713s
user    0m0.044s
sys     0m0.040s
```
Quase todo esse 2,7s é espera de relógio, não trabalho de CPU. A causa está na thread de conexão do `NetworkClient.cpp`:
```cpp
if(port.tcp_client_connect() == true) {
    ...
} else {
    printf("Connection attempt failed\n");
}
...
connection_cv.wait_for(lock, 1s);   // <-- só tenta de novo uma vez por segundo
```
A primeiríssima tentativa de conexão de um processo cliente recém-iniciado costuma falhar (imprime "Connection attempt failed"), e o loop de retry só tenta de novo depois de um segundo inteiro. Multiplique isso por um processo por dispositivo e os segundos se acumulam rápido.

**Correção:** disparar exatamente **uma** chamada de `openrgb-mr3027 --client`, encadeando o bloco `--device N --mode M --color C` de cada dispositivo na mesma invocação. Isso paga o custo de conexão de ~1-3s uma vez só, não uma vez por dispositivo — reduzindo uma sincronização de 6 dispositivos de ~15-18s pra **menos de 3s**. (A observação anterior de que "chamadas combinadas descartam silenciosamente RAM/GPU", que motivou dividir tudo em primeiro lugar, se mostrou depois um alarme falso vindo de um problema não relacionado durante o desenvolvimento, não uma corrida real — retestado deliberadamente depois e confirmado confiável em várias trocas de tema.)

O parsing da CLI suporta esse encadeamento nativamente: toda nova flag `--device` fecha a combinação anterior de dispositivo+zona+modo+cor como uma unidade completa antes de começar uma nova (confirmado lendo o loop de parsing de opções do `cli.cpp`), então `--device 0 ... --device 1 ... --device 6 --zone 3 ...` tudo num único comando aplica cada bloco de forma independente e correta.

## Notas de portabilidade

- A porta `6742` é a porta SDK padrão do OpenRGB; só um servidor deve ocupá-la (rodar `--server` duas vezes ao mesmo tempo, ou rodar tanto o OpenRGB do pacote stock quanto o OpenRGB de uma build customizada com `--server` simultaneamente, vai conflitar). Se uma instalação stock do OpenRGB já estiver usando essa porta pra outra coisa na máquina alvo, ou pare-a ou mude essa build customizada pra um `--server-port` diferente.
- O comportamento "a primeira tentativa de conexão costuma falhar" parece ser uma peculiaridade de implementação do OpenRGB, não algo específico desta configuração, então a otimização de "uma única chamada combinada" deve valer em qualquer máquina usando esse mesmo padrão cliente/servidor.
- Se um dispositivo futuro precisar de escritas de fato sequenciais e com atraso (um dispositivo comprovadamente com corrida quando comandos chegam um atrás do outro), isso apareceria como um sintoma real e reproduzível — reintroduza um loop por dispositivo com um `sleep` curto entre chamadas só se isso for de fato observado, em vez de por padrão.
