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
import re
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
# 03/10/2026: Inter no lugar da Archivo. Os carrosséis estilo tweet dos grandes perfis
# (Hormozi, Justin Welsh) usam a fonte do Twitter (Chirp/Helvetica), e a Inter é a
# equivalente livre mais próxima.
FONTE = AQUI / "fontes" / "Inter.ttf"
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
        f.set_variation_by_axes([min(32, max(14, tam // 2)), peso])   # Optical size, Weight
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


def desenhar(texto: str, i: int, total: int, peso_capa: bool = False) -> Image.Image:
    capa, cta = i == 0, i == total - 1
    im = Image.new("RGB", (L, A), NAVY if cta else BRANCO)
    d = ImageDraw.Draw(im)
    d.rectangle([90, 96, 90 + (320 if capa else 120), 106], fill=CHAMP)

    # 03/10/2026: tamanho medido nos carrosséis estilo tweet de Hormozi e Justin Welsh,
    # texto corrido a ~48 px num slide de 1080 (era 78, e 100 na capa).
    tam, peso = (56, 700) if capa or peso_capa else (48, 400)
    while True:
        f = fonte(tam, peso)
        linhas = quebrar(d, texto, f, LARGURA)
        if len(linhas) * tam * 1.3 <= A - 460 or tam <= 30:
            break
        tam -= 3
    bloco = len(linhas) * tam * 1.3
    y = max(190, (A - bloco) / 2 - 40)
    cor = BRANCO if cta else NAVY
    for linha in linhas:
        d.text((MARGEM, y), linha, font=f, fill=cor, anchor="la")
        y += tam * 1.3

    rod = fonte(30, 500)
    d.text((MARGEM, A - 150), "@vendanaobra", font=rod, anchor="la",
           fill=(195, 199, 207) if cta else (154, 163, 173))
    if not cta:
        n = f"{i + 1}/{total}"
        d.text((L - MARGEM - d.textlength(n, font=rod), A - 150), n,
               font=rod, fill=CHAMP, anchor="la")
    return im


# ---- teste A/B da capa (aprovado pelo Diego em 02/10/2026) --------------------
# Os grandes perfis de negócio (Primo Rico, Thiago Reis, Hormozi) abrem o carrossel
# com rosto + nome no estilo de post/tweet; o nosso melhor carrossel (05/09, 2.118
# views) também tinha rosto. Nenhum estudo mede estilo, então medimos aqui: a capa
# alterna dia sim, dia não entre "tweet" e "tipografica" a partir de 02/10, e o
# miolo fica igual. Régua em 31/10: (salvos + compartilhamentos) por mil alcançados.
# Carrossel com 10+ slides tem o slide 2 escrito como SEGUNDA CAPA (o Instagram
# reexibe o post a partir do slide 2 para quem não deslizou) e ganha o peso da capa.
TESTE_CAPA_INICIO = "2026-10-02"
AVATAR = AQUI / "fontes" / "avatar-diego.jpg"
CINZA = (110, 118, 130)


def variante_capa(dia: str) -> str:
    # 03/10/2026: teste A/B encerrado pelo Diego. O carrossel de 02/10 ("Quando o cliente
    # diz...", capa tweet) é o modelo; o de 03/10 saiu tipográfico e foi apagado do perfil.
    if dia < TESTE_CAPA_INICIO:
        return "tipografica"
    return "tweet"


def _avatar(tam: int):
    f = Image.open(AVATAR).convert("RGB").resize((tam, tam), Image.LANCZOS)
    masc = Image.new("L", (tam * 4, tam * 4), 0)
    ImageDraw.Draw(masc).ellipse([0, 0, tam * 4, tam * 4], fill=255)
    return f, masc.resize((tam, tam), Image.LANCZOS)


def desenhar_capa_tweet(texto: str, numeros: list | None = None) -> Image.Image:
    """Capa estilo post: foto, nome e @ do Diego, a frase e (se houver) o quadro do número."""
    im = Image.new("RGB", (L, A), BRANCO)
    d = ImageDraw.Draw(im)
    tam_av, y0 = 120, 150
    f, m = _avatar(tam_av)
    im.paste(f, (MARGEM, y0), m)
    d.text((MARGEM + tam_av + 28, y0 + 24), "Diego Moraes", font=fonte(44, 700), fill=NAVY)
    d.text((MARGEM + tam_av + 28, y0 + 76), "@vendanaobra", font=fonte(38, 400), fill=CINZA)

    numeros = [n for n in (numeros or []) if n.get("num")][:2]
    topo, fundo = y0 + tam_av + 60, A - 190
    espaco = (fundo - topo) - (420 if numeros else 0)
    tam = 54 if not numeros else 50
    while True:
        ft = fonte(tam, 500)
        blocos = [quebrar(d, par, ft, LARGURA) for par in texto.split("\n\n")]
        altura = sum(len(b) for b in blocos) * tam * 1.25 + (len(blocos) - 1) * tam * 0.5
        if altura <= espaco or tam <= 40:
            break
        tam -= 3
    y = topo if numeros else max(topo, topo + (espaco - altura) / 2 - 40)
    for b in blocos:
        for linha in b:
            d.text((MARGEM, y), linha, font=ft, fill=NAVY)
            y += tam * 1.25
        y += tam * 0.5

    if numeros:
        y1 = fundo
        y0q = max(int(y + 10), y1 - 420)
        x1 = L - MARGEM
        d.rounded_rectangle([MARGEM, y0q, x1, y1], radius=36, fill=NAVY)
        cy = (y0q + y1) // 2
        fl = fonte(32, 500)
        if len(numeros) == 1:
            n = numeros[0]
            tn = 120
            while d.textlength(n["num"], font=fonte(tn, 800)) > x1 - MARGEM - 80 and tn > 60:
                tn -= 6
            d.text(((MARGEM + x1) // 2, cy + 40), n["num"], font=fonte(tn, 800), fill=CHAMP, anchor="ms")
            d.text(((MARGEM + x1) // 2, cy + 110), n.get("rot", ""), font=fl,
                   fill=(195, 199, 207), anchor="ms")
        else:
            meio = (MARGEM + x1) // 2
            larg = meio - MARGEM - 120
            tn = 120
            while max(d.textlength(n["num"], font=fonte(tn, 800)) for n in numeros) > larg and tn > 50:
                tn -= 6
            for cx, n, cor in ((MARGEM + (meio - MARGEM) // 2, numeros[0], BRANCO),
                               (meio + (x1 - meio) // 2, numeros[1], CHAMP)):
                d.text((cx, cy + 40), n["num"], font=fonte(tn, 800), fill=cor, anchor="ms")
                d.text((cx, cy + 110), n.get("rot", ""), font=fl, fill=(195, 199, 207), anchor="ms")
            d.text((meio, cy - 15), "→", font=fonte(80, 500), fill=(120, 130, 150), anchor="mm")

    rod = fonte(30, 500)
    d.text((MARGEM, A - 150), "arrasta para o lado", font=rod, fill=CINZA, anchor="la")
    d.text((L - MARGEM, A - 150 + 15), "→", font=fonte(52, 600), fill=CHAMP, anchor="rm")
    return im


def desenhar_segunda_capa(texto: str, total: int) -> Image.Image:
    return desenhar(texto, 1, total, peso_capa=True)   # peso e tamanho da capa, número 2/N


def renderizar(c: dict, pasta: Path) -> list[Path]:
    pasta.mkdir(parents=True, exist_ok=True)
    arquivos = []
    total = len(c["slides"])
    capa = variante_capa(c["dia"])
    for i, texto in enumerate(c["slides"]):
        p = pasta / f"{c['dia']}-carrossel{c['n']}-{i + 1:02d}.jpg"
        if i == 0 and capa == "tweet":
            im = desenhar_capa_tweet(texto, c.get("capa_numero"))
        elif i == 1 and total >= 10 and c["dia"] >= TESTE_CAPA_INICIO:
            im = desenhar_segunda_capa(texto, total)
        else:
            im = desenhar(texto, i, total)
        im.save(p, "JPEG", quality=92)
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

def sem_pontuacao_pesada(t: str) -> str:
    """Sem travessão e sem ponto e vírgula (pedido do Diego, 27/09/2026).

    Sites e perfis grandes do mercado não usam nenhum dos dois. O texto nasce limpo
    no app Canteiro, e isto é só a rede de segurança para o que escapar.
    """
    t = re.sub(r"(?m)^[ \t]*[—–][ \t]*", "· ", t or "")
    t = re.sub(r"(\d)\s*–\s*(\d)", r"\1 a \2", t)
    t = re.sub(r"[ \t]+[—–][ \t]+", ", ", t)
    t = re.sub(r"[—–]", ",", t)
    t = re.sub(r";[ \t]*$", "", t, flags=re.M)
    t = re.sub(r";\s+(\w)", lambda m: ". " + m.group(1).upper(), t)
    return t.replace(";", ".")


CTA_BIO = ("Siga o @vendanaobra. Desenvolvo empresas da construção a vender mais "
           "e de forma previsível.")


def garantir_cta(t: str) -> str:
    """Toda legenda leva a linha de transformação da bio (Rota 100K, 30/09/2026).

    O app já escreve assim. Isto cobre legenda antiga que ainda feche só com
    "@vendanaobra": a linha solta vira o CTA; sem ela, o CTA entra antes das hashtags.
    """
    t = t or ""
    if "de forma previsível" in t:
        return t
    if re.search(r"(?m)^@vendanaobra[ \t]*$", t):
        return re.sub(r"\n?^@vendanaobra[ \t]*$", "\n\n" + CTA_BIO, t, count=1, flags=re.M)
    m = re.search(r"(?m)^#", t)
    if m:
        return t[:m.start()].rstrip() + "\n\n" + CTA_BIO + "\n\n" + t[m.start():]
    return t.rstrip() + "\n\n" + CTA_BIO


FIM_DE_FRASE = re.compile(r"(?<=[A-Za-zÀ-ÿ%)\]])\.[ \t]+(?=[A-ZÀ-Ý\"“«])")


def sem_ponto_final(t: str) -> str:
    """Nas redes não se usa ponto final (pedido do Diego, 30/09/2026).

    A frase acaba sem ponto e a próxima começa depois de uma linha em branco. O
    ponto de lista ("1. ") e as reticências ficam. Rede de segurança: o app já
    escreve assim.
    """
    saida = []
    for linha in (t or "").split("\n"):
        partes = FIM_DE_FRASE.split(linha)
        partes = [re.sub(r"(?<!\.)\.([\"”]?)[ \t]*$", r"\1", p) for p in partes]
        saida.append("\n\n".join(partes))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(saida)).strip()


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
    for c in todos:
        c["slides"] = [re.sub(r"(?<!\.)\.([\"”]?)\s*$", r"\1", sem_pontuacao_pesada(s))
                       for s in c["slides"]]
        c["legenda"] = sem_ponto_final(garantir_cta(sem_pontuacao_pesada(c["legenda"])))
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
        "capa": variante_capa(c["dia"]),
        "slides": len(c["slides"]),
    }
    gravar_estado(st)
    # o registro humano fica no próprio estado: publicados.md é escrito pelo
    # workflow dos stories, e dois workflows anexando no mesmo arquivo dão
    # conflito de rebase na hora do push.



if __name__ == "__main__":
    main()
