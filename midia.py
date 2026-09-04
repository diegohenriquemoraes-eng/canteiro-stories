"""Normaliza o que sai do celular no que o Instagram aceita como Story.

O Diego fotografa e filma na obra: chega arquivo 4:3, foto deitada, HEIC de
iPhone, vídeo de 3 minutos, clipe de 2 segundos. A API de Stories é exigente
(JPEG até 8 MB; vídeo de 3 a 60 s, 9:16 recomendado) e devolve erro seco
quando o arquivo não serve — então o arquivo é consertado ANTES de subir, e
não se pede nada ao Diego.

Enquadramento: a mídia inteira cabe no centro (nunca corta a obra) sobre um
fundo desfocado dela mesma — em vez das barras pretas que denunciam repost.
O desfoque é feito em 135x240 e só depois ampliado: borrar em tamanho cheio
custa caro no runner de 2 núcleos e o resultado na tela é o mesmo.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

L, A = 1080, 1920           # o Story é 1080x1920
IMAGEM = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".bmp", ".gif"}
VIDEO = {".mp4", ".mov", ".m4v", ".3gp", ".avi", ".mkv", ".webm"}

# split -> [fundo] cobre e borra; [frente] cabe inteiro; overlay centraliza.
ENQUADRAR = (
    "[0:v]split=2[bg][fg];"
    f"[bg]scale=135:240:force_original_aspect_ratio=increase,crop=135:240,"
    f"gblur=sigma=6,scale={L}:{A}[bgb];"
    f"[fg]scale={L}:{A}:force_original_aspect_ratio=decrease[fgs];"
    "[bgb][fgs]overlay=(W-w)/2:(H-h)/2,format=yuv420p[vout]"
)


class MidiaInvalida(Exception):
    """Arquivo que não dá para consertar (corrompido, formato desconhecido)."""


def tipo(arquivo: Path) -> str:
    ext = arquivo.suffix.lower()
    if ext in IMAGEM:
        return "imagem"
    if ext in VIDEO:
        return "video"
    raise MidiaInvalida(f"extensão não suportada: {ext}")


def _run(cmd: list[str]) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        cauda = (r.stderr or "").strip().splitlines()[-4:]
        raise MidiaInvalida(" | ".join(cauda) or "ffmpeg falhou sem mensagem")
    return r.stdout


def sondar(arquivo: Path) -> dict:
    """Duração, dimensões e se tem faixa de áudio."""
    out = _run(["ffprobe", "-v", "error", "-print_format", "json",
                "-show_format", "-show_streams", str(arquivo)])
    d = json.loads(out)
    v = next((s for s in d["streams"] if s.get("codec_type") == "video"), None)
    if v is None:
        raise MidiaInvalida("arquivo sem faixa de vídeo/imagem")
    dur = float(d.get("format", {}).get("duration") or v.get("duration") or 0)
    return {
        "duracao_s": dur,
        "largura": int(v.get("width") or 0),
        "altura": int(v.get("height") or 0),
        "tem_audio": any(s.get("codec_type") == "audio" for s in d["streams"]),
    }


def _heic_para_jpg(origem: Path, destino: Path) -> Path:
    """iPhone entrega HEIC e o ffmpeg do runner não decodifica sem libheif.

    Sem isto o Story do dia morre num erro de codec — que é exatamente o tipo
    de falha que o Diego só descobriria à noite, olhando o perfil vazio.
    """
    from PIL import Image
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except ImportError:
        pass
    with Image.open(origem) as im:
        im.convert("RGB").save(destino, "JPEG", quality=95)
    return destino


def preparar_imagem(origem: Path, destino: Path) -> dict:
    entrada = origem
    if origem.suffix.lower() in {".heic", ".heif"}:
        entrada = _heic_para_jpg(origem, destino.with_suffix(".bruta.jpg"))
    _run(["ffmpeg", "-y", "-v", "error", "-i", str(entrada),
          "-filter_complex", ENQUADRAR, "-map", "[vout]",
          "-q:v", "3", str(destino)])
    if destino.stat().st_size / 1e6 > 8:         # teto duro da API de Stories
        _run(["ffmpeg", "-y", "-v", "error", "-i", str(entrada),
              "-filter_complex", ENQUADRAR, "-map", "[vout]",
              "-q:v", "7", str(destino)])
    return {"tipo": "imagem", "arquivos": [destino], "duracao_s": 0.0}


def _cortar_video(origem: Path, destino: Path, inicio: float,
                  duracao: float, tem_audio: bool) -> None:
    cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{inicio:.3f}",
           "-i", str(origem)]
    if not tem_audio:
        # vídeo mudo às vezes trava o processamento do container; uma faixa
        # silenciosa custa nada e tira a variável do caminho
        cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
    # mapear na mão: com filter_complex e duas entradas, deixar o ffmpeg
    # escolher a faixa de áudio dá silêncio em vídeo que tinha som
    cmd += ["-t", f"{duracao:.3f}", "-filter_complex", ENQUADRAR,
            "-map", "[vout]", "-map", "0:a:0" if tem_audio else "1:a:0",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-maxrate", "8M", "-bufsize", "12M", "-profile:v", "high",
            "-r", "30", "-pix_fmt", "yuv420p",
            # apad em vez de -shortest: no clipe esticado o áudio original é
            # mais curto que o vídeo, e -shortest truncava o Story de volta
            # para o tamanho que a API acabou de recusar
            "-af", "apad", "-c:a", "aac", "-b:a", "128k",
            "-ar", "44100", "-ac", "2",
            "-movflags", "+faststart", str(destino)]
    _run(cmd)


def preparar_video(origem: Path, destino: Path, cfg_video: dict) -> dict:
    info = sondar(origem)
    dur = info["duracao_s"]
    if dur <= 0:
        raise MidiaInvalida("não consegui ler a duração do vídeo")

    max_s = float(cfg_video.get("max_s", 60.0))
    min_s = float(cfg_video.get("min_s", 3.0))

    if dur < min_s:
        # clipe curto demais para a API: congela o último frame até o mínimo
        estendido = destino.with_suffix(".ext.mp4")
        _run(["ffmpeg", "-y", "-v", "error", "-i", str(origem),
              "-vf", f"tpad=stop_mode=clone:stop_duration={min_s - dur + 0.3:.3f}",
              "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
              "-pix_fmt", "yuv420p", str(estendido)])
        # o tpad pode ou não ter carregado o áudio junto: perguntar ao
        # arquivo novo em vez de supor
        origem, dur = estendido, min_s + 0.3
        info["tem_audio"] = sondar(estendido)["tem_audio"]

    if dur <= max_s or not cfg_video.get("dividir_longos", True):
        _cortar_video(origem, destino, 0.0, min(dur, max_s), info["tem_audio"])
        return {"tipo": "video", "arquivos": [destino],
                "duracao_s": round(min(dur, max_s), 1)}

    # Vídeo longo vira partes de 60 s, como o próprio Instagram faria — em vez
    # de cortar aos 60 s e jogar fora o resto do que foi gravado na obra.
    partes, inicio, n = [], 0.0, 0
    while inicio < dur - 0.5:
        pedaco = min(max_s, dur - inicio)
        if pedaco < min_s:                       # sobra curta entra na anterior
            break
        n += 1
        alvo = destino.with_name(f"{destino.stem}-p{n}{destino.suffix}")
        _cortar_video(origem, alvo, inicio, pedaco, info["tem_audio"])
        partes.append(alvo)
        inicio += pedaco
    if not partes:
        raise MidiaInvalida("não consegui dividir o vídeo em partes válidas")
    return {"tipo": "video", "arquivos": partes, "duracao_s": round(dur, 1)}


def preparar(origem: Path, pasta: Path, base: str, cfg_video: dict) -> dict:
    """Devolve {tipo, arquivos: [Path], duracao_s} pronto para subir."""
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise MidiaInvalida("ffmpeg/ffprobe não encontrados no PATH")
    pasta.mkdir(parents=True, exist_ok=True)
    if tipo(origem) == "imagem":
        return preparar_imagem(origem, pasta / f"{base}.jpg")
    return preparar_video(origem, pasta / f"{base}.mp4", cfg_video)
