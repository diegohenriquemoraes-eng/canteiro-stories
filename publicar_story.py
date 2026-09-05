"""Publica no Story do Instagram o que estiver vencido na fila.

Roda no GitHub Actions de 10 em 10 minutos. Em execução sem nada devido sai
antes de qualquer chamada de API: custa um minuto de runner (ilimitado em repo
público) e zero cota do Instagram.

O caminho de um arquivo:

    Release `fila`  ->  baixa  ->  normaliza (midia.py)  ->  Release `pronto`
                    ->  POST /media (STORIES)  ->  /media_publish
                    ->  apaga os dois assets  ->  grava o estado

Segredos (Secrets do repositório):
  IG_USER_ID       - id de graph.instagram.com/me da conta profissional
  IG_ACCESS_TOKEN  - token de longa duração com instagram_business_content_publish

Sem os secrets o script não quebra: lê a fila, diz o que faria e sai — dá para
testar a esteira inteira antes de existir token.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
sys.stdout.reconfigure(encoding="utf-8")

import fila as filamod        # noqa: E402
import midia                  # noqa: E402

CONFIG = AQUI / "config.json"
STATE = AQUI / "state.json"
REGISTRO = AQUI / "publicados.md"
TRABALHO = AQUI / "saida"
GRAPH = "https://graph.instagram.com"


def log(msg: str) -> None:
    # o repositório é público e o log do Actions também: mensagem de erro do
    # requests carrega a URL inteira, e nos GET o token vai na query string
    texto = str(msg)
    for chave in ("IG_ACCESS_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
        segredo = os.environ.get(chave, "").strip()
        if len(segredo) > 8:
            texto = texto.replace(segredo, "***")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {texto}", flush=True)


def carregar(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def gravar(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def estado() -> dict:
    st = carregar(STATE, {})
    st.setdefault("publicados", {})
    st.setdefault("ignorados", [])
    st.setdefault("dia", {"data": "", "n": 0})
    return st


# ------------------------------------------------------------ Instagram ----

def descobrir_ig_id(token: str) -> str:
    """O id da conta sai do próprio token — não precisa ser cadastrado à mão.

    E não é o número que o painel da Meta mostra (17841...), é o de
    graph.instagram.com/me: confundir os dois foi o que fez o pipeline dos
    Reels falhar em silêncio quando foi ligado.
    """
    r = requests.get(f"{GRAPH}/me", params={"fields": "id,username",
                                            "access_token": token}, timeout=30)
    j = r.json()
    if "id" not in j:
        raise SystemExit(f"o token não respondeu quem é a conta: {j}")
    log(f"conta do token: @{j.get('username', '?')} (id {j['id']})")
    return j["id"]


def dentro_do_limite(ig_id: str, token: str) -> bool:
    try:
        r = requests.get(f"{GRAPH}/{ig_id}/content_publishing_limit",
                         params={"fields": "quota_usage,config",
                                 "access_token": token}, timeout=30)
        d = (r.json().get("data") or [{}])[0]
        uso = d.get("quota_usage", 0)
        teto = (d.get("config") or {}).get("quota_total", 100)
        log(f"cota do Instagram: {uso}/{teto} publicações nas últimas 24 h")
        return uso < teto
    except Exception as exc:
        log(f"não consegui ler a cota ({exc}); seguindo")
        return True


def publicar_story(ig_id: str, token: str, url: str, eh_video: bool) -> str:
    dados = {"media_type": "STORIES", "access_token": token}
    dados["video_url" if eh_video else "image_url"] = url
    j = requests.post(f"{GRAPH}/{ig_id}/media", data=dados, timeout=120).json()
    if "id" not in j:
        raise SystemExit(f"falha ao criar o container: {j}")
    creation_id = j["id"]

    # o Instagram vai buscar a URL e transcodifica; publicar antes de FINISHED
    # devolve erro genérico que não diz o que houve
    limite = 60 if eh_video else 12          # ~10 min de vídeo, ~2 min de foto
    for tentativa in range(limite):
        s = requests.get(f"{GRAPH}/{creation_id}",
                         params={"fields": "status_code,status",
                                 "access_token": token}, timeout=30).json()
        code = s.get("status_code")
        if code == "FINISHED":
            break
        if code == "ERROR":
            raise SystemExit(f"o Instagram recusou a mídia: {s}")
        if code is None and tentativa >= 2:
            break                            # conta que não expõe status
        time.sleep(10)
    else:
        raise SystemExit("tempo esgotado esperando o Instagram processar")

    p = requests.post(f"{GRAPH}/{ig_id}/media_publish",
                      data={"creation_id": creation_id,
                            "access_token": token}, timeout=60).json()
    if "id" not in p:
        raise SystemExit(f"falha no media_publish: {p}")
    return p["id"]


def registrar(nome: str, alvo: datetime, media_ids: list[str], info: dict,
              falha: str = "") -> None:
    with REGISTRO.open("a", encoding="utf-8") as fh:
        fh.write(f"\n## {alvo:%d/%m/%Y %H:%M} — {nome}\n\n"
                 f"- Tipo: {info['tipo']}"
                 + (f" ({info['duracao_s']}s)" if info["duracao_s"] else "") + "\n"
                 f"- Stories: {', '.join(media_ids)}\n"
                 f"- Publicado em: {datetime.now().isoformat(timespec='seconds')}\n"
                 + (f"- FALHOU: {falha}\n" if falha else ""))


# ------------------------------------------------------------------ main ---

def rodada(args) -> None:
    """Uma passada pela fila: publica o que estiver vencido e volta."""
    cfg = carregar(CONFIG, None)
    if cfg is None:
        raise SystemExit(f"config ausente: {CONFIG}")

    if args.local:
        origem = Path(args.local).expanduser().resolve()
        res = midia.preparar(origem, TRABALHO / "teste", origem.stem, cfg["video"])
        for a in res["arquivos"]:
            log(f"{a} ({a.stat().st_size / 1e6:.1f} MB)")
        return

    tz = ZoneInfo(cfg["fuso"])
    agora = datetime.now(tz)
    hoje = agora.date().isoformat()
    st = estado()
    if st["dia"]["data"] != hoje:
        st["dia"] = {"data": hoje, "n": 0}

    # o prazo do token está anotado em token.json (sem segredo nenhum): dá
    # para avisar cedo, em vez de descobrir no dia em que o story não sai
    try:
        import refresh_token
        faltam = refresh_token.dias_restantes()
        if faltam is not None and faltam <= refresh_token.ALERTA_DIAS:
            log(f"ATENÇÃO: o token do Instagram vence em {faltam} dias e a "
                f"renovação semanal não está pegando. Ver o workflow "
                f"'Renovar token'.")
    except Exception:
        pass

    if args.dry_run:
        # o diagnóstico da credencial vem ANTES da fila: fila vazia é o caso
        # mais comum de rodar isto, e sair antes de testar o token seria
        # justamente falhar no que o dry-run existe para responder
        tok = os.environ.get("IG_ACCESS_TOKEN", "").strip()
        if tok:
            dentro_do_limite(os.environ.get("IG_USER_ID", "").strip()
                             or descobrir_ig_id(tok), tok)
        else:
            log("[dry-run] sem IG_ACCESS_TOKEN: não dá para conferir a conta")

    repo = filamod.Repo()
    # duas portas de entrada: a página de envio grava na branch `entrada`
    # (é a que o Diego usa) e a Release `fila` continua valendo para quem
    # preferir anexar o arquivo direto, já com o horário no nome
    assets = [dict(a, origem="release") for a in repo.assets(cfg["release_fila"])]
    assets += repo.entrada_listar()
    # arquivo grande sobe fatiado (a API de blobs recusa acima de ~35 MB):
    # junta os pedaços de volta antes de qualquer decisão sobre a fila
    assets, incompletos = filamod.juntar_partes(assets)
    for pendente in incompletos:
        log(f"envio em partes ainda incompleto, esperando: {pendente}")
    if not assets:
        log("fila vazia — nada a publicar")
        return

    devidos, futuros, sem_horario = [], [], []
    for a in assets:
        if Path(a["name"]).suffix.lower() not in cfg["extensoes"]:
            continue
        alvo = filamod.alvo_do_nome(a["name"], agora, cfg["atraso_max_min"])
        if alvo is None:
            sem_horario.append(a["name"])
            continue
        chave = f"{alvo.date().isoformat()}|{a['name']}"
        if chave in st["publicados"]:
            continue
        (devidos if alvo <= agora else futuros).append((alvo, a["name"], a, chave))

    devidos.sort(key=lambda t: (t[0], t[1]))
    futuros.sort(key=lambda t: (t[0], t[1]))

    for nome in sem_horario:
        if nome not in st["ignorados"]:
            st["ignorados"] = (st["ignorados"] + [nome])[-50:]
            log(f"IGNORADO (nome não começa com o horário): {nome}")
    for alvo, nome, *_ in futuros:
        log(f"agendado para {alvo:%d/%m %H:%M}: {nome}")

    # acordou ANTES da hora e o proximo esta' logo ali: espera e publica no
    # minuto certo. E' o que faz o horario do app valer, mesmo com o cron do
    # GitHub chegando quando quer.
    espera_max = cfg.get("esperar_ate_min", 0)
    if not devidos and futuros and espera_max and not args.dry_run:
        alvo_prox, nome_prox, *_ = futuros[0]
        faltam = (alvo_prox - agora).total_seconds()
        if 0 < faltam <= espera_max * 60:
            log(f"esperando {faltam/60:.0f} min até {alvo_prox:%H:%M} para publicar "
                f"na hora certa: {nome_prox}")
            time.sleep(faltam)
            agora = datetime.now(tz)
            devidos = [futuros.pop(0)]

    if not devidos and not args.forcar:
        log(f"nada vencido às {agora:%H:%M} — {len(futuros)} na fila")
        gravar(STATE, st)
        return
    if args.forcar and not devidos and futuros:
        devidos = [futuros[0]]

    resta_hoje = max(0, cfg["cap_diario"] - st["dia"]["n"])
    if resta_hoje <= 0:
        log(f"teto diário de {cfg['cap_diario']} Stories já atingido; segurando")
        gravar(STATE, st)
        return
    devidos = devidos[:cfg["max_por_execucao"]]

    if args.dry_run:
        for alvo, nome, *_ in devidos:
            log(f"[dry-run] publicaria agora ({alvo:%H:%M}): {nome}")
        return

    ig_id = os.environ.get("IG_USER_ID", "").strip()
    token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    if not args.render_apenas and not token:
        log("SEM IG_ACCESS_TOKEN nos secrets — a fila está lida e correta, "
            "mas não há como publicar. Ver README.md.")
        for alvo, nome, *_ in devidos:
            log(f"  publicaria agora: {nome}")
        return
    if token and not ig_id and not args.render_apenas:
        ig_id = descobrir_ig_id(token)

    if not args.render_apenas and not dentro_do_limite(ig_id, token):
        log("cota de publicação esgotada nas últimas 24 h; segurando a fila")
        return

    for alvo, nome, asset, chave in devidos:
        log(f"preparando {nome} (era para {alvo:%d/%m %H:%M})")
        try:
            if asset["origem"] == "release":
                bruto = repo.baixar(asset, TRABALHO / "bruto" / nome)
            elif asset["origem"] == "partes":
                log(f"  remontando de {len(asset['partes'])} pedaços e conferindo o sha256")
                bruto = filamod.baixar_montado(repo, asset, TRABALHO / "bruto" / nome)
            else:
                bruto = repo.entrada_baixar(asset, TRABALHO / "bruto" / nome)
        except filamod.FilaErro as exc:
            # remontagem que nao confere: fica na fila, nao publica pela metade
            log(f"NAO CONFERE, deixando na fila: {exc}")
            continue
        base = f"{alvo:%Y%m%d-%H%M}-{Path(nome).stem[:40]}"
        try:
            res = midia.preparar(bruto, TRABALHO / "pronto", base, cfg["video"])
        except midia.MidiaInvalida as exc:
            log(f"ARQUIVO RUIM, pulando: {nome} — {exc}")
            st["ignorados"].append(f"{nome} ({exc})")
            continue

        partes = res["arquivos"][:resta_hoje]
        if not partes:
            # teto diário no fim do arquivo: segura para a próxima execução em
            # vez de marcar como publicado sem ter publicado nada
            log("  teto diário atingido; este fica para a próxima rodada")
            break
        if len(partes) < len(res["arquivos"]):
            log(f"  teto diário corta o vídeo em {len(partes)} de "
                f"{len(res['arquivos'])} partes")
        log(f"  {res['tipo']}, {len(partes)} story(s)"
            + (f", {res['duracao_s']}s no total" if res["duracao_s"] else ""))

        if args.render_apenas:
            for p in partes:
                log(f"  [render-apenas] {p}")
            continue

        media_ids, enviados, falha = [], [], ""
        for i, arquivo in enumerate(partes, 1):
            sufixo = f"-p{i}" if len(partes) > 1 else ""
            nome_asset = f"{base}{sufixo}{arquivo.suffix}"
            try:
                url = repo.subir(cfg["release_pronto"], arquivo, nome_asset)
                enviados.append(nome_asset)
                log(f"  subindo parte {i}/{len(partes)}")
                media_ids.append(publicar_story(
                    ig_id, token, url, arquivo.suffix.lower() == ".mp4"))
                log(f"  no ar: {media_ids[-1]}")
            except (SystemExit, filamod.FilaErro, requests.RequestException) as exc:
                # com parte já no ar, repetir o arquivo inteiro na próxima
                # rodada duplicaria o que foi publicado: perder a parte que
                # faltou é o erro mais barato
                falha = f"parte {i}/{len(partes)}: {exc}"
                log(f"  FALHOU na {falha}")
                break

        if not media_ids:
            log(f"  nada publicado de {nome}; fica na fila para a próxima")
            for a in repo.assets(cfg["release_pronto"]):
                if a["name"] in enviados:
                    repo.apagar(a["id"])
            continue

        st["publicados"][chave] = {
            "quando": datetime.now(tz).isoformat(timespec="seconds"),
            "alvo": alvo.isoformat(timespec="minutes"),
            "media_ids": media_ids,
        }
        st["dia"]["n"] += len(media_ids)
        resta_hoje -= len(media_ids)
        registrar(nome, alvo, media_ids, res, falha)
        gravar(STATE, st)

        if asset["origem"] == "release":               # sai da caixa de entrada
            repo.apagar(asset["id"])
        elif asset["origem"] == "partes":              # os pedaços e o manifesto
            repo.entrada_remover({p["name"] for p in asset["partes"]}
                                 | {asset["manifesto"]["name"]})
        else:
            repo.entrada_remover({asset["name"]})
        for a in repo.assets(cfg["release_pronto"]):   # e da hospedagem
            if a["name"] in enviados:
                repo.apagar(a["id"])
        log(f"  {nome}: publicado e removido da fila")

    gravar(STATE, st)


def main() -> None:
    ap = argparse.ArgumentParser(description="Publica o Story devido agora")
    ap.add_argument("--dry-run", action="store_true",
                    help="mostra a fila e o que publicaria; não toca em nada")
    ap.add_argument("--render-apenas", action="store_true",
                    help="baixa e normaliza sem publicar (não precisa de token)")
    ap.add_argument("--forcar", action="store_true",
                    help="ignora o horário e publica o primeiro da fila")
    ap.add_argument("--local", metavar="ARQUIVO",
                    help="só testa a normalização de um arquivo do PC")
    ap.add_argument("--vigia", type=int, metavar="MIN", default=0,
                    help="fica acordado por MIN minutos, olhando a fila de minuto "
                         "em minuto (é assim que o horário do app é cumprido)")
    args = ap.parse_args()

    if not args.vigia:
        rodada(args)
        return

    # VIGIA: o job não morre entre uma checagem e outra, então o horário
    # marcado no app é cumprido mesmo quando o cron do GitHub some por horas.
    fim = time.monotonic() + args.vigia * 60
    log(f"vigia ligado por {args.vigia} min — olhando a fila de minuto em minuto")
    n = 0
    while time.monotonic() < fim:
        n += 1
        try:
            rodada(args)
        except SystemExit as e:          # config ausente e afins: não insiste
            log(f"vigia parou: {e}")
            return
        except Exception as e:           # falha de rede não pode derrubar o dia
            log(f"passada {n} falhou ({type(e).__name__}: {e}); segue vigiando")
        restam = fim - time.monotonic()
        if restam <= 0:
            break
        time.sleep(min(60, restam))
    log(f"vigia encerrado depois de {n} passadas")


if __name__ == "__main__":
    main()
