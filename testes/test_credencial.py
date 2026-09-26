import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import publicar_story  # noqa: E402
import refresh_token  # noqa: E402


class TestCredencial(unittest.TestCase):
    def test_meta_token_manda_e_ignora_o_id_do_login(self):
        env = {"META_TOKEN": "sistema", "IG_ACCESS_TOKEN": "login",
               "IG_USER_ID": "28458102257148998"}
        with mock.patch.dict(os.environ, env, clear=True):
            graph, ig_id, token = publicar_story.credencial()
        self.assertEqual(graph, publicar_story.GRAPH_META)
        self.assertEqual(ig_id, "17841470188725651")
        self.assertEqual(token, "sistema")

    def test_fallback_para_o_token_de_login(self):
        with mock.patch.dict(os.environ, {"IG_ACCESS_TOKEN": "login"}, clear=True):
            graph, ig_id, token = publicar_story.credencial()
        self.assertEqual((graph, ig_id, token), (publicar_story.GRAPH, "", "login"))

    def test_sem_token_nenhum(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(publicar_story.credencial())

    def test_token_invalidado_nao_vira_alarme(self):
        self.assertTrue(refresh_token.token_morto(
            "Error validating access token: The session has been invalidated "
            "because the user changed their password or Facebook has changed "
            "the session for security reasons."))
        self.assertFalse(refresh_token.token_morto("Please retry in 24 hours"))


class TestVencido(unittest.TestCase):
    def test_story_de_dias_atras_fica_segurado(self):
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo
        agora = datetime(2026, 9, 26, 13, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
        self.assertTrue(publicar_story.vencido_demais(agora - timedelta(days=10), agora, 24))
        self.assertFalse(publicar_story.vencido_demais(agora - timedelta(hours=3), agora, 24))
        self.assertFalse(publicar_story.vencido_demais(agora + timedelta(hours=1), agora, 24))


if __name__ == "__main__":
    unittest.main()
