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
ENTRADA = "entrada"      # branch descartável onde a página de envio grava
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


# ------------------------------------------------- arquivo grande em partes ---
#
# A API de blobs do GitHub recusa arquivo grande: medido em 04/09/2026, um video
# de 75 MB levou 422 — "your input was too large to process". Nao adianta
# otimizar o envio, o limite e' do servidor. Entao a pagina de envio fatia o
# arquivo em pedacos pequenos e grava um manifesto junto; aqui a fila junta tudo
# de volta ANTES de qualquer coisa, e so aceita se o resultado bater byte a byte
# com o que saiu do celular.
#
#   2026-09-04-1930-solucao.p1de9     ... .p9de9   (pedacos, sem extensao)
#   2026-09-04-1930-solucao.partes.json           (nome, bytes, sha256, ext)
#
# Os pedacos nao tem extensao de midia de proposito: se o manifesto faltar ou o
# envio parar no meio, nada disso e' confundido com um Story pronto para ir ao
# ar — some da fila em silencio em vez de publicar video quebrado.

RE_PARTE = re.compile(r"^(?P<base>.+)\.p(?P<i>\d+)de(?P<n>\d+)$")
SUFIXO_MANIFESTO = ".partes.json"


def juntar_partes(itens: list[dict]) -> tuple[list[dict], list[str]]:
    """Troca os pedacos de cada arquivo por um item so.

    Devolve (itens, incompletos). Um conjunto so vira item quando o manifesto
    esta la E todos os pedacos de 1 a n existem — faltando qualquer coisa, ele
    fica de fora e o nome vai em `incompletos` para o log (o envio pode estar
    em andamento; na proxima rodada estara completo).
    """
    manifestos, pedacos, soltos = {}, {}, []
    for it in itens:
        nome = it["name"]
        if nome.endswith(SUFIXO_MANIFESTO):
            manifestos[nome[:-len(SUFIXO_MANIFESTO)]] = it
            continue
        m = RE_PARTE.match(nome)
        if m:
            pedacos.setdefault(m["base"], {})[int(m["i"])] = (int(m["n"]), it)
            continue
        soltos.append(it)

    incompletos = []
    for base, man in sorted(manifestos.items()):
        achados = pedacos.pop(base, {})
        total = next(iter(achados.values()))[0] if achados else 0
        if not achados or len(achados) != total or set(achados) != set(range(1, total + 1)):
            incompletos.append(f"{base} ({len(achados)} de {total or '?'} pedaços)")
            continue
        soltos.append({
            "name": base, "origem": "partes", "manifesto": man,
            "partes": [achados[i][1] for i in range(1, total + 1)],
            "size": sum(p[1].get("size", 0) for p in achados.values()),
        })
    for base, achados in pedacos.items():          # pedaços sem manifesto
        incompletos.append(f"{base} (sem manifesto)")
    return soltos, incompletos


def baixar_montado(repo, item: dict, destino: Path) -> Path:
    """Remonta o arquivo a partir dos pedacos e SO devolve se conferir.

    O manifesto traz o tamanho e o sha256 do arquivo que saiu do celular. Se o
    remontado nao bater nos dois, levanta — publicar video truncado no Story e'
    pior do que nao publicar, e o erro vira issue no workflow.
    """
    import hashlib
    import json as _json

    man_txt = repo.entrada_baixar(item["manifesto"], destino.with_suffix(".manifesto"))
    man = _json.loads(man_txt.read_text(encoding="utf-8"))
    man_txt.unlink(missing_ok=True)

    destino.parent.mkdir(parents=True, exist_ok=True)
    h, escritos = hashlib.sha256(), 0
    with destino.open("wb") as saida:
        for i, parte in enumerate(item["partes"], 1):
            tmp = destino.with_suffix(f".p{i}")
            repo.entrada_baixar(parte, tmp)
            dados = tmp.read_bytes()
            saida.write(dados)
            h.update(dados)
            escritos += len(dados)
            tmp.unlink(missing_ok=True)

    if man.get("bytes") and escritos != man["bytes"]:
        destino.unlink(missing_ok=True)
        raise FilaErro(f"{item['name']}: remontado com {escritos} bytes, "
                       f"o manifesto diz {man['bytes']}")
    if man.get("sha256") and h.hexdigest() != man["sha256"]:
        destino.unlink(missing_ok=True)
        raise FilaErro(f"{item['name']}: o arquivo remontado nao confere com o "
                       "que saiu do celular (sha256 diferente)")
    return destino


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

    # ------------------------------------------- a branch que a página usa ---
    #
    # A página de envio (docs/index.html) roda no navegador do celular e o
    # upload de asset de Release é impossível de lá: uploads.github.com não
    # responde ao preflight de CORS (conferido). A api.github.com responde, e
    # é por ela que a página grava aqui.
    #
    # A branch `entrada` é SEMPRE um commit único e ÓRFÃO — sem pai. Reescrita
    # a cada envio e a cada publicação, ela nunca acumula histórico: é o que
    # permite trafegar vídeo por dentro do Git sem inchar o repositório para
    # sempre, que é o motivo de a fila original ser uma Release.

    def entrada_listar(self) -> list[dict]:
        r = self.sessao.get(f"{API}/repos/{self.repo}/git/trees/{ENTRADA}")
        if r.status_code == 404:
            return []
        arvore = self._ok(r).get("tree", [])
        return sorted(({"name": n["path"], "sha": n["sha"], "size": n.get("size", 0),
                        "origem": "branch"} for n in arvore if n["type"] == "blob"),
                      key=lambda a: a["name"])

    def entrada_baixar(self, item: dict, destino: Path) -> Path:
        r = self.sessao.get(f"{API}/repos/{self.repo}/git/blobs/{item['sha']}",
                            headers={"Accept": "application/vnd.github.raw"},
                            stream=True, timeout=300)
        if r.status_code >= 300:
            raise FilaErro(f"não consegui baixar {item['name']}: {r.status_code}")
        destino.parent.mkdir(parents=True, exist_ok=True)
        with destino.open("wb") as fh:
            for bloco in r.iter_content(1 << 20):
                fh.write(bloco)
        return destino

    def entrada_remover(self, nomes: set[str]) -> None:
        """Reescreve a branch sem os arquivos já publicados (commit órfão)."""
        restantes = [i for i in self.entrada_listar() if i["name"] not in nomes]
        if not restantes:
            # a API recusa criar árvore vazia ("Invalid tree info"): fila sem
            # nada é a branch não existir, que entrada_listar já lê como vazia
            self.sessao.delete(f"{API}/repos/{self.repo}/git/refs/heads/{ENTRADA}")
            return
        tree = self._ok(self.sessao.post(f"{API}/repos/{self.repo}/git/trees", json={
            "tree": [{"path": i["name"], "mode": "100644", "type": "blob",
                      "sha": i["sha"]} for i in restantes]}))
        commit = self._ok(self.sessao.post(f"{API}/repos/{self.repo}/git/commits", json={
            "message": f"fila: {len(restantes)} pendente(s)",
            "tree": tree["sha"], "parents": []}))
        r = self.sessao.patch(f"{API}/repos/{self.repo}/git/refs/heads/{ENTRADA}",
                              json={"sha": commit["sha"], "force": True})
        if r.status_code == 422:      # a ref pode não existir ainda
            self._ok(self.sessao.post(f"{API}/repos/{self.repo}/git/refs", json={
                "ref": f"refs/heads/{ENTRADA}", "sha": commit["sha"]}))
        elif r.status_code >= 300:
            raise FilaErro(f"não consegui atualizar a fila: {r.status_code} {r.text[:200]}")
