"""Carrossel de terça e sexta: o roteiro do Reel que passou de 2.000 views.

Decisão do Diego em 14/10/2026: o carrossel diário saiu (alcance mediano 142 contra
474 do Reel, nunca passou de 423 em 3 meses). Ficam 2 por semana, às 12h30 de terça
e de sexta, e só com o roteiro de um Reel que JÁ provou: mais de 2.000 views nos
últimos 8 dias. Sem Reel nessa marca, não sai carrossel no dia.

Como funciona (roda no workflow do carrossel, antes do `carrossel.py`):

    Graph API -> Reels dos últimos 8 dias com views > 2.000, ainda não usados
      -> o de mais views
      -> a legenda dele vira os slides (capa = a fala entre aspas, um slide por
         parágrafo, a lista numerada num slide só, último slide = pergunta + palavra)
      -> grava em docs/carrosseis_virais.json com dia = hoje, hora = 12:30

O `carrossel.py` lê esse arquivo junto com o docs/carrosseis.json do app e publica
igual a qualquer outro. A legenda do carrossel abre com uma linha a mais, para não
ser confundida com a do Reel na conferência "já está no perfil".

Uso:
  python carrossel_viral.py                  # só age em terça e sexta (Brasília)
  python carrossel_viral.py --data 2026-10-17 --forcar --dry-run
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
DIAS_DA_SEMANA = {1, 4}          # terça e sexta
HORA = "12:30"
MINIMO_VIEWS = 2000
JANELA_DIAS = 8
MAX_SLIDES = 10
ABERTURA = "O roteiro do Reel que mais rodou essa semana, pra salvar e usar amanhã"


def log(msg: str) -> None:
    print(msg, flush=True)


def reels_recentes(token: str, ig_id: str, agora: datetime) -> list[dict]:
    desde = agora - timedelta(days=JANELA_DIAS)
    url = f"{GRAPH}/{ig_id}/media"
    params = {"fields": "id,caption,media_product_type,timestamp,permalink",
              "limit": 50, "access_token": token}
    out = []
    j = requests.get(url, params=params, timeout=30).json()
    for m in j.get("data", []):
        quando = datetime.strptime(m["timestamp"], "%Y-%m-%dT%H:%M:%S%z")
        if quando < desde:
            break
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
    ap.add_argument("--forcar", action="store_true", help="ignora o dia da semana")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    agora = datetime.now(FUSO)
    if args.data:
        agora = datetime.fromisoformat(args.data).replace(hour=11, tzinfo=FUSO)
    dia = agora.date().isoformat()
    if agora.weekday() not in DIAS_DA_SEMANA and not args.forcar:
        log(f"{dia}: carrossel viral só sai terça e sexta")
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

    candidatos = [r for r in reels_recentes(token, ig_id, agora)
                  if r["views"] > MINIMO_VIEWS and r["id"] not in usados]
    if not candidatos:
        log(f"{dia}: nenhum Reel acima de {MINIMO_VIEWS} views nos últimos {JANELA_DIAS} dias "
            "que ainda não virou carrossel. Sem carrossel hoje")
        return
    reel = max(candidatos, key=lambda r: r["views"])
    dow = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"][agora.weekday()]
    c = montar(reel, dia, dow)
    log(f"{dia}: carrossel do Reel {reel['id']} ({reel['views']} views), {len(c['slides'])} slides")
    for i, s in enumerate(c["slides"], 1):
        log(f"  {i:02d}. {s[:90]!r}")
    if args.dry_run:
        return
    feitos.append(c)
    SAIDA.write_text(json.dumps(feitos, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"gravado em {SAIDA}")


if __name__ == "__main__":
    main()
