# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from carrossel import CTA_BIO, garantir_cta  # noqa: E402


class TestCta(unittest.TestCase):
    def test_troca_arroba_solto(self):
        t = "Texto.\n\nPergunta?\n@vendanaobra\n\n#vendas #obra"
        self.assertEqual(garantir_cta(t),
                         "Texto.\n\nPergunta?\n\n" + CTA_BIO + "\n\n#vendas #obra")

    def test_ja_tem_cta_nao_mexe(self):
        t = "Pergunta?\n\n" + CTA_BIO + "\n\n#vendas"
        self.assertEqual(garantir_cta(t), t)

    def test_sem_arroba_entra_antes_das_hashtags(self):
        self.assertEqual(garantir_cta("Pergunta?\n\n#vendas"),
                         "Pergunta?\n\n" + CTA_BIO + "\n\n#vendas")

    def test_sem_hashtag(self):
        self.assertEqual(garantir_cta("Pergunta?"), "Pergunta?\n\n" + CTA_BIO)


class TestSemPontoFinal(unittest.TestCase):
    def test_frases_viram_blocos_sem_ponto(self):
        from carrossel import sem_ponto_final
        t = "O cliente não sumiu. Ninguém ligou.\n\nQual é o seu?"
        self.assertEqual(sem_ponto_final(t),
                         "O cliente não sumiu\n\nNinguém ligou\n\nQual é o seu?")

    def test_lista_numerada_e_reticencias_ficam(self):
        from carrossel import sem_ponto_final
        t = "1. Pergunte antes.\n2. Espere...\n\nR$ 3,5 mil."
        self.assertEqual(sem_ponto_final(t), "1. Pergunte antes\n2. Espere...\n\nR$ 3,5 mil")

    def test_cta_da_bio_quebra_em_duas_linhas(self):
        from carrossel import sem_ponto_final
        self.assertEqual(sem_ponto_final(CTA_BIO),
                         "Siga o @vendanaobra\n\nDesenvolvo empresas da construção a vender "
                         "mais e de forma previsível")


if __name__ == "__main__":
    unittest.main()
