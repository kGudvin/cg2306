import unittest
from datetime import date
from types import SimpleNamespace

from app.services.document import _output_stem


class DocumentNamingTest(unittest.TestCase):
    def test_output_stem_uses_brand_inn_recipient_and_date(self):
        proposal = SimpleNamespace(
            quote_date=date(2026, 6, 23),
            recipient_inn="7727482783",
            recipient_name="\u041e\u041e\u041e \u0420\u043e\u043c\u0430\u0448\u043a\u0430",
        )

        self.assertEqual(_output_stem(proposal), "\u041a\u041f \u0411\u0435\u0448\u0442\u0430\u0443 - 7727482783 - \u041e\u041e\u041e_\u0420\u043e\u043c\u0430\u0448\u043a\u0430 - 23.06.2026")
        self.assertEqual(_output_stem(proposal, suffix="_preview_1234"), "\u041a\u041f \u0411\u0435\u0448\u0442\u0430\u0443 - 7727482783 - \u041e\u041e\u041e_\u0420\u043e\u043c\u0430\u0448\u043a\u0430 - 23.06.2026_preview_1234")


if __name__ == "__main__":
    unittest.main()
