# -*- coding: utf-8 -*-
"""Confere a fila ANTES da hora de publicar: o que vai sair, quando, e o que quebraria.

Existe porque o erro de fila é silencioso: um arquivo cujo nome não começa com o
horário é ignorado sem aviso, e o Diego só descobriria no dia em que o Story não
aparecesse. Aqui a checagem é feita a frio, a qualquer momento, sem publicar nada.

Uso: python conferir_fila.py            # lê a fila pela API do GitHub
     python conferir_fila.py --json     # a mesma coisa, para outro programa ler
"""
from __future__ import annotations

import argparse
import json
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import fila as filamod

BASE = Path(__file__).parent
API = ("https://api.github.com/repos/diegohenriquemoraes-eng/"
       "canteiro-stories/contents/?ref=entrada")
TETO_MB = 90


def _fila_publica():
    """A branch `entrada` é pública: dá para conferir sem token nenhum."""
    with urllib.request.urlopen(API, timeout=30) as r:
        dados = json.loads(r.read())
    return [d for d in dados if d.get("type") == "file"]


def conferir():
    cfg = json.loads((BASE / "config.json").read_text(encoding="utf-8"))
    estado = json.loads((BASE / "state.json").read_text(encoding="utf-8"))
    tz = ZoneInfo(cfg["fuso"])
    agora = datetime.now(tz)

    saida = []
    for it in sorted(_fila_publica(), key=lambda x: x["name"]):
        nome, tam = it["name"], it["size"]
        alvo = filamod.alvo_do_nome(nome, agora, cfg["atraso_max_min"])
        problemas = []
        if Path(nome).suffix.lower() not in cfg["extensoes"]:
            problemas.append(f"extensão {Path(nome).suffix} não é aceita")
        if alvo is None:
            problemas.append("o nome não diz o horário — este seria ignorado")
        elif f"{alvo.date().isoformat()}|{nome}" in estado["publicados"]:
            problemas.append("já consta como publicado; não sai de novo")
        if tam > TETO_MB * 1e6:
            problemas.append(f"{tam/1e6:.0f} MB, acima do teto de {TETO_MB} MB")
        saida.append({"arquivo": nome, "mb": round(tam / 1e6, 2),
                      "sai_em": alvo.isoformat(timespec="minutes") if alvo else None,
                      "problemas": problemas})
    return agora, cfg, estado, saida


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--json", action="store_true")
    o = a.parse_args()

    agora, cfg, estado, itens = conferir()
    if o.json:
        print(json.dumps(itens, ensure_ascii=False, indent=1))
        return

    print(f"Fila do Canteiro — {len(itens)} arquivo(s), conferida {agora:%d/%m %H:%M}\n")
    for i in itens:
        quando = datetime.fromisoformat(i["sai_em"]).strftime("%d/%m %H:%M") if i["sai_em"] else "—"
        print(f"  {i['arquivo']}")
        print(f"    sai {quando} · {i['mb']} MB · "
              + ("ok" if not i["problemas"] else "PROBLEMA: " + "; ".join(i["problemas"])))
    print(f"\nteto do dia: {cfg['cap_diario']} · por execução: {cfg['max_por_execucao']}"
          f" · publicados em {estado['dia']['data']}: {estado['dia']['n']}")
    ruins = sum(1 for i in itens if i["problemas"])
    print("RESULTADO:", "tudo certo" if not ruins else f"{ruins} arquivo(s) com problema")


if __name__ == "__main__":
    main()
