import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import carrossel  # noqa: E402


class TestCarrossel(unittest.TestCase):
    def test_json_do_app_tem_o_que_o_robo_precisa(self):
        dados = json.loads(carrossel.DADOS.read_text(encoding="utf-8"))
        self.assertTrue(dados)
        for c in dados:
            self.assertRegex(c["hora"], r"^\d\d:\d\d$")
            self.assertTrue(2 <= len(c["slides"]) <= 10, c["dia"])   # limite da API
            self.assertLessEqual(len(c["legenda"]), 2200, c["dia"])  # limite do IG

    def test_alvo_e_chave(self):
        c = {"dia": "2026-09-27", "hora": "12:30", "n": 1}
        self.assertEqual(carrossel.alvo_de(c).strftime("%Y-%m-%d %H:%M"), "2026-09-27 12:30")
        self.assertEqual(carrossel.chave(c), "2026-09-27|1")

    def test_desenho_no_formato_do_feed(self):
        im = carrossel.desenhar("Uma frase de teste com número 10% e “aspas”.", 1, 8)
        self.assertEqual(im.size, (1080, 1350))
        capa = carrossel.desenhar(" ".join(["palavra"] * 60), 0, 8)  # encolhe sem quebrar
        self.assertEqual(capa.size, (1080, 1350))


if __name__ == "__main__":
    unittest.main()
