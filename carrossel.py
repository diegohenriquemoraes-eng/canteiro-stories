"""Publica sozinho o carrossel do dia do @vendanaobra, às 12h30, pela API.

Decisão do Diego em 26/09/2026: o carrossel deixa de ser postado à mão e sai
**sem música** — era a música (que a Graph API não põe) a única razão de ele
ser manual. A medição de 26/09 não mostrou ganho de alcance com música
(Canteiro com música 145-169 de mediana, mini-aula por API sem música 125,
tudo em torno de 1,5 % dos seguidores), e o Diego preferiu assumir o risco a
ter uma tarefa manual todo dia.

O caminho:

    docs/carrosseis.json (exportado do app Canteiro)
      -> desenha os 8 slides (mesmo desenho de docs/carrossel.html)
      -> Release `pronto` (URL pública que o Instagram vem buscar)
      -> 8 containers is_carousel_item -> container CAROUSEL com a legenda
      -> media_publish -> apaga as imagens da Release -> grava state_carrossel.json

Proteções contra post duplicado: o estado em `state_carrossel.json` e, antes
de publicar, uma conferência no PERFIL (legenda igual nas últimas 30 h) — se o
estado não chegou a ser commitado numa rodada anterior, o perfil segura.

Uso:
  python carrossel.py                 # publica o carrossel devido agora (ou espera até a hora)
  python carrossel.py --agora         # publica o de HOJE já, mesmo antes/depois da hora
  python carrossel.py --data 2026-09-27 --render-apenas   # só desenha, em saida/carrossel/
  python carrossel.py --dry-run       # diz o que faria
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from PIL import Image, ImageDraw, ImageFont

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
sys.stdout.reconfigure(encoding="utf-8")

import fila as filamod        # noqa: E402

FUSO = ZoneInfo("America/Sao_Paulo")
DADOS = AQUI / "docs" / "carrosseis.json"
STATE = AQUI / "state_carrossel.json"
SAIDA = AQUI / "saida" / "carrossel"
FONTE = AQUI / "fontes" / "Archivo.ttf"
GRAPH = "https://graph.instagram.com"
# 26/09/2026: o IG_ACCESS_TOKEN deste repo (login do Instagram) foi invalidado por
# troca de senha. O carrossel usa o TOKEN DE SISTEMA da Meta (META_TOKEN): não
# expira, não cai com troca de senha e tem instagram_content_publish. Ele fala
# com graph.facebook.com e com o id de conta business (17841...).
GRAPH_META = "https://graph.facebook.com/v21.0"
IG_BUSINESS_ID = "17841470188725651"
RELEASE = "pronto"

# Janela: acordou até ESPERA_MIN antes da hora -> dorme e publica no minuto
# certo; acordou depois -> publica se não passou de ATRASO_MAX_MIN (cron do
# GitHub atrasado). Passou disso, o dia é dado como perdido e o log diz.
ESPERA_MIN = 150
ATRASO_MAX_MIN = 360

# ---- desenho: cópia fiel de docs/carrossel.html (canvas) --------------------
L, A = 1080, 1350
NAVY, CHAMP, BRANCO = (7, 16, 37), (216, 184, 136), (255, 255, 255)
MARGEM = 90
LARGURA = L - MARGEM * 2


def log(msg: str) -> None:
    texto = str(msg)
    for chave in ("META_TOKEN", "IG_ACCESS_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
        segredo = os.environ.get(chave, "").strip()
        if len(segredo) > 8:
            texto = texto.replace(segredo, "***")
    print(f"[{datetime.now(FUSO).strftime('%H:%M:%S')}] {texto}", flush=True)


def fonte(tam: int, peso: int) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONTE), tam)
    try:
        f.set_variation_by_axes([peso, 100])      # Weight, Width (normal)
    except Exception:
        pass
    return f


def quebrar(draw, texto: str, f, largura: int) -> list[str]:
    linhas = []
    for par in texto.split("\n"):
        linha = ""
        for p in par.split(" "):
            t = f"{linha} {p}" if linha else p
            if draw.textlength(t, font=f) > largura and linha:
                linhas.append(linha)
                linha = p
            else:
                linha = t
        linhas.append(linha)
    return linhas


def desenhar(texto: str, i: int, total: int) -> Image.Image:
    capa, cta = i == 0, i == total - 1
    im = Image.new("RGB", (L, A), NAVY if cta else BRANCO)
    d = ImageDraw.Draw(im)
    d.rectangle([90, 96, 90 + (320 if capa else 120), 106], fill=CHAMP)

    tam, peso = (100, 800) if capa else (78, 500)
    while True:
        f = fonte(tam, peso)
        linhas = quebrar(d, texto, f, LARGURA)
        if len(linhas) * tam * 1.22 <= A - 460 or tam <= 30:
            break
        tam -= 3
    bloco = len(linhas) * tam * 1.22
    y = max(190, (A - bloco) / 2 - 40)
    cor = BRANCO if cta else NAVY
    for linha in linhas:
        d.text((MARGEM, y), linha, font=f, fill=cor, anchor="la")
        y += tam * 1.22

    rod = fonte(34, 500)
    d.text((MARGEM, A - 150), "@vendanaobra", font=rod, anchor="la",
           fill=(195, 199, 207) if cta else (154, 163, 173))
    if not cta:
        n = f"{i + 1}/{total}"
        d.text((L - MARGEM - d.textlength(n, font=rod), A - 150), n,
               font=rod, fill=CHAMP, anchor="la")
    return im


def renderizar(c: dict, pasta: Path) -> list[Path]:
    pasta.mkdir(parents=True, exist_ok=True)
    arquivos = []
    for i, texto in enumerate(c["slides"]):
        p = pasta / f"{c['dia']}-carrossel{c['n']}-{i + 1:02d}.jpg"
        desenhar(texto, i, len(c["slides"])).save(p, "JPEG", quality=92)
        arquivos.append(p)
    return arquivos


# ---- Instagram ---------------------------------------------------------------

def ig_id_do_token(token: str) -> str:
    j = requests.get(f"{GRAPH}/me", params={"fields": "id,username",
                                            "access_token": token}, timeout=30).json()
    if "id" not in j:
        raise SystemExit(f"o token não respondeu quem é a conta: {j}")
    log(f"conta do token: @{j.get('username', '?')}")
    return j["id"]


def esperar_pronto(cid: str, token: str) -> None:
    for tentativa in range(30):
        s = requests.get(f"{GRAPH}/{cid}", params={"fields": "status_code",
                                                   "access_token": token},
                         timeout=30).json()
        code = s.get("status_code")
        if code == "FINISHED":
            return
        if code == "ERROR":
            raise SystemExit(f"o Instagram recusou o container {cid}: {s}")
        if code is None and tentativa >= 2:
            return
        time.sleep(5)
    raise SystemExit(f"tempo esgotado esperando o container {cid}")


def ja_no_perfil(ig_id: str, token: str, legenda: str) -> str | None:
    """Legenda igual nas últimas 30 h = já publicado (estado perdido)."""
    try:
        j = requests.get(f"{GRAPH}/{ig_id}/media",
                         params={"fields": "id,caption,timestamp,media_type",
                                 "limit": 15, "access_token": token},
                         timeout=30).json()
    except requests.RequestException as exc:
        log(f"não consegui ler o perfil ({exc}); seguindo sem essa conferência")
        return None
    limite = datetime.now(FUSO) - timedelta(hours=30)
    alvo = " ".join(legenda.split())[:60]
    for m in j.get("data", []):
        ts = datetime.strptime(m["timestamp"], "%Y-%m-%dT%H:%M:%S%z")
        if ts < limite:
            continue
        if " ".join((m.get("caption") or "").split())[:60] == alvo:
            return m["id"]
    return None


def publicar(ig_id: str, token: str, urls: list[str], legenda: str) -> str:
    filhos = []
    for u in urls:
        j = requests.post(f"{GRAPH}/{ig_id}/media",
                          data={"image_url": u, "is_carousel_item": "true",
                                "access_token": token}, timeout=120).json()
        if "id" not in j:
            raise SystemExit(f"falha ao criar o slide: {j}")
        filhos.append(j["id"])
    for cid in filhos:
        esperar_pronto(cid, token)
    j = requests.post(f"{GRAPH}/{ig_id}/media",
                      data={"media_type": "CAROUSEL", "children": ",".join(filhos),
                            "caption": legenda, "access_token": token},
                      timeout=120).json()
    if "id" not in j:
        raise SystemExit(f"falha ao criar o carrossel: {j}")
    esperar_pronto(j["id"], token)
    p = requests.post(f"{GRAPH}/{ig_id}/media_publish",
                      data={"creation_id": j["id"], "access_token": token},
                      timeout=120).json()
    if "id" not in p:
        raise SystemExit(f"falha no media_publish: {p}")
    return p["id"]


# ---- agenda -------------------------------------------------------------------

def carregar(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def gravar_estado(st: dict) -> None:
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def chave(c: dict) -> str:
    return f"{c['dia']}|{c['n']}"


def alvo_de(c: dict) -> datetime:
    h, m = map(int, c["hora"].split(":"))
    return datetime.fromisoformat(c["dia"]).replace(hour=h, minute=m, tzinfo=FUSO)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--agora", action="store_true", help="publica o de hoje já")
    ap.add_argument("--data", help="AAAA-MM-DD (padrão: hoje em Brasília)")
    ap.add_argument("--render-apenas", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    agora = datetime.now(FUSO)
    dia = args.data or agora.date().isoformat()
    todos = carregar(DADOS, [])
    do_dia = [c for c in todos if c["dia"] == dia]
    if not do_dia:
        log(f"nenhum carrossel no app para {dia}")
        return

    st = carregar(STATE, {"publicados": {}})
    st.setdefault("publicados", {})

    if args.render_apenas:
        for c in do_dia:
            for p in renderizar(c, SAIDA):
                log(f"desenhado: {p}")
        return

    pendentes = [c for c in do_dia if chave(c) not in st["publicados"]]
    if not pendentes:
        log(f"carrossel de {dia} já publicado")
        return
    c = sorted(pendentes, key=lambda x: x["hora"])[0]
    alvo = alvo_de(c)

    if not args.agora:
        falta = (alvo - agora).total_seconds() / 60
        if falta > ESPERA_MIN:
            log(f"cedo demais: {c['titulo']} é às {c['hora']} (faltam {falta:.0f} min)")
            return
        if -falta > ATRASO_MAX_MIN:
            log(f"PERDIDO: {c['titulo']} era às {c['hora']} e já passou "
                f"{-falta:.0f} min — não publico fora da janela")
            return
        if falta > 0 and not args.dry_run:
            log(f"esperando {falta:.0f} min até {c['hora']} para publicar: {c['titulo']}")
            time.sleep(falta * 60)

    if args.dry_run:
        log(f"[dry-run] publicaria {c['dia']} {c['hora']}: {c['titulo']} "
            f"({len(c['slides'])} slides, legenda {len(c['legenda'])} caracteres)")
        return

    global GRAPH
    token = os.environ.get("META_TOKEN", "").strip()
    if token:
        GRAPH = GRAPH_META
        ig_id = os.environ.get("IG_BUSINESS_ID", "").strip() or IG_BUSINESS_ID
    else:
        token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
        if not token:
            raise SystemExit("sem META_TOKEN nem IG_ACCESS_TOKEN — não há como publicar")
        ig_id = os.environ.get("IG_USER_ID", "").strip() or ig_id_do_token(token)

    ja = ja_no_perfil(ig_id, token, c["legenda"])
    if ja:
        log(f"já está no perfil ({ja}); só registrando")
        st["publicados"][chave(c)] = {"media_id": ja, "quando": "achado no perfil"}
        gravar_estado(st)
        return

    arquivos = renderizar(c, SAIDA)
    repo = filamod.Repo()
    urls, nomes = [], []
    for p in arquivos:
        nomes.append(p.name)
        urls.append(repo.subir(RELEASE, p, p.name))
    log(f"{len(urls)} slides hospedados; publicando {c['titulo']}")
    try:
        media_id = publicar(ig_id, token, urls, c["legenda"])
    finally:
        for a in repo.assets(RELEASE):
            if a["name"] in nomes:
                try:
                    repo.apagar(a["id"])
                except Exception:
                    pass
    log(f"NO AR: {media_id} — {c['titulo']}")
    st["publicados"][chave(c)] = {
        "media_id": media_id,
        "quando": datetime.now(FUSO).isoformat(timespec="seconds"),
        "titulo": c["titulo"],
    }
    gravar_estado(st)
    # o registro humano fica no próprio estado: publicados.md é escrito pelo
    # workflow dos stories, e dois workflows anexando no mesmo arquivo dão
    # conflito de rebase na hora do push.



if __name__ == "__main__":
    main()
