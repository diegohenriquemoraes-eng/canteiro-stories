"""A fila é uma Release do próprio repositório — não há banco, painel nem app.

O Diego abre a página da Release no navegador do celular, anexa as fotos e os
vídeos do dia com o horário no começo do nome (`0930-fundacao.jpg`) e acabou:
o horário É o agendamento. Release e não commit porque vídeo no Git incha o
histórico para sempre, e porque a Graph API precisa de uma URL pública para
baixar a mídia — o asset de Release de repo público é exatamente isso.

Duas Releases separadas de propósito: `fila` é a caixa de entrada dele,
`pronto` guarda o arquivo já normalizado que o Instagram vem buscar. Fossem a
mesma, o arquivo pronto seria lido como entrada nova na rodada seguinte.
"""

from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import requests

API = "https://api.github.com"
UPLOADS = "https://uploads.github.com"

# Horário no começo do nome, com data opcional na frente:
#   0930-fundacao.jpg · 930 concreto.mp4 · 09h30.jpg · 1500.jpeg
#   2026-09-05-0930-laje.jpg · 20260905-0930-laje.jpg
RE_NOME = re.compile(
    r"^(?:(\d{4})-(\d{2})-(\d{2})|(\d{4})(\d{2})(\d{2}))?[ ._-]*"
    r"(\d{1,2})[hH:._-]?(\d{2})(?=\D|$)"
)


class FilaErro(Exception):
    pass


# ------------------------------------------------------------- o horário ---

def alvo_do_nome(nome: str, agora: datetime, atraso_max_min: int):
    """Quando este arquivo deve ir ao ar. None se o nome não diz horário.

    Sem data no nome, o horário vale para a PRÓXIMA ocorrência: se já passou
    há pouco, é hoje (cobre cron atrasado e upload em cima da hora); se passou
    há muito, é amanhã — que é o que alguém quer dizer ao subir `0800-x.jpg`
    às duas da tarde.
    """
    m = RE_NOME.match(Path(nome).stem)
    if not m:
        return None
    a1, m1, d1, a2, m2, d2, hh, mm = m.groups()
    hora, minuto = int(hh), int(mm)
    if hora > 23 or minuto > 59:
        return None

    tz = agora.tzinfo
    ano, mes, dia = (a1 or a2), (m1 or m2), (d1 or d2)
    if ano:
        try:
            return datetime(int(ano), int(mes), int(dia), hora, minuto, tzinfo=tz)
        except ValueError:
            return None

    hoje = agora.replace(hour=hora, minute=minuto, second=0, microsecond=0)
    if hoje >= agora - timedelta(minutes=atraso_max_min):
        return hoje
    return hoje + timedelta(days=1)


# -------------------------------------------------------------- a Release ---

def _repo() -> str:
    r = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if r:
        return r
    url = subprocess.run(["git", "remote", "get-url", "origin"],
                         capture_output=True, text=True).stdout.strip()
    m = re.search(r"github\.com[:/](.+?/.+?)(?:\.git)?$", url)
    if not m:
        raise FilaErro("não sei em que repositório estou (sem GITHUB_REPOSITORY "
                       "e sem remote origin do GitHub)")
    return m.group(1)


def _token() -> str:
    for chave in ("GH_TOKEN", "GITHUB_TOKEN"):
        v = os.environ.get(chave, "").strip()
        if v:
            return v
    # fora do Actions, aproveita a credencial que o Git já guardou
    p = subprocess.run(["git", "credential", "fill"], input=(
        "protocol=https\nhost=github.com\n\n"), capture_output=True, text=True)
    for linha in p.stdout.splitlines():
        if linha.startswith("password="):
            return linha.split("=", 1)[1]
    raise FilaErro("sem token do GitHub (GH_TOKEN/GITHUB_TOKEN)")


class Repo:
    def __init__(self) -> None:
        self.repo = _repo()
        self.sessao = requests.Session()
        self.sessao.headers.update({
            "Authorization": f"Bearer {_token()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })

    def _ok(self, r: requests.Response) -> dict:
        if r.status_code >= 300:
            raise FilaErro(f"GitHub {r.status_code}: {r.text[:300]}")
        return r.json() if r.content else {}

    def release(self, tag: str, titulo: str = "", notas: str = "") -> dict:
        r = self.sessao.get(f"{API}/repos/{self.repo}/releases/tags/{tag}")
        if r.status_code == 200:
            return r.json()
        return self._ok(self.sessao.post(
            f"{API}/repos/{self.repo}/releases",
            json={"tag_name": tag, "name": titulo or tag, "body": notas}))

    def assets(self, tag: str) -> list[dict]:
        rel = self.release(tag)
        return sorted(rel.get("assets", []), key=lambda a: a["name"])

    def baixar(self, asset: dict, destino: Path) -> Path:
        # o asset de repo público resolve pela URL de download; a de API com
        # Accept: octet-stream funciona nos dois casos e não depende disso
        r = self.sessao.get(f"{API}/repos/{self.repo}/releases/assets/{asset['id']}",
                            headers={"Accept": "application/octet-stream"},
                            stream=True, timeout=300)
        if r.status_code >= 300:
            raise FilaErro(f"não consegui baixar {asset['name']}: {r.status_code}")
        destino.parent.mkdir(parents=True, exist_ok=True)
        with destino.open("wb") as fh:
            for bloco in r.iter_content(1 << 20):
                fh.write(bloco)
        return destino

    def subir(self, tag: str, arquivo: Path, nome: str) -> str:
        """Sobe (substituindo homônimo) e devolve a URL pública do asset."""
        rel = self.release(tag, "Mídia pronta (temporária)",
                           "Arquivos já normalizados que o Instagram vem "
                           "buscar. São apagados depois de publicados.")
        for a in rel.get("assets", []):
            if a["name"] == nome:
                self.apagar(a["id"])
        # O GitHub serve TODO asset como application/octet-stream, mande-se o
        # que mandar no upload — conferido. O que o Instagram usa para
        # reconhecer a mídia é a extensão no fim da URL, e é por isso que o
        # nome do asset precisa terminar em .jpg/.mp4. Mesmo caminho que o
        # pipeline dos Reels usa em produção desde 24/07, inclusive para as
        # capas (imagem).
        r = self.sessao.post(
            f"{UPLOADS}/repos/{self.repo}/releases/{rel['id']}/assets",
            params={"name": nome},
            headers={"Content-Type": "application/octet-stream"},
            data=arquivo.read_bytes(), timeout=600)
        return self._ok(r)["browser_download_url"]

    def apagar(self, asset_id: int) -> None:
        self.sessao.delete(f"{API}/repos/{self.repo}/releases/assets/{asset_id}")
