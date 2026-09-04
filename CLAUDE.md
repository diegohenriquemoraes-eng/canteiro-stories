# Canteiro Venda na Obra — Stories agendados no @vendanaobra

Pipeline de agendamento de **Stories** (o app do Instagram não agenda Story).
O Diego sobe as mídias de manhã pelo navegador do celular e cada uma vai ao ar
no horário marcado, sem ele tocar no aparelho durante o dia. Uso no `README.md`.

## As decisões, e por que elas

- **A entrada é um botão no cartão do Canteiro** (04/09/2026, 2ª rodada). A
  primeira versão pedia que o Diego renomeasse cada arquivo para `0930-x.jpg`;
  ele recusou — com razão, é trabalho manual num aparelho onde renomear é
  chato. Agora cada cartão de story do app leva um botão que abre a página de
  envio **já com o dia e a hora daquele cartão**: ele escolhe a mídia e pronto.
- **O nome do arquivo continua sendo o agendamento por baixo** — só que agora
  quem o monta é a página (`AAAA-MM-DD-HHMM-slug.ext`). O contrato entre as
  duas metades é o `RE_NOME` de `fila.py`, e tem teste
  (`test_nome_que_a_pagina_de_envio_monta`): se esse formato deixar de ser
  entendido, o Story não sai com hora errada — ele é ignorado em silêncio.
- **A mídia nunca entra no histórico do Git.** Vídeo commitado incha o
  repositório para sempre. A branch `entrada`, que a página grava, é sempre um
  commit **órfão** reescrito a cada envio e a cada publicação: guarda só o que
  está na fila. A Release `fila` é a outra porta (arquivo anexado à mão) e a
  `pronto` é a hospedagem temporária — a Graph API não aceita upload direto,
  ela exige uma URL pública para vir buscar a mídia. `fila` e `pronto` são
  separadas porque, sendo uma só, o arquivo já normalizado voltaria a ser lido
  como entrada nova na rodada seguinte.
- **Repositório público**: Actions ilimitado (cron de 10 em 10 min) e URL de
  mídia pública. Consequência aceita: o que está na fila é acessível por URL
  por algumas horas — e vai virar Story público mesmo.
- **Sem data no nome, o horário é a PRÓXIMA ocorrência.** Passou há menos de
  `atraso_max_min` (90 min) é hoje; passou há mais, é amanhã. Cobre os dois
  casos reais: o cron do GitHub atrasando e o `0800-x.jpg` subido às 14h.
- **Nome sem horário é IGNORADO**, não publicado na hora. Foto que veio direto
  da galeria (`IMG_20260904_093012.jpg`) publicada "agora" é pior que nenhuma.
- **1 Story por arquivo, 2 arquivos por execução, teto de 12/dia.** O limite da
  API é 100 publicações/24 h e a cota é conferida antes de cada publicação.

## O Artifact não consegue publicar sozinho — e por que a página existe

O Canteiro é um **Artifact**, e a plataforma bloqueia por CSP toda chamada de
rede da página (fetch, XHR, WebSocket para qualquer host). Não há capability de
armazenamento de arquivo que o GitHub Actions consiga ler depois: `db` só é
lido por Claude e pelos visitantes da página, e não existe capability `assets`
para este usuário. **Então o upload não pode acontecer dentro do Canteiro** —
não é escolha de desenho, é limite da plataforma.

O que dá para fazer, e é o que está no ar: o cartão leva um link externo com o
dia e a hora nos parâmetros (`?d=2026-09-05&h=0800&t=Tiro+de+alerta`), e a
página de envio abre pronta. Custa um salto de tela; poupa toda digitação.

⚠ **O upload direto para uma Release é impossível do navegador**:
`uploads.github.com` não responde ao preflight de CORS (conferido — devolve
400). A `api.github.com` responde, e é por isso que a página grava numa branch
por Git Data API, e não como asset de Release.

⚠ A página precisa de um **PAT fine-grained** do Diego, guardado no
localStorage do celular. Escopo mínimo: só o repo `canteiro-stories`, só
**Contents: Read and write**. Contents não permite mexer em
`.github/workflows` (isso exige a permissão Workflows, separada), então uma
chave vazada não consegue trocar o que o Actions roda — mas consegue editar
`publicar_story.py`, que roda com os secrets do Instagram no ambiente. É o
motivo de o escopo ser o mínimo e de a chave não ir para lugar nenhum além do
navegador dele.

## Armadilhas já pagas (04/09/2026, construção)

- **`-shortest` truncava o clipe esticado.** Vídeo de 2 s é estendido para 3 s
  (mínimo da API), mas o `tpad` estica só o vídeo: o áudio continuava com 2 s e
  o `-shortest` cortava a saída de volta para 2,02 s — devolvendo à API
  exatamente a duração que ela acabou de recusar. Agora é `-af apad` com o
  `-t` mandando na duração.
- **Mapear as streams na mão.** Com `filter_complex` e duas entradas (a
  segunda é o `anullsrc` para vídeo mudo), deixar o ffmpeg escolher a faixa de
  áudio dá silêncio em vídeo que tinha som. `-map [vout]` + `-map 0:a:0` ou
  `1:a:0`.
- **O GitHub serve TODO asset como `application/octet-stream`**, mande-se o
  que mandar no upload — conferido, não adianta tentar `image/jpeg`. Quem
  identifica a mídia para o Instagram é a **extensão no fim da URL**, então o
  nome do asset precisa terminar em `.jpg`/`.mp4`. É o mesmo caminho que o
  pipeline dos Reels do Palavra Viva usa em produção desde 24/07, inclusive
  para imagem (as capas), então está comprovado.
- **Log de Actions de repo público é público.** O token renovado pelo
  `refresh_token.py` **não** é mascarado (o mascaramento automático só cobre o
  valor já cadastrado como secret), então no runner ele nunca é impresso: sem
  `REPO_PAT` o workflow falha de propósito, pedindo renovação pelo PC. O `log()`
  do publicador também mascara os segredos por conta própria.
- **HEIC do iPhone** não é decodificado pelo ffmpeg do runner: passa antes pelo
  `pillow-heif`. Sem isso o Story morreria num erro de codec que só apareceria
  à noite, com o perfil vazio.

## O que NÃO existe, e não adianta procurar

**Story publicado por API é mídia pura**: sem sticker de link, enquete, quiz,
música, menção, localização ou hashtag clicável. Não é limitação deste código
— o Meta Business Suite também não faz. Story que precise de sticker tem de
ser postado à mão.

## Pendências do Diego

1. **Chave do GitHub na página de envio** (PAT fine-grained): o passo a passo
   está na própria tela, em "Como criar a chave". Uma vez por aparelho. Sem
   ela a página abre mas não consegue gravar a fila.
2. **Token do Instagram** (secrets `IG_USER_ID` e `IG_ACCESS_TOKEN`): passo a
   passo no `README.md`. Sem eles o pipeline lê a fila e diz o que faria, mas
   não publica.
3. **App OAuth em produção**, senão o token morre em 7 dias.
4. *(opcional)* `REPO_PAT` para o token do Instagram se renovar sozinho.

## Contexto que não está no código

Em **21/08/2026** o Diego tirou os carrosséis do @vendanaobra da publicação por
API, com receio de a automação prejudicar a entrega do perfil. Ele pediu esta
automação de Stories mesmo assim, em 04/09 — e Story é caso diferente
(efêmero, fora do ranking do feed). Se a entrega do perfil cair, esta é a
primeira variável a olhar.
