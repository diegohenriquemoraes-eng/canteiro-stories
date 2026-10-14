"""Publica sozinho o story "fato do dia" às 08h50 (pedido do Diego, 14/10/2026).

Formato de 2 toques por dia: o robô posta o fato (arte de texto, sem foto), o
Diego posta à mão a caixinha de manhã e o vídeo + oferta às 18h30. É a única
exceção à regra de 26/09 ("o único story automático é o que ele mesmo sobe"):
foi ele quem pediu este robô.

Lê `docs/fatos.json` (exportado do app Canteiro por `exportar_carrosseis.py`),
desenha a arte 1080x1920 no padrão do carrossel (navy, champagne, Inter),
hospeda na Release `pronto` e publica com `media_type=STORIES`. O estado em
`state_story_fato.json` impede duplicata.

Uso: python story_fato.py [--agora] [--data AAAA-MM-DD] [--dry-run] [--render-apenas]
     python story_fato.py --fixas      # redesenha as 3 artes fixas em saida/stories-fixos
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from PIL import Image, ImageDraw

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

import carrossel as car        # noqa: E402  (fonte, quebrar, log, cores, Graph)
import fila as filamod         # noqa: E402

DADOS = AQUI / "docs" / "fatos.json"
STATE = AQUI / "state_story_fato.json"
SAIDA = AQUI / "saida" / "story-fato"
FIXAS = AQUI / "saida" / "stories-fixos"

L, A = 1080, 1920
MARGEM = 100
# Zona segura do story: o Instagram cobre ~250 px em cima (barra e nome) e
# ~300 px embaixo (campo de resposta). O texto mora no meio.
TOPO, BASE = 330, A - 380

ESPERA_MIN = 120
ATRASO_MAX_MIN = 90     # fato depois das 10h20 já não anuncia a caixinha da manhã


def arte(rotulo: str, frases: list[str], rodape: str, espaco_sticker: int = 0) -> Image.Image:
    """Fundo navy, rótulo champagne, frases grandes em branco, rodapé discreto.

    `espaco_sticker` reserva altura livre abaixo do texto para o sticker que o
    Diego cola por cima (caixinha ou link).
    """
    im = Image.new("RGB", (L, A), car.NAVY)
    d = ImageDraw.Draw(im)
    texto = "\n\n".join(car.sem_pontuacao_pesada(f) for f in frases)
    tam = 78
    while True:
        f = car.fonte(tam, 700)
        linhas = car.quebrar(d, texto, f, L - MARGEM * 2)
        altura = len(linhas) * tam * 1.25
        if altura <= BASE - TOPO - 160 - espaco_sticker or tam <= 44:
            break
        tam -= 4
    y = TOPO + max(0, (BASE - TOPO - 160 - espaco_sticker - altura) / 2)
    d.rectangle([MARGEM, y, MARGEM + 140, y + 10], fill=car.CHAMP)
    rf = car.fonte(36, 700)
    d.text((MARGEM, y + 40), rotulo.upper(), font=rf, fill=car.CHAMP, anchor="la")
    y += 130
    for linha in linhas:
        d.text((MARGEM, y), linha, font=f, fill=car.BRANCO, anchor="la")
        y += tam * 1.25
    pf = car.fonte(34, 500)
    for n, linha in enumerate(car.quebrar(d, rodape, pf, L - MARGEM * 2)):
        d.text((MARGEM, BASE - 40 + n * 46), linha, font=pf, fill=(195, 199, 207), anchor="la")
    return im


def desenhar_fato(c: dict) -> Path:
    SAIDA.mkdir(parents=True, exist_ok=True)
    p = SAIDA / f"{c['dia']}-0850-fato.jpg"
    arte("Fato do dia", c["frases"], "@vendanaobra · hoje de manhã tem caixinha do Plantão da Objeção").save(
        p, "JPEG", quality=92)
    return p


FIXAS_TEXTO = {
    "caixinha-plantao-da-objecao.jpg": ("Plantão da Objeção", [
        "Qual objeção de preço travou a tua venda?",
        "Eu respondo a melhor hoje às 18h30"], "@vendanaobra · todo dia de manhã", 360),
    "oferta-caderno.jpg": ("Caderno do Vendedor da Construção", [
        "Criei a partir do meu método de vendas: Atração, Conexão, Diagnóstico, Oferta e Decisão",
        "Roteiro e rotina em cada passo, do primeiro contato ao fechamento"], "@vendanaobra · toque no link", 260),
    "oferta-raio-x.jpg": ("Raio-X Comercial gratuito", [
        "Quer ver onde o teu comercial perde margem sem perceber?",
        "Você responde no celular e vê onde está o teu maior vazamento comercial"], "@vendanaobra · toque no link", 260),
}


def desenhar_fixas() -> list[Path]:
    FIXAS.mkdir(parents=True, exist_ok=True)
    feitos = []
    for nome, (rot, frases, rod, esp) in FIXAS_TEXTO.items():
        p = FIXAS / nome
        arte(rot, frases, rod, esp).save(p, "JPEG", quality=92)
        feitos.append(p)
    return feitos


def publicar_story(ig_id: str, token: str, url: str) -> str:
    j = requests.post(f"{car.GRAPH}/{ig_id}/media",
                      data={"media_type": "STORIES", "image_url": url, "access_token": token},
                      timeout=120).json()
    if "id" not in j:
        raise SystemExit(f"falha ao criar o story: {j}")
    car.esperar_pronto(j["id"], token)
    p = requests.post(f"{car.GRAPH}/{ig_id}/media_publish",
                      data={"creation_id": j["id"], "access_token": token}, timeout=120).json()
    if "id" not in p:
        raise SystemExit(f"falha no media_publish: {p}")
    return p["id"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--agora", action="store_true")
    ap.add_argument("--data")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--render-apenas", action="store_true")
    ap.add_argument("--fixas", action="store_true")
    args = ap.parse_args()

    if args.fixas:
        for p in desenhar_fixas():
            car.log(f"desenhado: {p}")
        return

    agora = datetime.now(car.FUSO)
    dia = args.data or agora.date().isoformat()
    c = next((x for x in car.carregar(DADOS, []) if x["dia"] == dia), None)
    if not c:
        car.log(f"nenhum fato do dia no app para {dia}")
        return
    if args.render_apenas:
        car.log(f"desenhado: {desenhar_fato(c)}")
        return

    st = car.carregar(STATE, {"publicados": {}})
    st.setdefault("publicados", {})
    if dia in st["publicados"]:
        car.log(f"fato de {dia} já publicado")
        return

    h, m = map(int, c["hora"].split(":"))
    alvo = datetime.fromisoformat(dia).replace(hour=h, minute=m, tzinfo=car.FUSO)
    if not args.agora:
        falta = (alvo - agora).total_seconds() / 60
        if falta > ESPERA_MIN:
            car.log(f"cedo demais: o fato é às {c['hora']} (faltam {falta:.0f} min)")
            return
        if -falta > ATRASO_MAX_MIN:
            car.log(f"PERDIDO: o fato era às {c['hora']} e já passou {-falta:.0f} min")
            return
        if falta > 0 and not args.dry_run:
            car.log(f"esperando {falta:.0f} min até {c['hora']}")
            time.sleep(falta * 60)

    if args.dry_run:
        car.log(f"[dry-run] publicaria o fato de {dia}: {' / '.join(c['frases'])}")
        return

    token = os.environ.get("META_TOKEN", "").strip()
    if not token:
        raise SystemExit("sem META_TOKEN: não há como publicar o story")
    car.GRAPH = car.GRAPH_META
    ig_id = os.environ.get("IG_BUSINESS_ID", "").strip() or car.IG_BUSINESS_ID

    p = desenhar_fato(c)
    repo = filamod.Repo()
    url = repo.subir(car.RELEASE, p, p.name)
    try:
        media_id = publicar_story(ig_id, token, url)
    finally:
        for a in repo.assets(car.RELEASE):
            if a["name"] == p.name:
                try:
                    repo.apagar(a["id"])
                except Exception:
                    pass
    car.log(f"NO AR: {media_id} (fato de {dia})")
    st["publicados"][dia] = {"media_id": media_id,
                             "quando": datetime.now(car.FUSO).isoformat(timespec="seconds")}
    STATE.write_text(car.json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
