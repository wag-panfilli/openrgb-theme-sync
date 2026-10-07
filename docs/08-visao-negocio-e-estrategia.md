# 8. Visão, Modelo de Negócio e Estratégia de Release

> Documento de estratégia (não técnico) para transformar o `openrgb-theme-sync`,
> hoje uma pilha de scripts pessoais rodando em uma máquina, num projeto
> open-source adotável pela comunidade. Complementa os docs técnicos 01–07.
> Escrito em 2026-09-25 como base para retomar depois.

---

## 1. O reframe que muda tudo

Hoje o projeto se apresenta como *"sincronização de RGB do tema do Omarchy"*.
Para release, o enquadramento certo é mais amplo:

> **Um daemon de RGB dirigido por tema, sobre o OpenRGB — com o Omarchy sendo
> apenas um dos provedores de cor.**

Essa mudança de escopo:
- Amplia o público de "usuários de Omarchy" para **qualquer usuário de OpenRGB**
  que queira o RGB seguindo o tema, em qualquer distro.
- Faz o objetivo "distros base Arch" **cair fora naturalmente** — deixa de ser a
  fronteira do projeto e vira só o primeiro alvo de teste.

**Gancho de uma linha (para README e anúncio):**
> *"Um controlador de RGB, dirigido por tema. Seu PC inteiro numa cor só,
> seguindo seu tema, atualizando sozinho — sem cinco softwares proprietários,
> sem bandeja, sem login. Um daemon."*

---

## 2. O problema / o mercado

**A dor real (documentada e virou meme):** no Windows, controlar o RGB de um PC
com peças de marcas diferentes exige vários softwares proprietários que brigam
entre si na bandeja — iCUE (Corsair), Armoury Crate (Asus), Mystic Light (MSI),
RGB Fusion (Gigabyte), Synapse (Razer). Cada um come RAM, muitos exigem login, e
cada RGB vira uma "ilha" que não conversa com as outras.

**O que o OpenRGB já resolve:** ele nasceu justamente para ser *um controlador
para reinar sobre todos* — abstrai o inferno de protocolo por-dispositivo (ENE,
ITE, Aura, Mystic, protocolos proprietários) numa API única.

**O buraco que ESTE projeto preenche:** o OpenRGB unifica o *controle*, mas não
faz o RGB **seguir o tema automaticamente**. É "controle unificado"; este projeto
adiciona "**controle unificado que se pinta sozinho**". Nenhum dos softwares de
fabricante tenta isso.

---

## 3. Proposta de valor

- **Unificação:** um daemon, uma cor, todos os dispositivos — em vez de N softwares.
- **Automação:** a cor acompanha o accent do tema ativo, atualizando sozinha em
  ~3s após troca de tema ou boot.
- **Leveza / soberania:** sem bandeja, sem login, sem telemetria. Roda como serviço.
- **No Linux, muitas vezes é *a* forma de fazer** (não só a mais bonita): boa parte
  desses RGBs só é controlável via OpenRGB no Linux — então automatizar em cima
  dele não é um luxo, é o caminho.

**Dois públicos de uma vez:**
1. Entusiasta de Linux / ricing — quer o RGB parando de ser o único pedaço que não
   segue o rice.
2. Refugiado do Windows — cansado da guerra de softwares proprietários.

---

## 4. Princípio de arquitetura: "baixo nível" no lugar certo

Premissa a corrigir: *"quanto mais baixo nível, melhor para driblar problemas
pontuais"* — está **metade certa**.

- ❌ **Descer ABAIXO do OpenRGB** (falar direto com I2C/hidraw/SMBus) = **menos**
  portabilidade. O OpenRGB **é** a camada de abstração de hardware; reimplementá-la
  faria cada placa/RAM/GPU nova do usuário virar um caso pontual seu. Não escala.
- ✅ **Subir para mecanismos de SO mais universais** = é aqui que os pontuais morrem:
  - `autostart.lua` do Hyprland + hooks do Omarchy → **`systemd --user`**
    (roda em qualquer distro com systemd, agnóstico de compositor/DE).
  - Hook `theme-set.d` do Omarchy → **daemon com `inotify`** vigiando o arquivo de
    cor (re-sincroniza quando qualquer coisa mexe nele, sem depender do sistema de
    tema específico).

Ou seja: não se desce abaixo do OpenRGB; sobe-se para cima do DE.

---

## 5. Arquitetura em camadas trocáveis (o alvo do release)

| Camada | Papel | Estado hoje | Alvo para release |
|---|---|---|---|
| **1. Fonte de cor (provider)** | "Devolva uma cor primária" | Lê `colors.toml` do Omarchy hardcoded | Interface plugável: Omarchy, pywal, wallust, accent GTK/KDE, hex fixo |
| **2. Mapa de dispositivos** | Quais devices, quais modos/zonas | Tabela de índice hardcoded no bash | **Config TOML** + comando **`calibrate`** (pinta cada device, pergunta "qual mudou?") |
| **3. Motor de aplicação** | Aplica a cor via OpenRGB | Server SDK persistente + cliente efêmero encadeando `--device` | **Manter** — já é hardware-agnóstico |
| **4. Ciclo de vida** | Subir no boot, re-sincronizar | `autostart.lua` + hooks Omarchy | **`systemd --user`** + **watcher `inotify`** |
| **5. Bootstrap por-máquina** | Preparar o ambiente | Manual (docs 01–03) | **`install.sh`** detector (cmdline, VID:PID udev, build custom) |

Isso é a materialização das ideias #1 e #3 do `07-portability-checklist.md`,
levadas a sério.

---

## 6. As duas decisões que mais decidem a adoção

1. **Desacoplar o theme-sync da build custom do OpenRGB.**
   Hoje o projeto acopla os dois (a build custom existe por causa do teclado AULA).
   Para release, a ferramenta **tem que funcionar com OpenRGB *stock*** no caso
   comum. A build custom do AULA vira uma **receita opcional documentada** para
   quem tem esse teclado. *Ninguém adota um projeto que exige compilar o OpenRGB.*

2. **Empurrar o suporte do AULA para o upstream.**
   A contribuição de maior alavancagem para a comunidade **não é o script** — é a
   **MR !3027** mesclada no OpenRGB. Quando entrar, o custom build some da equação
   para todo mundo. Acompanhar e ajudar a empurrar (issue upstream #4232).

---

## 7. Modelo de negócio (honesto)

Isto é, antes de tudo, uma **contribuição open-source de nicho** — não um produto
de receita. Ser honesto sobre isso evita construir para um retorno que não vem.

**Realidade de mercado:** público nichado, porém apaixonado (ricers + comunidade
OpenRGB). Alcance de "estrelas no GitHub e gratidão", não de faturamento.

**O retorno real (o que de fato se ganha):**
- **Reputação / portfólio** — um projeto técnico bem feito, com engenharia de
  sistema real (server/cliente SDK, systemd, udev, build custom). Vitrine forte.
- **Aprendizado** e a satisfação de resolver um problema real da comunidade.
- **Rede** — contribuir upstream no OpenRGB coloca seu nome num projeto relevante.

**Caminhos de sustentabilidade, se um dia fizer sentido (do mais leve ao mais
pesado — nenhum urgente):**
1. **GitHub Sponsors / doações** — botãozinho no README. Cobre café, não aluguel.
2. **Open-core** — core gratuito; uma camada "pro" opcional (ex.: TUI/app de
   bandeja polido, perfis avançados, efeitos multi-cor) — só se a base crescer.
3. **Nada** — deixar puramente comunitário é uma escolha válida e legítima.

**Diretriz:** decidir o modelo **não bloqueia** o release. Solta como OSS puro
com um Sponsors opcional; monetização é uma porta que se abre depois, se abrir.

---

## 8. Roadmap de release (fases)

- **Fase 0 — hoje:** funciona numa máquina (Arch + Omarchy/Hyprland). Pessoal,
  scripts, acoplado à build custom.
- **Fase 1 — "roda na máquina dos outros" (Arch + stock):**
  desacoplar da build custom · config TOML + `calibrate` · `systemd --user` +
  `inotify` no lugar dos hooks. Meta: outro usuário Arch com OpenRGB stock instala
  e funciona.
- **Fase 2 — "além do Omarchy":** providers plugáveis (pywal, wallust, GTK/KDE).
- **Fase 3 — "instalável":** `install.sh` detector · pacote **AUR** · docs de
  release (com separação clara *core stock* vs *receita AULA opcional*).
- **Fase 4 — "além do Arch":** outras distros (ajuste de nomes de pacote no
  install) · idealmente com a MR do AULA já mesclada upstream.

Ligações com `07-portability-checklist.md`: Fase 1 = ideias #1 e #4; Fase 2 =
ideia #3; Fase 3 = ideias #4 e #6; Fase 4 = generalização final.

---

## 9. Riscos e dependências honestas

- **Depende do OpenRGB *detectar* o hardware do usuário.** Onde detecta, humilha a
  experiência do Windows; onde não (device muito novo, controlador proprietário
  exótico), o usuário fica na mão — igual no Windows, só sem o software do
  fabricante como muleta. O `calibrate` + provider plugável são justamente o que
  faz funcionar **na máquina dos outros**, não só na sua. É a diferença entre
  "olha que legal no meu PC" e "instalei e funcionou".
- **Barreira da build custom** — enquanto exigir compilar OpenRGB, a adoção morre
  na porta. Por isso a decisão #6.1 é pré-requisito de release.
- **Manutenção** — projeto OSS gera issues, PRs, pedidos de suporte a hardware.
  Definir escopo ("suporto o que o OpenRGB suporta") protege seu tempo.
- **RGB de hardware novo atrasa no OpenRGB** — ex.: a GPU nova (RX 9070 XT) pode
  não ter RGB suportado de imediato. Não é bug do projeto; é do upstream.

---

## 10. Próximos passos concretos (retomar por aqui)

Escolher a peça que mais destrava:
- [ ] Rascunhar o **schema TOML** do mapa de dispositivos + interface de provider.
- [ ] Escrever as **units `systemd --user` + o watcher `inotify`** que substituem
      `autostart.lua` e os hooks do Omarchy.
- [ ] Montar a **estrutura do repo + README** para release, com a separação
      "core stock" vs "receita AULA opcional" e o gancho da seção 1.
- [ ] Acompanhar/empurrar a **MR !3027** no GitLab do OpenRGB.

---

## Referências

- Docs técnicos deste projeto: `01`–`07` (I2C/RAM, build custom, udev, SDK
  server/cliente, persistência de boot, sync de cor, portabilidade).
- OpenRGB — MR !3027 (suporte ao teclado AULA wireless, draft em 2026-09-16).
- OpenRGB — issue upstream #4232 ("AULA F75 Keyboard").
