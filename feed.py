"""Publica no feed do @vendanaobra as fotos avulsas agendadas em feed_agendado.json.

Pedido do Diego em 27/09/2026: foto dele (recortada 4:5) com legenda no padrão do
Canteiro, uma na hora e a outra exatamente uma semana depois, no mesmo horário.
Não é fonte nova de story: sai só no feed, e só o que estiver no JSON.

Cada item do JSON:
    {"id": "...", "quando": "2026-10-04T20:40:00-03:00", "arquivo": "x.jpg",
     "legenda": "...", "publicado": null}

A imagem mora como asset da Release `feed` (URL pública que o Instagram vem
buscar; mídia nunca entra no histórico do Git). Depois de publicar, o asset é
apagado e o item ganha `publicado` com o media_id.

Uso:
  python feed.py              # publica o que estiver devido (dorme até a hora se faltar pouco)
  python feed.py --agora ID   # publica esse item já
  python feed.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
sys.stdout.reconfigure(encoding="utf-8")

import requests                                    # noqa: E402

import carrossel as cmod                           # noqa: E402
import fila as filamod                             # noqa: E402

DADOS = AQUI / "feed_agendado.json"
RELEASE = "feed"
ESPERA_MIN = 150
ATRASO_MAX_MIN = 360
log = cmod.log


def publicar_foto(ig_id: str, token: str, url: str, legenda: str) -> str:
    graph = cmod.GRAPH_META
    j = requests.post(f"{graph}/{ig_id}/media",
                      data={"image_url": url, "caption": legenda,
                            "access_token": token}, timeout=120).json()
    if "id" not in j:
        raise SystemExit(f"falha ao criar o post: {j}")
    cmod.GRAPH = graph
    cmod.esperar_pronto(j["id"], token)
    p = requests.post(f"{graph}/{ig_id}/media_publish",
                      data={"creation_id": j["id"], "access_token": token},
                      timeout=120).json()
    if "id" not in p:
        raise SystemExit(f"falha no media_publish: {p}")
    return p["id"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--agora", metavar="ID")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    itens = json.loads(DADOS.read_text(encoding="utf-8"))
    agora = datetime.now(cmod.FUSO)
    pend = [i for i in itens if not i.get("publicado")]
    if args.agora:
        pend = [i for i in pend if i["id"] == args.agora]
        if not pend:
            log(f"item {args.agora} não existe ou já foi publicado")
            return
    else:
        devidos = []
        for i in pend:
            falta = (datetime.fromisoformat(i["quando"]) - agora).total_seconds() / 60
            if falta > ESPERA_MIN:
                continue
            if -falta > ATRASO_MAX_MIN:
                log(f"PERDIDO: {i['id']} era {i['quando']}; não publico fora da janela")
                continue
            devidos.append((falta, i))
        if not devidos:
            log("nada devido no feed agora")
            return
        falta, item = sorted(devidos, key=lambda x: x[0])[0]
        pend = [item]
        if falta > 0 and not args.dry_run:
            log(f"esperando {falta:.0f} min até {item['quando']}: {item['id']}")
            time.sleep(falta * 60)

    item = pend[0]
    legenda = cmod.sem_pontuacao_pesada(item["legenda"])
    if args.dry_run:
        log(f"[dry-run] publicaria {item['id']} ({item['arquivo']}, legenda {len(legenda)} caracteres)")
        return

    token = os.environ.get("META_TOKEN", "").strip()
    if not token:
        raise SystemExit("sem META_TOKEN, não há como publicar")
    ig_id = os.environ.get("IG_BUSINESS_ID", "").strip() or cmod.IG_BUSINESS_ID

    cmod.GRAPH = cmod.GRAPH_META
    ja = cmod.ja_no_perfil(ig_id, token, legenda)
    if ja:
        log(f"já está no perfil ({ja}); só registrando")
        media_id = ja
    else:
        repo = filamod.Repo()
        asset = next((a for a in repo.assets(RELEASE) if a["name"] == item["arquivo"]), None)
        if not asset:
            raise SystemExit(f"a imagem {item['arquivo']} não está na Release `{RELEASE}`")
        media_id = publicar_foto(ig_id, token, asset["browser_download_url"], legenda)
        try:
            repo.apagar(asset["id"])
        except Exception:
            pass
        log(f"NO AR: {media_id} ({item['id']})")

    item["publicado"] = {"media_id": media_id,
                         "quando": datetime.now(cmod.FUSO).isoformat(timespec="seconds")}
    DADOS.write_text(json.dumps(itens, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
