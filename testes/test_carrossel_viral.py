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
        self.assertEqual(c["hora"], "12:12")


# 06/11/2026: a legenda citava "essa pergunta" e a pergunta só existia na fala do vídeo
LEGENDA_SEM_PERGUNTA = """“Me envia teu preço que já tenho 3 orçamentos”

Se você envia, vira só mais uma empresa pra comparação de preço

Que comparação de preço só ganha quem tem o preço mais baixo e quase nunca é você

Essa pergunta desmonta a objeção do cliente quando ele quer o preço só pra sumir depois

Tá com dificuldade em vendas na construção civil? Siga o @vendanaobra 
#vendas #empreendedorismo #construçãocivil"""

LEGENDA_DO_DIA = """"Me dá um desconto que eu te indico pra todo mundo"

Quando o cliente disser isso, não paga adiantado

O desconto sai hoje, na proposta, e a indicação talvez nunca venha

Eu responderia: "adoro indicação, e quem indica comigo ganha quando o indicado fecha"

1. Para cada indicado que fechar, ele ganha um valor ou um serviço
2. Combinado por escrito, no mesmo dia
3. Você paga quando a venda acontece

O cliente que queria indicar continua querendo, e agora tem motivo

Indicação se paga depois da venda, não antes

Pegou a visão?

Quantas indicações prometidas viraram venda na tua empresa?

Comenta INDICACAO que eu te mando o roteiro que eu usaria

Siga o @vendanaobra. Desenvolvo empresas da construção a vender mais e de forma previsível

#indicacao #desconto #negociacao #vendas #construcaocivil"""


class Trava(unittest.TestCase):
    def test_reprova_pergunta_citada_e_nao_mostrada(self):
        slides, _ = cv.slides_da_legenda(LEGENDA_SEM_PERGUNTA)
        erros = cv.problemas(slides)
        self.assertTrue(any("pergunta" in e for e in erros), erros)

    def test_hashtag_e_siga_nao_entram_no_slide(self):
        slides, _ = cv.slides_da_legenda(LEGENDA_SEM_PERGUNTA)
        texto = "\n".join(slides)
        self.assertNotIn("#", texto)
        self.assertNotIn("Siga o @", texto)

    def test_aprova_o_refeito_de_06_11(self):
        slides = [
            "“Me envia teu preço que já tenho 3 orçamentos”",
            "Se você manda a proposta na hora, vira só mais uma empresa na comparação de preço",
            "E comparação de preço só ganha quem tem o mais baixo, que quase nunca é você",
            "Antes de mandar qualquer número, faz uma única pergunta pra esse cliente:",
            "“Até quando você pretende tomar essa decisão?”",
            "Se ele tem data, é prioridade e você conduz a venda",
            "Essa pergunta tira a pressa falsa do cliente\n\nSalva pra usar amanhã",
        ]
        self.assertEqual(cv.problemas(slides), [])

    def test_reel_do_dia_com_roteiro_completo_passa(self):
        slides, palavra = cv.slides_da_legenda(LEGENDA_DO_DIA)
        self.assertEqual(palavra, "INDICACAO")
        self.assertEqual(cv.problemas(slides), [])
        self.assertIn("Quantas indicações prometidas", slides[-1])

    def test_curto_demais_reprova(self):
        self.assertTrue(cv.problemas(["“Tá caro”", "Pergunta antes", "Comenta X"]))


if __name__ == "__main__":
    unittest.main()
