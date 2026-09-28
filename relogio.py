"""Relogio: dispara os workflows no horario certo, sem depender do cron do GitHub.

O cron do GitHub e "quando der": em 28/09/2026 ele engoliu TODAS as janelas do
dia dos distribuidores (10h-16h BRT) e os seis disparos do carrossel. O vigia
dos Stories, que fica acordado 5h50 por disparo, nao sentiu. Este script e o
mesmo truque para o resto: fica acordado e, a cada minuto, confere a tabela de
horarios; horario vencido sem execucao desde entao -> `gh workflow run`.

Tabela em RELOGIO_SLOTS (JSON): [{"hora": "10:17", "workflow": "distribuir.yml",
"inputs": {"limite": "2"}}, ...], horas em Brasilia. Disparo na mao
(workflow_dispatch) e aceito por GitHub mesmo vindo do GITHUB_TOKEN.

Uso: python relogio.py --minutos 350 [--ensaio]
"""
import argparse
import json
import os
import subprocess
import time
from datetime import datetime, timedelta, timezone

FUSO = timezone(timedelta(hours=-3))
TOLERANCIA_MIN = 100  # depois disso a janela seguinte cobre


def log(msg: str) -> None:
    print(f"[{datetime.now(FUSO):%H:%M}] {msg}", flush=True)


def ja_rodou(workflow: str, desde: datetime) -> bool:
    """Alguma execucao (qualquer evento) criada desde o horario da janela?"""
    desde_utc = desde.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = subprocess.run(
        ["gh", "run", "list", "-w", workflow, "-L", "20",
         "--json", "createdAt", "-q", ".[].createdAt"],
        capture_output=True, text=True, check=True).stdout.split()
    return any(c >= desde_utc for c in out)


def disparar(workflow: str, inputs: dict, ensaio: bool) -> None:
    cmd = ["gh", "workflow", "run", workflow]
    for k, v in inputs.items():
        cmd += ["-f", f"{k}={v}"]
    if ensaio:
        log(f"[ensaio] {' '.join(cmd)}")
        return
    subprocess.run(cmd, check=True)
    log(f"disparado: {workflow} {inputs or ''}")


def passada(slots: list, ensaio: bool, feitos: set) -> None:
    agora = datetime.now(FUSO)
    for s in slots:
        h, m = map(int, s["hora"].split(":"))
        alvo = agora.replace(hour=h, minute=m, second=0, microsecond=0)
        chave = (alvo.date().isoformat(), s["hora"], s["workflow"])
        if chave in feitos or not (alvo <= agora < alvo + timedelta(minutes=TOLERANCIA_MIN)):
            continue
        try:
            if ja_rodou(s["workflow"], alvo):
                log(f"{s['hora']} {s['workflow']}: ja rodou desde a hora")
            else:
                disparar(s["workflow"], s.get("inputs", {}), ensaio)
            feitos.add(chave)
        except subprocess.CalledProcessError as e:
            log(f"{s['hora']} {s['workflow']}: falhou ({e}); tento no proximo minuto")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutos", type=int, default=0, help="0 = uma passada so")
    ap.add_argument("--ensaio", action="store_true")
    args = ap.parse_args()
    slots = json.loads(os.environ["RELOGIO_SLOTS"])
    fim = time.time() + args.minutos * 60
    feitos: set = set()
    while True:
        passada(slots, args.ensaio, feitos)
        if time.time() >= fim:
            break
        time.sleep(60)


if __name__ == "__main__":
    main()
