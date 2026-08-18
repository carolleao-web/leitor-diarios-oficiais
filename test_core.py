import unittest

from core import OfficialDocumentError, is_allowed_host, validate_official_url


class SecurityTests(unittest.TestCase):
    def test_allows_official_hosts_and_subdomains(self):
        self.assertTrue(is_allowed_host("in.gov.br"))
        self.assertTrue(is_allowed_host("pesquisa.in.gov.br"))
        self.assertTrue(is_allowed_host("www.ioepa.com.br"))
        self.assertTrue(is_allowed_host("sistemas.belem.pa.gov.br"))

    def test_rejects_similar_unofficial_hosts(self):
        self.assertFalse(is_allowed_host("in.gov.br.example.com"))
        self.assertFalse(is_allowed_host("fakeioepa.com.br"))

    def test_requires_https(self):
        with self.assertRaises(OfficialDocumentError):
            validate_official_url("http://www.in.gov.br/")

    def test_rejects_unofficial_url(self):
        with self.assertRaises(OfficialDocumentError):
            validate_official_url("https://example.com/file.pdf")


if __name__ == "__main__":
    unittest.main()

