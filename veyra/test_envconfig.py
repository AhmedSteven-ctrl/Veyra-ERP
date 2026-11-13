import os
import tempfile
import unittest

from veyra.envconfig import load_env_file, parse_database_url

DIRECT = "postgresql://app_owner:s3cret@ep-quiet-lake-123456.c-7.us-east-2.aws.neon.tech/appdb?sslmode=require&channel_binding=require"


class ParseDatabaseUrlTests(unittest.TestCase):
    def test_neon_style_url(self):
        cfg = parse_database_url(DIRECT)
        self.assertEqual(cfg["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual((cfg["NAME"], cfg["USER"], cfg["PASSWORD"]), ("appdb", "app_owner", "s3cret"))
        self.assertEqual(cfg["HOST"], "ep-quiet-lake-123456.c-7.us-east-2.aws.neon.tech")
        self.assertEqual(cfg["PORT"], "")
        self.assertEqual(cfg["OPTIONS"], {"sslmode": "require", "channel_binding": "require"})
        self.assertNotIn("DISABLE_SERVER_SIDE_CURSORS", cfg)

    def test_pooler_host_disables_server_side_cursors(self):
        cfg = parse_database_url(DIRECT.replace("ep-quiet-lake-123456", "ep-quiet-lake-123456-pooler"))
        self.assertTrue(cfg["DISABLE_SERVER_SIDE_CURSORS"])

    def test_accepts_the_whole_psql_command_with_quotes(self):
        self.assertEqual(parse_database_url(f"psql '{DIRECT}'")["NAME"], "appdb")
        self.assertEqual(parse_database_url(f'  "{DIRECT}"  ')["USER"], "app_owner")

    def test_port_and_percent_encoded_password(self):
        cfg = parse_database_url("postgres://u:p%40ss%2Fword@db.example.com:6432/mydb")
        self.assertEqual((cfg["PASSWORD"], cfg["PORT"], cfg["OPTIONS"]), ("p@ss/word", "6432", {}))

    def test_bad_urls_are_rejected_without_leaking_the_password(self):
        for bad in ("", "mysql://u:p@h/db", "postgresql://u:topsecret@/db", "postgresql://u:topsecret@host", "not a url"):
            with self.assertRaises(ValueError) as caught:
                parse_database_url(bad)
            self.assertNotIn("topsecret", str(caught.exception))


class LoadEnvFileTests(unittest.TestCase):
    def load(self, text, environ=None, raw=None):
        environ = {} if environ is None else environ
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, ".env")
            with open(path, "wb") as handle:
                handle.write(raw if raw is not None else text.encode("utf-8"))
            load_env_file(path, environ)
        return environ

    def test_reads_values_comments_blank_lines_quotes_and_export(self):
        env = self.load("# تعليق\n\nA=1\nB = two \nC=\"quoted value\"\nD='single'\nexport E=5\nno equals sign here\n")
        self.assertEqual(env, {"A": "1", "B": "two", "C": "quoted value", "D": "single", "E": "5"})

    def test_value_may_contain_equals_and_ampersand(self):
        env = self.load(f"DATABASE_URL={DIRECT}\n")
        self.assertEqual(env["DATABASE_URL"], DIRECT)

    def test_existing_environment_wins_over_the_file(self):
        env = self.load("A=from-file\nB=from-file\n", {"A": "from-shell"})
        self.assertEqual((env["A"], env["B"]), ("from-shell", "from-file"))

    def test_utf8_bom_from_notepad_or_powershell_is_ignored(self):
        env = self.load("", raw=b"\xef\xbb\xbfFIRST=ok\nSECOND=ok\n")
        self.assertEqual(env, {"FIRST": "ok", "SECOND": "ok"})

    def test_missing_file_is_fine(self):
        environ = {}
        load_env_file(os.path.join(tempfile.gettempdir(), "definitely-missing-folder", ".env"), environ)
        self.assertEqual(environ, {})


if __name__ == "__main__":
    unittest.main()
