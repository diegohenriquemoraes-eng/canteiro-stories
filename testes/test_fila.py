"""O nome do arquivo é o agendamento — então o parser é a peça crítica.

Um erro aqui não dá erro nenhum: publica no horário errado, ou some com o
Story do dia por não reconhecer o nome. Roda sem rede.
"""

import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fila import alvo_do_nome  # noqa: E402

TZ = ZoneInfo("America/Sao_Paulo")
MANHA = datetime(2026, 9, 4, 8, 0, tzinfo=TZ)      # o Diego montando a pauta
TARDE = datetime(2026, 9, 4, 14, 0, tzinfo=TZ)
ATRASO = 90


class Horario(unittest.TestCase):

    def test_formatos_que_o_diego_vai_digitar(self):
        for nome, (h, m) in {
            "0930-fundacao.jpg": (9, 30),
            "0930 fundacao.jpg": (9, 30),
            "0930.jpg": (9, 30),
            "930-concreto.mp4": (9, 30),
            "09h30-laje.jpg": (9, 30),
            "09-30-laje.jpg": (9, 30),
            "1500-entrega.mp4": (15, 0),
            "2359-final.jpg": (23, 59),
        }.items():
            with self.subTest(nome=nome):
                alvo = alvo_do_nome(nome, MANHA, ATRASO)
                self.assertIsNotNone(alvo, f"{nome} devia ser reconhecido")
                self.assertEqual((alvo.hour, alvo.minute), (h, m))
                self.assertEqual(alvo.date(), MANHA.date())

    def test_data_no_nome_fixa_o_dia(self):
        for nome in ("2026-09-06-0930-laje.jpg", "20260906-0930-laje.jpg"):
            with self.subTest(nome=nome):
                alvo = alvo_do_nome(nome, MANHA, ATRASO)
                self.assertEqual(alvo.date(), datetime(2026, 9, 6).date())
                self.assertEqual((alvo.hour, alvo.minute), (9, 30))

    def test_nome_sem_horario_e_ignorado(self):
        # foto direto da galeria: publicar isso "agora" seria pior que ignorar
        for nome in ("IMG_20260904_093012.jpg", "foto da obra.jpg",
                     "WhatsApp Image 2026-09-04.jpeg", "video.mp4"):
            with self.subTest(nome=nome):
                self.assertIsNone(alvo_do_nome(nome, MANHA, ATRASO))

    def test_hora_impossivel_nao_vira_horario(self):
        for nome in ("2599-x.jpg", "0975-x.jpg"):
            with self.subTest(nome=nome):
                self.assertIsNone(alvo_do_nome(nome, MANHA, ATRASO))

    def test_atraso_curto_ainda_e_hoje(self):
        # cron do GitHub atrasa; 08:00 com alvo 07:00 tem de sair hoje mesmo
        alvo = alvo_do_nome("0700-x.jpg", MANHA, ATRASO)
        self.assertEqual(alvo.date(), MANHA.date())
        self.assertLess(alvo, MANHA)

    def test_atraso_longo_vira_amanha(self):
        # subir "0800" às duas da tarde quer dizer amanhã, não agora
        alvo = alvo_do_nome("0800-x.jpg", TARDE, ATRASO)
        self.assertEqual(alvo.date(), datetime(2026, 9, 5).date())

    def test_futuro_do_mesmo_dia(self):
        alvo = alvo_do_nome("1600-x.jpg", TARDE, ATRASO)
        self.assertEqual(alvo.date(), TARDE.date())
        self.assertGreater(alvo, TARDE)

    def test_nome_que_a_pagina_de_envio_monta(self):
        """O contrato entre as duas metades do projeto.

        A página (docs/index.html) monta `AAAA-MM-DD-HHMM-slug.ext` a partir do
        seletor de dia e hora. Se este formato deixar de ser entendido aqui, o
        Story não é publicado com horário errado — ele é ignorado em silêncio.
        """
        for nome, (dia, h, m) in {
            "2026-09-05-0930-fundacao.jpg": (5, 9, 30),
            "2026-09-05-1415-concretagem-do-radier.mp4": (5, 14, 15),
            "2026-09-05-0930-fundacao-2.jpg": (5, 9, 30),   # dois no mesmo horário
            "2026-09-05-0000-virada.jpg": (5, 0, 0),
            "2026-09-05-2345-fim-do-dia.jpg": (5, 23, 45),
            "2026-09-05-1200-story.jpg": (5, 12, 0),        # nome sem letras vira "story"
        }.items():
            with self.subTest(nome=nome):
                alvo = alvo_do_nome(nome, MANHA, ATRASO)
                self.assertIsNotNone(alvo, f"{nome} devia ser reconhecido")
                self.assertEqual((alvo.day, alvo.hour, alvo.minute), (dia, h, m))

    def test_ordem_de_publicacao_segue_o_relogio(self):
        nomes = ["1500-c.jpg", "0930-a.jpg", "1130-b.jpg"]
        alvos = [(alvo_do_nome(n, MANHA, ATRASO), n) for n in nomes]
        self.assertEqual([n for _, n in sorted(alvos)],
                         ["0930-a.jpg", "1130-b.jpg", "1500-c.jpg"])


if __name__ == "__main__":
    unittest.main()
