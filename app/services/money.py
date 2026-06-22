from datetime import date
from decimal import Decimal, ROUND_HALF_UP

MONEY = Decimal("0.01")
VAT_RATE = Decimal("22.00")


ONES = {
    0: "",
    1: "один",
    2: "два",
    3: "три",
    4: "четыре",
    5: "пять",
    6: "шесть",
    7: "семь",
    8: "восемь",
    9: "девять",
}
ONES_FEM = {1: "одна", 2: "две"}
TEENS = {
    10: "десять",
    11: "одиннадцать",
    12: "двенадцать",
    13: "тринадцать",
    14: "четырнадцать",
    15: "пятнадцать",
    16: "шестнадцать",
    17: "семнадцать",
    18: "восемнадцать",
    19: "девятнадцать",
}
TENS = {
    2: "двадцать",
    3: "тридцать",
    4: "сорок",
    5: "пятьдесят",
    6: "шестьдесят",
    7: "семьдесят",
    8: "восемьдесят",
    9: "девяносто",
}
HUNDREDS = {
    1: "сто",
    2: "двести",
    3: "триста",
    4: "четыреста",
    5: "пятьсот",
    6: "шестьсот",
    7: "семьсот",
    8: "восемьсот",
    9: "девятьсот",
}


def money(value: Decimal | int | str) -> Decimal:
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def line_total(quantity: int, unit_price_vat: Decimal | str) -> Decimal:
    return money(Decimal(quantity) * Decimal(str(unit_price_vat)))


def vat_from_gross(total_with_vat: Decimal, vat_rate: Decimal = VAT_RATE) -> Decimal:
    return money(total_with_vat * vat_rate / (Decimal("100.00") + vat_rate))


def format_money(value: Decimal) -> str:
    value = money(value)
    whole, frac = f"{value:.2f}".split(".")
    groups = []
    while whole:
        groups.append(whole[-3:])
        whole = whole[:-3]
    return f"{' '.join(reversed(groups))},{frac}"


def choose_plural(number: int, forms: tuple[str, str, str]) -> str:
    n = abs(number) % 100
    if 11 <= n <= 14:
        return forms[2]
    last = n % 10
    if last == 1:
        return forms[0]
    if 2 <= last <= 4:
        return forms[1]
    return forms[2]


def _under_thousand(number: int, feminine: bool = False) -> list[str]:
    parts: list[str] = []
    hundreds = number // 100
    rest = number % 100
    tens = rest // 10
    ones = rest % 10
    if hundreds:
        parts.append(HUNDREDS[hundreds])
    if 10 <= rest <= 19:
        parts.append(TEENS[rest])
    else:
        if tens:
            parts.append(TENS[tens])
        if ones:
            if feminine and ones in ONES_FEM:
                parts.append(ONES_FEM[ones])
            else:
                parts.append(ONES[ones])
    return parts


def integer_to_words(number: int) -> str:
    if number == 0:
        return "ноль"
    if number < 0:
        return "минус " + integer_to_words(abs(number))

    scales = [
        ("", ("", "", ""), False),
        ("тысяча", ("тысяча", "тысячи", "тысяч"), True),
        ("миллион", ("миллион", "миллиона", "миллионов"), False),
        ("миллиард", ("миллиард", "миллиарда", "миллиардов"), False),
    ]
    parts: list[str] = []
    scale_index = 0
    while number > 0:
        chunk = number % 1000
        if chunk:
            _, forms, feminine = scales[scale_index]
            chunk_words = _under_thousand(chunk, feminine)
            if scale_index:
                chunk_words.append(choose_plural(chunk, forms))
            parts = chunk_words + parts
        number //= 1000
        scale_index += 1
    return " ".join(parts)


def amount_to_words(value: Decimal) -> str:
    value = money(value)
    rubles = int(value)
    kopecks = int((value - Decimal(rubles)) * 100)
    return (
        f"{integer_to_words(rubles)} {choose_plural(rubles, ('рубль', 'рубля', 'рублей'))} "
        f"{kopecks:02d} {choose_plural(kopecks, ('копейка', 'копейки', 'копеек'))}"
    )


RU_MONTHS = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря",
}


def format_ru_date(value: date) -> str:
    return f"«{value.day:02d}» {RU_MONTHS[value.month]} {value.year} г."


def format_numeric_date(value: date) -> str:
    return value.strftime("%d.%m.%Y")


def outgoing_number_for_date(value: date, middle: str) -> str:
    return f"{value.day:02d}{value.month:02d}/{middle or ''}/М"


def add_one_calendar_month(value: date) -> date:
    month = value.month + 1
    year = value.year
    if month == 13:
        month = 1
        year += 1
    month_lengths = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    day = min(value.day, month_lengths[month - 1])
    return date(year, month, day)


def sanitize_filename_part(value: str, max_len: int = 80) -> str:
    cleaned = "".join(ch for ch in value if ch not in r'\/:*?"<>|').strip()
    cleaned = "_".join(cleaned.split())
    return (cleaned[:max_len] or "Адресат").strip("_")
