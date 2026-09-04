# Canteiro Venda na Obra — Stories agendados no @vendanaobra

Pipeline de agendamento de **Stories** (o app do Instagram não agenda Story).
O Diego sobe as mídias de manhã pelo navegador do celular e cada uma vai ao ar
no horário marcado, sem ele tocar no aparelho durante o dia. Uso no `README.md`.

## As decisões, e por que elas

- **O agendamento é o NOME DO ARQUIVO** (`0930-fundacao.jpg`). Foi o que
  permitiu a entrada pelo celular ser um upload só, sem app, sem formulário e
  sem editar JSON no telefone. Todo o resto do desenho serve a isso.
- **A fila é uma Release**, não uma pasta do repositório: vídeo commitado
  incharia o Git para sempre, e a Graph API não aceita upload direto — ela
  exige URL pública para vir buscar a mídia. Duas Releases (`fila` e `pronto`)
  porque, sendo uma só, o arquivo já normalizado voltaria a ser lido como
  entrada nova na rodada seguinte.
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

1. **Token do Instagram** (secrets `IG_USER_ID` e `IG_ACCESS_TOKEN`): passo a
   passo no `README.md`. Sem eles o pipeline lê a fila e diz o que faria, mas
   não publica.
2. **App OAuth em produção**, senão o token morre em 7 dias.
3. *(opcional)* `REPO_PAT` para o token de 60 dias se renovar sozinho.

## Contexto que não está no código

Em **21/08/2026** o Diego tirou os carrosséis do @vendanaobra da publicação por
API, com receio de a automação prejudicar a entrega do perfil. Ele pediu esta
automação de Stories mesmo assim, em 04/09 — e Story é caso diferente
(efêmero, fora do ranking do feed). Se a entrega do perfil cair, esta é a
primeira variável a olhar.
