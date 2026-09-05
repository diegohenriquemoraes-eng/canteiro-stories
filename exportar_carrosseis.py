# -*- coding: utf-8 -*-
"""Tira os carrosseis do app Canteiro e publica o JSON que a pagina de artes le.

O carrossel e' o unico post que o Diego publica a mao — a API do Instagram nao
poe musica, e musica e' o que joga o carrossel na aba de Reels (exigencia do
metodo). Entao o app escreve os slides, esta pagina desenha as artes no proprio
navegador do celular e ele salva/compartilha na hora de postar.

Nao gera imagem aqui de proposito: imagem commitada incharia o repo para sempre
(3 carrosseis/dia x 8 slides). O desenho e' feito em canvas, na hora.

Uso: python exportar_carrosseis.py            # le o app e escreve docs/carrosseis.json
     python exportar_carrosseis.py --ver      # so mostra o que sairia
"""
import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path

APP = Path(r"C:\Users\NOTE\Desktop\Perffec\Claude\Canteiro\canteiro-vno.html")
SAIDA = Path(__file__).parent / "docs" / "carrosseis.json"


def dias_do_app(caminho: Path):
    """Avalia o trecho do app que define DIAS — e' JS puro, sem DOM ate' ali."""
    html = caminho.read_text(encoding="utf-8")
    ini = html.rindex("<script>") + len("<script>")
    corpo = html[ini:]
    fim = corpo.index("\n];", corpo.index("const DIAS")) + len("\n];")
    js = corpo[:fim] + "\nconsole.log(JSON.stringify(DIAS));"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as f:
        f.write(js)
        tmp = f.name
    try:
        saida = subprocess.run(["node", tmp], capture_output=True, text=True,
                               encoding="utf-8", check=True).stdout
    finally:
        Path(tmp).unlink(missing_ok=True)
    return json.loads(saida)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--ver", action="store_true")
    o = a.parse_args()

    ano = 2026
    out = []
    for d in dias_do_app(APP):
        dia, mes = d["data"].split("/")
        for i, c in enumerate(d.get("carrosseis") or []):
            out.append({
                "dia": f"{ano}-{mes}-{dia}",
                "dow": d.get("dow", ""),
                "hora": c.get("hora", ""),
                "n": i + 1,
                "titulo": c.get("titulo", ""),
                "slides": c.get("slides", []),
                "legenda": c.get("legenda", ""),
            })

    out.sort(key=lambda x: (x["dia"], x["hora"]))
    print(f"{len(out)} carrosséis, de {out[0]['dia']} a {out[-1]['dia']}"
          if out else "nenhum carrossel encontrado")
    for c in out:
        print(f"  {c['dia']} {c['hora']}  {len(c['slides'])} slides  {c['titulo'][:50]}")
    if o.ver:
        return
    SAIDA.parent.mkdir(exist_ok=True)
    SAIDA.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\ngravado em {SAIDA}")


if __name__ == "__main__":
    main()
