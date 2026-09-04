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

## Arquivo grande sobe em pedaços (04/09/2026)

Um vídeo de 75 MB levou **422** da API de blobs — *"Sorry, your input was too
large to process"*. O limite é do servidor do GitHub e aparece bem antes dos
100 MB da documentação, então otimizar o envio não resolve. (Antes disso, o
mesmo arquivo dava "Load failed": a página montava o base64 na mão e
materializava o vídeo três vezes na memória do Safari. Agora usa
`FileReader.readAsDataURL`; foi essa correção que fez o upload chegar até o
servidor e o erro mudar de cara.)

Acima de **6 MB** a página fatia:

    2026-09-04-1930-solucao.mp4.p1de9  …  .p9de9   (pedaços)
    2026-09-04-1930-solucao.mp4.partes.json        (bytes, sha256, nº de partes)

A extensão fica **antes** do sufixo de propósito: o item remontado precisa
continuar sendo `.mp4` para `RE_NOME` e o filtro de extensões funcionarem sem
mudar nada. Os pedaços, esses, não têm extensão de mídia — se o manifesto
faltar ou o envio parar no meio, nada disso é confundido com Story pronto.

`fila.juntar_partes` junta antes de qualquer decisão e **só aceita conjunto
completo**; faltando pedaço, o nome vai para o log e espera a próxima rodada.
`fila.baixar_montado` confere **tamanho e sha256** contra o manifesto e levanta
se não bater — Story truncado no ar é pior que Story não publicado. Coberto por
`testes/test_partes.py`.

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

## NO AR desde 04/09/2026

App Meta **vendanaobra** (id 1910368269635506, já existia) com o caso de uso
"API do Instagram" e as permissões `instagram_business_basic` e
`instagram_business_content_publish` prontas. Conta `@vendanaobra` aceita como
**Testador do Instagram**, token de longa duração gerado e gravado no secret
`IG_ACCESS_TOKEN`. Diagnóstico do dia:

    conta do token: @vendanaobra (id 28458102257148998)
    cota do Instagram: 2/100 publicações nas últimas 24 h

⚠ **O id que a API usa NÃO é o do painel.** O Studio da Meta mostra
`17841470188725651`; o que `graph.instagram.com/me` devolve — e o único que
funciona — é `28458102257148998`. É por isso que `IG_USER_ID` deixou de ser
cadastrado à mão: `descobrir_ig_id()` pergunta ao próprio token.

Para diagnosticar depois: **Actions → Publicar Story → Run workflow →
dry_run**. Ele confere a credencial ANTES de olhar a fila (com a fila vazia
sairia antes de testar, que é justamente quando se quer testar) e não publica
nada.

## O token não para sozinho — como isso foi fechado (04/09/2026)

O Diego pediu "de forma que nunca pare". O que derruba um pipeline assim não é
o prazo do token (60 dias, renovável para outros 60 a cada vez) — é a renovação
falhar **em silêncio**. Três camadas, todas no ar e testadas no mesmo dia:

1. **Renovação SEMANAL** (segunda, 11:20 UTC), não mensal: dentro de uma
   validade cabem ~8 tentativas, então uma falha isolada não custa nada.
2. **O prazo mora no repositório** (`token.json`, commitado a cada renovação):
   qualquer execução sabe quanto falta sem precisar do segredo, e o publicador
   avisa no log quando entra nos últimos 21 dias (`ALERTA_DIAS`).
3. **Falha vira issue, e issue vira e-mail** — na renovação e também na
   publicação (`if: failure()` nos dois workflows, com guarda para não empilhar
   issue nova a cada rodada). Foi assim que o ES perdeu metade da esteira por
   sete dias em agosto: o vigia media silêncio, e meia-falha não é silêncio.

⚠ `refresh_token.py` regrava o MESMO token quando a Meta recusa renovar por
idade (<24 h). Parece inútil e não é: é o que prova, no dia do setup, que o
`REPO_PAT` tem permissão de gravar secret — em vez de descobrir isso dois meses
depois, no dia em que a renovação era necessária.

Teste real de 04/09: `Pelo último registro, faltavam 59 dias. Token renovado:
válido por mais ~59 dias. Secret IG_ACCESS_TOKEN gravado com o REPO_PAT.`

**O que ainda poderia parar, e é aceito:** repositório 60 dias sem atividade faz
o GitHub desativar os crons (improvável — cada publicação e cada renovação
commita). E o `REPO_PAT` foi criado sem expiração de propósito: com prazo, ele
seria a peça que vence e derruba o resto.

**O caminho que nunca expira mesmo**, se um dia valer a pena: token de *System
User* de Portfólio Comercial. Não tem prazo nenhum, mas exige a API com login do
**Facebook** (`graph.facebook.com`), a conta vinculada a uma Página e reescrever
a publicação. Foi apresentado ao Diego em 04/09 e ficou para depois.

## Pendências do Diego

Nenhuma. Chave do GitHub, token do Instagram e `REPO_PAT` foram feitos em
04/09/2026.

⚠ A regra de "app OAuth precisa estar em produção senão o token morre em 7
dias" é do **Google/YouTube**, não da Meta — foi copiada por engano para cá na
primeira versão. O app da Meta do Palavra Viva Reels roda em
**desenvolvimento** e publica desde 24/07 sem isso; o que vale aqui é o token
de longa duração de 60 dias, renovável.

## Contexto que não está no código

Em **21/08/2026** o Diego tirou os carrosséis do @vendanaobra da publicação por
API, com receio de a automação prejudicar a entrega do perfil. Ele pediu esta
automação de Stories mesmo assim, em 04/09 — e Story é caso diferente
(efêmero, fora do ranking do feed). Se a entrega do perfil cair, esta é a
primeira variável a olhar.
