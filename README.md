# Canteiro Venda na Obra — Stories agendados

Cada cartão de story no app **[Canteiro / VNO](https://claude.ai/code/artifact/c6da235d-79ca-4c9b-bca9-778cf6aba136)**
tem um botão **"Enviar a foto e agendar 08:00"**. Você toca, escolhe a mídia
e pronto: ela vai ao ar naquele horário, sozinha. O dia e a hora já vêm do
cartão — você não digita nem renomeia nada.

O app do Instagram não agenda Story. O **Meta Business Suite** agenda (grátis,
um story por vez, criado um a um). Aqui o agendamento já está no cartão que
você ia executar de qualquer jeito.

## O caminho, do toque ao ar

1. No Canteiro, abra a aba **Stories** do dia.
2. No cartão, toque em **Enviar a foto e agendar**.
3. Escolha a foto ou o vídeo (a data e a hora já vêm preenchidas).
4. **Agendar**. Some da tela e vai ao ar na hora.

Na primeira vez a página pede uma **chave de acesso do GitHub** — o passo a
passo está na própria tela, em "Como criar a chave". É uma vez por aparelho.

## Enviar sem passar pelo cartão

A mesma página funciona solta, em
<https://diegohenriquemoraes-eng.github.io/canteiro-stories/>: escolha vários
arquivos de uma vez e marque o horário de cada um no seletor. Serve para o que
não está na pauta do dia.

## Também dá para largar o arquivo direto na fila

Anexando na [Release `fila`](../../releases/edit/fila) com o horário no começo
do nome. É o caminho de emergência — vale quando o arquivo é grande demais
para o navegador do celular dar conta.

| Nome | Vai ao ar |
|---|---|
| `0930-fundacao.jpg` | hoje, 09:30 |
| `930 concreto.mp4` | hoje, 09:30 |
| `09h30-laje.jpg` | hoje, 09:30 |
| `2026-09-06-0930-laje.jpg` | dia 06/09, 09:30 |

**O nome tem de COMEÇAR com o horário.** `IMG_20260904_093012.jpg` é ignorado
de propósito — publicar "agora" uma foto que veio direto da galeria seria pior
que não publicar. (Pela página isso não acontece: ela monta o nome sozinha.)

Sem data no nome, o horário vale para a **próxima ocorrência**: passou há menos
de 90 minutos é hoje (cobre o atraso do cron), passou há mais é amanhã.

## O que o pipeline conserta sozinho

Foto e vídeo saem do celular em qualquer formato, e a API de Stories é
exigente. Antes de subir, cada arquivo é normalizado:

- **Enquadramento 1080×1920** com a imagem inteira no centro sobre um fundo
  desfocado dela mesma — nada é cortado e não ficam as barras pretas.
- **Foto deitada, 4:3, PNG, HEIC do iPhone** → JPEG dentro do teto de 8 MB.
- **Vídeo de mais de 60 s** → dividido em partes de até 60 s, publicadas em
  sequência (é o que o próprio Instagram faz).
- **Clipe de menos de 3 s** → estendido até o mínimo que a API aceita.
- **Vídeo mudo** → ganha faixa de áudio silenciosa (vídeo sem áudio às vezes
  trava o processamento do Instagram).

## O que a API oficial NÃO faz

Isto vale para qualquer ferramenta de agendamento, inclusive o Meta Business
Suite: um Story publicado por API é **mídia pura**. Não tem sticker de link,
enquete, quiz, música, menção, localização nem hashtag clicável. Story que
precise de sticker tem de ser postado à mão, no app.

## Ligar a publicação (uma vez só, ~20 minutos)

Sem os secrets abaixo, o pipeline roda, lê a fila e diz o que faria — mas não
publica. É seguro deixar assim enquanto o token não existe.

1. **Conta profissional**: `@vendanaobra` no app do Instagram → Configurações
   → Tipo de conta → **Empresa** ou **Criador**. É pré-requisito da API.
2. **App na Meta**: <https://developers.facebook.com/apps> → Criar app → tipo
   **Business** → produto **Instagram** → **API com login do Instagram**
   (*Instagram API with Instagram Login*; não precisa de Página do Facebook).
   Dá para reaproveitar o app que já existe do Palavra Viva Reels — basta
   adicionar `@vendanaobra` como conta de teste.
3. Em *Instagram → Configuração da API com login do Instagram*: adicione a
   conta como usuária de teste e **gere um token** com os escopos
   `instagram_business_basic` e `instagram_business_content_publish`. Troque
   por um **token de longa duração** (60 dias), botão na mesma tela.
4. **Pegue o id da conta**:
   `GET https://graph.instagram.com/me?fields=id,username&access_token=SEU_TOKEN`
   → use o `id` que vier aí (não o número que o painel mostra).
5. **Cadastre os secrets** em Settings → Secrets and variables → Actions:
   - `IG_USER_ID` = o id do passo 4
   - `IG_ACCESS_TOKEN` = o token de longa duração
   - *(opcional)* `REPO_PAT` = um PAT com permissão de escrever Secrets, para
     o token se renovar sozinho todo mês.

⚠ **O app OAuth precisa estar em produção**, senão o token morre em 7 dias —
armadilha já paga nos canais do YouTube.

### O token vale 60 dias

O workflow **Renovar token** roda dia 1º de cada mês. Com `REPO_PAT`, renova
sozinho. Sem PAT, ele **falha de propósito** para avisar: o repositório é
público, o log do Actions também é, e imprimir um token recém-gerado ali o
publicaria (o mascaramento automático do GitHub só cobre o valor que já está
cadastrado como secret). Nesse caso renove pelo PC:

```bash
IG_ACCESS_TOKEN=<token atual> python refresh_token.py
```

## Testar sem esperar

Em **Actions → Publicar Story → Run workflow**:

- `dry_run` → lista a fila e diz o que publicaria, sem tocar em nada.
- `render_apenas` → baixa e normaliza (não precisa de token).
- `forcar` → publica agora o primeiro da fila, ignorando o horário.

No PC, só para ver como um arquivo vai ficar depois de normalizado:

```bash
python publicar_story.py --local "C:\caminho\foto.jpg"
```

Sai em `saida/` (ignorado pelo Git). Os testes rodam sem rede:

```bash
python -m unittest discover -s testes
```

## Por dentro

| Peça | O quê |
|---|---|
| `docs/index.html` | A página de envio (GitHub Pages). Aceita `?d=&h=&t=` para vir pronta de um cartão do Canteiro |
| Branch `entrada` | A fila que a página grava. Sempre um commit ÓRFÃO, reescrito a cada envio e a cada publicação — nunca acumula histórico |
| Release `fila` | A outra porta de entrada: arquivo anexado à mão, com o horário no nome |
| Release `pronto` | Hospedagem temporária: a Graph API precisa de uma URL pública para vir buscar a mídia. O asset é apagado assim que publica |
| `fila.py` | Lê o horário do nome do arquivo e conversa com as Releases |
| `midia.py` | Normaliza para 1080×1920, divide vídeo longo, conserta clipe curto |
| `publicar_story.py` | Decide o que venceu, publica (`/media` com `media_type=STORIES` → `/media_publish`) e limpa |
| `state.json` | Memória entre execuções — o runner é descartado; sem isto o disparo seguinte republicaria o mesmo Story |
| `config.json` | Fuso, tolerância de atraso, teto diário, regras de vídeo |

**Por que Release e não uma pasta no repositório:** vídeo commitado incha o Git
para sempre, e a Graph API não aceita upload direto — ela exige uma URL
pública para buscar o arquivo. O asset de Release é exatamente isso, fica fora
do histórico e é apagado depois de publicado.

**Por que repositório público:** minutos de Actions ilimitados (o cron roda de
10 em 10 minutos) e a URL da mídia precisa ser pública para o Instagram baixar.
As fotos ficam acessíveis por URL enquanto estão na fila — algumas horas — e
são apagadas ao ir para o ar. Não coloque aqui nada que não vá virar Story
público de qualquer forma.

**Teto diário:** 12 Stories por dia (`cap_diario`), bem abaixo do limite de 100
publicações/24 h da API. A cota é conferida antes de cada publicação.
