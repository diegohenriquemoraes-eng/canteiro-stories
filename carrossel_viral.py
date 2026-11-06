"""Carrossel de todo dia, 12h30: o roteiro de um Reel do próprio dia.

Histórico: 14/10/2026 o carrossel diário saiu e ficou terça e sexta com o Reel acima de
2.000 views da semana. **06/11/2026 (Diego): volta a ser 1 por dia, com o tema de um dos
vídeos do dia.** No mesmo dia o automático publicou um carrossel que dizia "essa pergunta
desmonta a objeção" sem a pergunta (ela só existia na fala do vídeo, a legenda não tinha).
Foi apagado e refeito. Daí a trava `problemas()`: carrossel que cita pergunta, frase ou
roteiro sem mostrar, que leva hashtag ou "Siga" no slide, ou que fica curto demais, NÃO sai.

Como funciona (roda no workflow do carrossel, antes do `carrossel.py`):

    Graph API -> Reels de hoje (Brasília), o mais cedo primeiro (o das 09h)
      -> a legenda dele vira os slides (capa = a fala entre aspas, um slide por
         parágrafo, a lista numerada num slide só, último slide = pergunta + palavra)
      -> passa na trava; se reprovar, tenta o próximo Reel de hoje e depois os das
         últimas 24 h; nenhum passou = sem carrossel no dia (melhor nada que errado)
      -> grava em docs/carrosseis_virais.json com dia = hoje, hora = 12:30

O carrossel escrito à mão no app Canteiro (docs/carrosseis.json) tem preferência no dia dele.
A legenda do carrossel abre com uma linha a mais, para não ser confundida com a do Reel
na conferência "já está no perfil".

Uso:
  python carrossel_viral.py                  # monta o de hoje
  python carrossel_viral.py --data 2026-11-06 --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

AQUI = Path(__file__).resolve().parent
sys.stdout.reconfigure(encoding="utf-8")

FUSO = ZoneInfo("America/Sao_Paulo")
GRAPH = "https://graph.facebook.com/v21.0"
IG_BUSINESS_ID = "17841470188725651"
SAIDA = AQUI / "docs" / "carrosseis_virais.json"
HORA = "12:30"
JANELA_HORAS = 24
MINIMO_SLIDES = 4
MAX_SLIDES = 10
ABERTURA = "O roteiro do Reel de hoje, pra salvar e usar amanhã"


def log(msg: str) -> None:
    print(msg, flush=True)


def reels_recentes(token: str, ig_id: str, agora: datetime) -> list[dict]:
    desde = agora - timedelta(hours=JANELA_HORAS)
    url = f"{GRAPH}/{ig_id}/media"
    params = {"fields": "id,caption,media_product_type,timestamp,permalink",
              "limit": 50, "access_token": token}
    out = []
    j = requests.get(url, params=params, timeout=30).json()
    for m in j.get("data", []):
        quando = datetime.strptime(m["timestamp"], "%Y-%m-%dT%H:%M:%S%z")
        if quando > agora:
            continue
        if quando < desde:
            break
        m["quando"] = quando.astimezone(FUSO)
        if m.get("media_product_type") != "REELS" or not m.get("caption"):
            continue
        ins = requests.get(f"{GRAPH}/{m['id']}/insights",
                           params={"metric": "views", "access_token": token}, timeout=30).json()
        try:
            m["views"] = ins["data"][0]["values"][0]["value"]
        except (KeyError, IndexError):
            m["views"] = 0
        out.append(m)
    return out


def slides_da_legenda(legenda: str) -> tuple[list[str], str]:
    """A legenda do Reel já tem o roteiro na ordem: gancho, contexto, a frase, lista, fecho."""
    partes = [p.strip() for p in re.split(r"\n\s*\n", legenda) if p.strip()]
    palavra = ""
    pergunta = ""
    corpo = []
    depois_da_visao = False
    for p in partes:
        if p.startswith("#") or p.startswith("Siga ") or p.startswith("Desenvolvo empresas") or p.startswith("@"):
            continue
        if re.search(r"(?i)(siga o @|me segue)", p):
            continue
        p = re.sub(r"\s*#\S+", "", p).strip()
        if not p:
            continue
        m = re.match(r"Comenta (\S+)", p)
        if m:
            palavra = m.group(1)
            continue
        if p.startswith("Pegou a vis"):
            depois_da_visao = True
            continue
        if depois_da_visao:
            pergunta = pergunta or p
            continue
        corpo.append(p)
    if not pergunta:
        perguntas = [p for p in corpo[1:] if p.endswith("?")]
        if perguntas:
            pergunta = perguntas[-1]
            corpo.remove(pergunta)
    # a lista numerada vira um slide só
    juntos = []
    for p in corpo:
        if re.match(r"^\d+[.)]", p) and juntos and re.match(r"^\d+[.)]", juntos[-1].split("\n")[-1]):
            juntos[-1] += "\n" + p
        else:
            juntos.append(p)
    corpo = juntos
    # capa curta ("Chegou no evento?") leva a frase seguinte junto
    if len(corpo) > 2 and len(corpo[0].split()) < 6 and not re.match(r"^\d+[.)]", corpo[1]):
        corpo[0:2] = [corpo[0] + "\n\n" + corpo[1]]
    # cabe no teto: junta os parágrafos curtos do meio, dois a dois
    while len(corpo) + 1 > MAX_SLIDES:
        i = min(range(1, len(corpo) - 1), key=lambda k: len(corpo[k]) + len(corpo[k + 1]))
        corpo[i:i + 2] = [corpo[i] + "\n\n" + corpo[i + 1]]
    final = (pergunta + "\n\n" if pergunta else "") + (
        f"Comenta {palavra} que eu te mando o roteiro" if palavra else "Salva pra usar amanhã")
    return corpo + [final], palavra


CITA_PERGUNTA = re.compile(r"(?i)\b(essa|esta|uma|única|unica|a) pergunta\b")
CITA_RESPOSTA = re.compile(r"(?i)\b(essa|esta) (frase|resposta|técnica|tecnica|fala)\b|\besse roteiro\b")
MOSTRA_RESPOSTA = re.compile(r"(?i)\beu (responderia|perguntaria|falaria|diria|faria)\b|^\d+[.)]|[“\"][^”\"]{6,}[”\"]", re.M)
PERGUNTA_ENTRE_ASPAS = re.compile(r"[“\"][^”\"]{6,}\?[”\"]")


def problemas(slides: list[str]) -> list[str]:
    """O que impede o carrossel de sair. Vazio = pode publicar.

    O erro de 06/11/2026: "Essa pergunta desmonta a objeção" e a pergunta não estava em
    slide nenhum. Todo slide que cita pergunta, frase ou roteiro precisa que ele apareça
    (até aquele slide, ou no seguinte, quando o slide anuncia com dois-pontos)."""
    out = []
    if len(slides) < MINIMO_SLIDES:
        out.append(f"só {len(slides)} slides")
    # elemento concreto obrigatório (Rota 100K): a frase que eu falaria, os passos ou a fala entre aspas
    if not MOSTRA_RESPOSTA.search("\n".join(slides[1:-1])):
        out.append("nenhum slide mostra o que fazer (frase, passos ou fala entre aspas)")
    for i, s in enumerate(slides):
        if re.search(r"(^|\s)#\w", s):
            out.append(f"slide {i + 1} tem hashtag")
        if re.search(r"(?i)siga o @|me segue", s):
            out.append(f"slide {i + 1} tem CTA de seguir")
        if i < len(slides) - 1 and re.search(r"(?i)\b(na minha bio|link na bio|caderno|raio-x)\b", s):
            out.append(f"slide {i + 1} tem oferta no meio do carrossel")
        if i == 0:
            continue  # a capa é a fala do cliente, não cita nada
        anuncia = s.rstrip().endswith(":")
        # o que já foi mostrado: do 2º slide até este (ou até o seguinte, se este anuncia)
        visto = "\n".join(slides[1:i + 2] if anuncia else slides[1:i + 1])
        if CITA_PERGUNTA.search(s) and not PERGUNTA_ENTRE_ASPAS.search(visto):
            out.append(f"slide {i + 1} cita a pergunta e ela não aparece")
        if CITA_RESPOSTA.search(s) and not MOSTRA_RESPOSTA.search(visto):
            out.append(f"slide {i + 1} cita a frase/roteiro e ele não aparece")
    return out


def montar(reel: dict, dia: str, dow: str) -> dict:
    slides, palavra = slides_da_legenda(reel["caption"])
    legenda = reel["caption"]
    gancho = slides[0]
    legenda = legenda.replace(gancho, gancho + "\n\n" + ABERTURA, 1) if gancho in legenda \
        else ABERTURA + "\n\n" + legenda
    return {
        "dia": dia, "dow": dow, "hora": HORA, "n": 1,
        "titulo": re.sub(r"\s+", " ", gancho)[:80],
        "publico": "compartilhar",
        "slides": slides,
        "capa_numero": [],
        "legenda": legenda,
        "origem": {"reel": reel["id"], "views": reel["views"], "link": reel.get("permalink", "")},
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", help="AAAA-MM-DD (padrão: hoje em Brasília)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    agora = datetime.now(FUSO)
    if args.data:
        agora = datetime.fromisoformat(args.data).replace(hour=12, minute=20, tzinfo=FUSO)
    dia = agora.date().isoformat()

    # O carrossel escrito à mão no app Canteiro (formato Notas, docs/carrosseis.json) tem
    # preferência. Este automático só entra no dia em que o app não tiver carrossel
    do_app = Path(__file__).parent / "docs" / "carrosseis.json"
    if do_app.exists() and any(c.get("dia") == dia for c in json.loads(do_app.read_text(encoding="utf-8"))):
        log(f"{dia}: o app já tem carrossel hoje (Notas), o automático não entra")
        return

    feitos = json.loads(SAIDA.read_text(encoding="utf-8")) if SAIDA.exists() else []
    if any(c["dia"] == dia for c in feitos):
        log(f"{dia}: carrossel viral já montado")
        return
    usados = {c.get("origem", {}).get("reel") for c in feitos}

    token = os.environ.get("META_TOKEN", "").strip()
    if not token:
        raise SystemExit("sem META_TOKEN — não há como ler os Reels")
    ig_id = os.environ.get("IG_BUSINESS_ID", "").strip() or IG_BUSINESS_ID

    recentes = [r for r in reels_recentes(token, ig_id, agora) if r["id"] not in usados]
    # tema de um vídeo do dia: os de hoje primeiro, o mais cedo (09h) antes; depois as últimas 24 h
    recentes.sort(key=lambda r: (r["quando"].date() != agora.date(),
                                 r["quando"] if r["quando"].date() == agora.date() else -r["quando"].timestamp()))
    dow = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"][agora.weekday()]
    c = reel = None
    for r in recentes:
        tentativa = montar(r, dia, dow)
        erros = problemas(tentativa["slides"])
        if not erros:
            c, reel = tentativa, r
            break
        log(f"{dia}: Reel {r['id']} ({r['quando']:%d/%m %H:%M}) reprovado: {'; '.join(erros)}")
    if not c:
        raise SystemExit(f"{dia}: nenhum Reel das últimas {JANELA_HORAS} h deu carrossel completo. "
                         "Sem carrossel hoje (melhor nada que slide citando o que não mostra)")
    log(f"{dia}: carrossel do Reel {reel['id']} ({reel['quando']:%d/%m %H:%M}, {reel['views']} views), "
        f"{len(c['slides'])} slides")
    for i, s in enumerate(c["slides"], 1):
        log(f"  {i:02d}. {s[:90]!r}")
    if args.dry_run:
        return
    feitos.append(c)
    SAIDA.write_text(json.dumps(feitos, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"gravado em {SAIDA}")


if __name__ == "__main__":
    main()
