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


if __name__ == "__main__":
    unittest.main()
