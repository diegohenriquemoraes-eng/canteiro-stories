import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import carrossel_viral as cv  # noqa: E402

LEGENDA = """“Se fechar hoje eu faço desconto”

Essa frase ensina o cliente a esperar

Se for dar condição, troca por alguma coisa:

1. Pagamento à vista
2. Entrada maior

Desconto sem troca é margem jogada fora

Pegou a visão?

Teu vendedor oferece desconto antes do cliente pedir?

Comenta MARGEM que eu te mando a lista de trocas

Siga o @vendanaobra

Desenvolvo empresas da construção a vender mais e de forma previsível

#desconto #margem"""


class SlidesDaLegenda(unittest.TestCase):
    def test_roteiro_vira_slides_e_fecha_com_a_palavra(self):
        slides, palavra = cv.slides_da_legenda(LEGENDA)
        self.assertEqual(palavra, "MARGEM")
        self.assertEqual(slides[0], "“Se fechar hoje eu faço desconto”")
        self.assertIn("1. Pagamento à vista\n2. Entrada maior", slides)
        self.assertTrue(slides[-1].startswith("Teu vendedor oferece desconto"))
        self.assertTrue(slides[-1].endswith("Comenta MARGEM que eu te mando o roteiro"))
        texto = "\n".join(slides)
        for fora in ("Pegou a visão", "Siga o @", "Desenvolvo empresas", "#desconto"):
            self.assertNotIn(fora, texto)

    def test_teto_de_slides(self):
        longa = "\n\n".join(f"Frase número {i} do roteiro" for i in range(30)) + "\n\nPegou a visão?\n\nE aí?"
        slides, _ = cv.slides_da_legenda(longa)
        self.assertLessEqual(len(slides), cv.MAX_SLIDES)

    def test_legenda_do_carrossel_difere_da_do_reel(self):
        c = cv.montar({"id": "1", "views": 3000, "caption": LEGENDA}, "2026-10-20", "Ter")
        self.assertNotEqual(c["legenda"], LEGENDA)
        self.assertIn(cv.ABERTURA, c["legenda"])
        self.assertEqual(c["hora"], "12:30")


if __name__ == "__main__":
    unittest.main()
