# -*- coding: utf-8 -*-
"""O contrato do envio em pedaços — os dois lados da ponte.

Existe porque um video de 75 MB levou 422 da API de blobs do GitHub em
04/09/2026 e o arquivo passou a subir fatiado. Se a remontagem falhar em
silencio, o que vai ao ar e' um Story truncado — pior do que nao publicar.
"""
import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fila


def item(nome, dados=b""):
    return {"name": nome, "sha": nome, "size": len(dados), "origem": "branch",
            "_dados": dados}


class RepoFalso:
    """Devolve o conteudo que o item carrega, como faria a API."""
    def entrada_baixar(self, it, destino):
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(it["_dados"])
        return destino


class TestJuntarPartes(unittest.TestCase):
    def test_conjunto_completo_vira_um_item_com_a_extensao(self):
        base = "2026-09-04-1930-solucao.mp4"
        itens = [item(f"{base}.p{i}de3") for i in (2, 1, 3)]
        itens.append(item(f"{base}.partes.json"))
        juntos, incompletos = fila.juntar_partes(itens)
        self.assertEqual(incompletos, [])
        self.assertEqual(len(juntos), 1)
        self.assertEqual(juntos[0]["name"], base)          # .mp4 preservado
        self.assertEqual(juntos[0]["origem"], "partes")
        self.assertEqual([p["name"] for p in juntos[0]["partes"]],
                         [f"{base}.p{i}de3" for i in (1, 2, 3)])   # em ordem

    def test_pedaco_faltando_nao_entra_na_fila(self):
        base = "2026-09-04-1930-solucao.mp4"
        itens = [item(f"{base}.p1de3"), item(f"{base}.p3de3"),
                 item(f"{base}.partes.json")]
        juntos, incompletos = fila.juntar_partes(itens)
        self.assertEqual(juntos, [])
        self.assertIn("2 de 3", incompletos[0])

    def test_pedacos_sem_manifesto_ficam_de_fora(self):
        itens = [item("2026-09-04-1930-x.mp4.p1de2"),
                 item("2026-09-04-1930-x.mp4.p2de2")]
        juntos, incompletos = fila.juntar_partes(itens)
        self.assertEqual(juntos, [])
        self.assertIn("sem manifesto", incompletos[0])

    def test_arquivo_normal_passa_intacto(self):
        itens = [item("2026-09-04-0930-foto.jpg")]
        juntos, incompletos = fila.juntar_partes(itens)
        self.assertEqual(juntos, itens)
        self.assertEqual(incompletos, [])


class TestRemontagem(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(__file__).parent / "_tmp"
        self.tmp.mkdir(exist_ok=True)
        self.original = bytes(range(256)) * 400          # 102.400 bytes
        self.base = "2026-09-04-1930-solucao.mp4"

    def tearDown(self):
        for f in self.tmp.glob("*"):
            f.unlink()
        self.tmp.rmdir()

    def _monta(self, dados, sha=None, bytes_=None, pedacos=4):
        n = len(dados) // pedacos + 1
        partes = [item(f"{self.base}.p{i+1}de{pedacos}", dados[i*n:(i+1)*n])
                  for i in range(pedacos)]
        man = json.dumps({"arquivo": self.base,
                          "bytes": len(dados) if bytes_ is None else bytes_,
                          "sha256": sha or hashlib.sha256(dados).hexdigest(),
                          "partes": pedacos})
        return {"name": self.base, "origem": "partes", "partes": partes,
                "manifesto": item(f"{self.base}.partes.json", man.encode())}

    def test_remonta_byte_a_byte(self):
        alvo = fila.baixar_montado(RepoFalso(), self._monta(self.original),
                                   self.tmp / "saida.mp4")
        self.assertEqual(alvo.read_bytes(), self.original)

    def test_sha256_diferente_recusa_e_apaga(self):
        it = self._monta(self.original, sha="0" * 64)
        with self.assertRaises(fila.FilaErro) as e:
            fila.baixar_montado(RepoFalso(), it, self.tmp / "saida.mp4")
        self.assertIn("nao confere", str(e.exception))
        self.assertFalse((self.tmp / "saida.mp4").exists())

    def test_tamanho_diferente_recusa(self):
        it = self._monta(self.original, bytes_=999999)
        with self.assertRaises(fila.FilaErro) as e:
            fila.baixar_montado(RepoFalso(), it, self.tmp / "saida.mp4")
        self.assertIn("bytes", str(e.exception))


if __name__ == "__main__":
    unittest.main()
