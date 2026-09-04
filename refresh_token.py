"""Renova o token de longa duração do Instagram (dura ~60 dias).

O token de longa duração da 'Instagram API with Instagram Login' expira em 60
dias. Este script troca o token atual por um novo (válido por mais 60 dias) e
imprime o resultado. Rode a cada ~50 dias — ou deixe o workflow mensal fazer.

Uso:
    IG_ACCESS_TOKEN=<token atual> python refresh_token.py

Se um PAT com permissão de escrever Secrets estiver em REPO_PAT (e GITHUB_
REPOSITORY definido), o script atualiza o secret IG_ACCESS_TOKEN sozinho via
gh; senão, imprime o token novo para você colar no secret À MÃO.

ATENÇÃO: rodando dentro do GitHub Actions o token NUNCA é impresso. O
repositório é público, o log do Actions também é, e o token recém-gerado não
existe na lista de secrets — então o mascaramento automático não o cobriria.
Lá, sem REPO_PAT, o script falha pedindo a renovação manual.

Alternativa sem validade: um token de System User de um Portfólio Comercial
(Business) NÃO expira — se você criar um, esqueça este script.
"""

from __future__ import annotations

import os
import subprocess
import sys

import requests

GRAPH = "https://graph.instagram.com"


def main() -> None:
    token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    if not token:
        sys.exit("Defina IG_ACCESS_TOKEN com o token atual.")
    r = requests.get(f"{GRAPH}/refresh_access_token", params={
        "grant_type": "ig_refresh_token", "access_token": token}, timeout=30)
    j = r.json()
    novo = j.get("access_token")
    if not novo:
        sys.exit(f"Falha ao renovar: {j}")
    dias = int(j.get("expires_in", 0)) // 86400
    print(f"Novo token válido por ~{dias} dias.")

    pat = os.environ.get("REPO_PAT", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if pat and repo:
        env = dict(os.environ, GH_TOKEN=pat)
        subprocess.run(["gh", "secret", "set", "IG_ACCESS_TOKEN",
                        "--repo", repo, "--body", novo], env=env, check=True)
        print("Secret IG_ACCESS_TOKEN atualizado no repositório.")
    else:
        print("\nCole este valor no secret IG_ACCESS_TOKEN do repositório:\n")
        print(novo)


if __name__ == "__main__":
    main()
