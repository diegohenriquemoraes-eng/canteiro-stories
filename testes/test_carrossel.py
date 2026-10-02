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

    def test_sem_travessao_nem_ponto_e_virgula(self):
        # pedido do Diego, 27/09/2026: pontuação de mercado no texto de slide e legenda
        dados = json.loads(carrossel.DADOS.read_text(encoding="utf-8"))
        for c in dados:
            if c["dia"] < "2026-09-28":
                continue
            for texto in c["slides"] + [c["legenda"]]:
                self.assertNotRegex(texto, "[—–;]", c["dia"])
        self.assertEqual(carrossel.sem_pontuacao_pesada("Tudo é da empresa — se escrito; ok"),
                         "Tudo é da empresa, se escrito. Ok")
        self.assertEqual(carrossel.sem_pontuacao_pesada("lembrar;\n— item"), "lembrar\n· item")
        self.assertEqual(carrossel.sem_pontuacao_pesada("de 2–7 dias"), "de 2 a 7 dias")

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


class TesteCapaAB(unittest.TestCase):
    def test_alterna_a_partir_de_02_10(self):
        self.assertEqual(carrossel.variante_capa("2026-10-01"), "tipografica")
        self.assertEqual(carrossel.variante_capa("2026-10-02"), "tweet")
        self.assertEqual(carrossel.variante_capa("2026-10-03"), "tipografica")
        self.assertEqual(carrossel.variante_capa("2026-10-04"), "tweet")

    def test_capa_tweet_desenha_com_e_sem_numero(self):
        for nums in ([], [{"num": "24 de 38", "rot": "x"}],
                     [{"num": "10%", "rot": "a"}, {"num": "21%", "rot": "b"}]):
            im = carrossel.desenhar_capa_tweet("Uma frase\n\nOutra frase", nums)
            self.assertEqual(im.size, (carrossel.L, carrossel.A))
