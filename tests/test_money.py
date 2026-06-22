import unittest
from datetime import date
from decimal import Decimal

from app.services.money import amount_to_words, format_money, line_total, outgoing_number_for_date, vat_from_gross


class MoneyTest(unittest.TestCase):
    def test_money_format_and_line_total(self):
        self.assertEqual(line_total(8, Decimal("412500.00")), Decimal("3300000.00"))
        self.assertEqual(format_money(Decimal("3953600")), "3 953 600,00")

    def test_vat_22_from_gross(self):
        self.assertEqual(vat_from_gross(Decimal("3953600.00")), Decimal("712944.26"))

    def test_amount_words(self):
        expected = (
            "\u0442\u0440\u0438 \u043c\u0438\u043b\u043b\u0438\u043e\u043d\u0430 "
            "\u0434\u0435\u0432\u044f\u0442\u044c\u0441\u043e\u0442 "
            "\u043f\u044f\u0442\u044c\u0434\u0435\u0441\u044f\u0442 "
            "\u0442\u0440\u0438 \u0442\u044b\u0441\u044f\u0447\u0438 "
            "\u0448\u0435\u0441\u0442\u044c\u0441\u043e\u0442 "
            "\u0440\u0443\u0431\u043b\u0435\u0439 00 "
            "\u043a\u043e\u043f\u0435\u0435\u043a"
        )
        self.assertEqual(amount_to_words(Decimal("3953600.00")), expected)

    def test_outgoing_number(self):
        self.assertEqual(outgoing_number_for_date(date(2026, 3, 20), ""), "2003//\u041c")
        self.assertEqual(outgoing_number_for_date(date(2026, 3, 20), "15"), "2003/15/\u041c")


if __name__ == "__main__":
    unittest.main()
