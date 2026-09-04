"""Renova o token de longa duração do Instagram — e deixa rastro de quando vence.

O token da "API com login do Instagram" vale 60 dias e é renovável: cada
renovação devolve outros 60. Enquanto a renovação acontecer, ele nunca expira
na prática. O que derruba um pipeline assim não é o prazo, é a renovação
falhar em silêncio — por isso aqui:

  * roda SEMANALMENTE (não mensalmente): com 60 dias de validade, são ~8
    tentativas antes de vencer. Uma falha isolada, ou duas, não derrubam nada.
  * grava `token.json` no repositório com a data de vencimento, para que
    qualquer execução possa dizer quanto falta sem precisar de segredo.
  * falha ALTO quando não consegue renovar — o workflow abre issue, que vira
    e-mail. Silêncio é o único modo de falha que não pode existir aqui.

Uso local (o token atual no ambiente):
    IG_ACCESS_TOKEN=<token atual> python refresh_token.py

No GitHub Actions, precisa de um PAT em REPO_PAT com permissão de escrever
Secrets — é o que permite gravar o token novo sozinho. Sem ele o script falha
de propósito: o repositório é público, o log do Actions também é, e o token
recém-gerado NÃO é mascarado (o mascaramento automático só cobre o valor já
cadastrado como secret), então imprimi-lo ali seria publicá-lo.

Alternativa sem validade nenhuma: um token de System User de um Portfólio
Comercial não expira — mas exige a API com login do FACEBOOK
(graph.facebook.com) e a conta vinculada a uma Página, que é outra
arquitetura. Ver o README.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

GRAPH = "https://graph.instagram.com"
AQUI = Path(__file__).resolve().parent
REGISTRO = AQUI / "token.json"

# abaixo disto o vencimento é notícia, não rotina
ALERTA_DIAS = 21


def gravar_registro(dias: int) -> None:
    agora = datetime.now(timezone.utc)
    REGISTRO.write_text(json.dumps({
        "renovado_em": agora.isoformat(timespec="seconds"),
        "expira_em": (agora + timedelta(days=dias)).isoformat(timespec="seconds"),
        "dias_na_renovacao": dias,
        "_nota": "Escrito por refresh_token.py. Serve para qualquer execução "
                 "saber quanto falta sem precisar do token em mãos.",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def dias_restantes() -> int | None:
    """Quanto falta pelo último registro. None se nunca foi renovado."""
    if not REGISTRO.exists():
        return None
    try:
        expira = datetime.fromisoformat(
            json.loads(REGISTRO.read_text(encoding="utf-8"))["expira_em"])
    except Exception:
        return None
    return (expira - datetime.now(timezone.utc)).days


def main() -> None:
    token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    if not token:
        sys.exit("Defina IG_ACCESS_TOKEN com o token atual.")

    restam = dias_restantes()
    if restam is not None:
        print(f"Pelo último registro, faltavam {restam} dias.")

    r = requests.get(f"{GRAPH}/refresh_access_token", params={
        "grant_type": "ig_refresh_token", "access_token": token}, timeout=30)
    j = r.json()
    novo = j.get("access_token")
    if not novo:
        erro = str((j.get("error") or {}).get("message", j))
        if "24 hours" in erro or "24 horas" in erro:
            # a Meta só renova token com mais de 24 h de vida; recém-gerado,
            # não há o que consertar — a rodada da semana que vem resolve
            print(f"Token novo demais para renovar ({erro}). Sem problema.")
            return
        if restam is not None and restam > ALERTA_DIAS:
            print(f"Não renovou desta vez ({erro}), mas ainda faltam {restam} "
                  f"dias — sem urgência. Tentativa nova na próxima rodada.")
            return
        sys.exit(f"FALHA AO RENOVAR e o prazo está curto: {erro}")

    dias = int(j.get("expires_in", 0)) // 86400
    print(f"Token renovado: válido por mais ~{dias} dias.")

    pat = os.environ.get("REPO_PAT", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if pat and repo:
        env = dict(os.environ, GH_TOKEN=pat)
        subprocess.run(["gh", "secret", "set", "IG_ACCESS_TOKEN",
                        "--repo", repo, "--body", novo], env=env, check=True)
        print("Secret IG_ACCESS_TOKEN atualizado no repositório.")
        gravar_registro(dias)
    elif os.environ.get("GITHUB_ACTIONS") == "true":
        sys.exit(
            "Renovou, mas SEM REPO_PAT não dá para gravar o secret — e "
            "imprimir o token novo aqui o publicaria no log deste repositório "
            "público.\nCadastre um PAT em REPO_PAT (permissão Secrets: Read "
            "and write) para isto virar automático, ou renove pelo PC:\n"
            "    IG_ACCESS_TOKEN=<atual> python refresh_token.py")
    else:
        gravar_registro(dias)
        print("\nCole este valor no secret IG_ACCESS_TOKEN do repositório:\n")
        print(novo)


if __name__ == "__main__":
    main()
