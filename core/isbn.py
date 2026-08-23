from dataclasses import dataclass
import re


@dataclass
class ISBNResult:
    original: str
    cleaned: str
    valid: bool
    isbn13: str = ""
    error: str = ""


def validate_isbn(value: str) -> ISBNResult:
    original = str(value).strip()

    if not original:
        return ISBNResult(
            original=original,
            cleaned="",
            valid=False,
            error="ISBN is empty.",
        )

    cleaned = re.sub(
        r"[\s-]",
        "",
        original.upper(),
    )

    if len(cleaned) == 13:
        return _validate_isbn13(
            original,
            cleaned,
        )

    if len(cleaned) == 10:
        return _validate_isbn10(
            original,
            cleaned,
        )

    return ISBNResult(
        original=original,
        cleaned=cleaned,
        valid=False,
        error="ISBN must contain 10 or 13 characters.",
    )


def _validate_isbn13(
    original: str,
    cleaned: str,
) -> ISBNResult:

    if not cleaned.isdigit():
        return ISBNResult(
            original=original,
            cleaned=cleaned,
            valid=False,
            error="ISBN-13 must contain digits only.",
        )

    if not cleaned.startswith(("978", "979")):
        return ISBNResult(
            original=original,
            cleaned=cleaned,
            valid=False,
            error="ISBN-13 must begin with 978 or 979.",
        )

    total = 0

    for index, digit in enumerate(cleaned[:12]):
        multiplier = 1 if index % 2 == 0 else 3
        total += int(digit) * multiplier

    expected_check_digit = (
        10 - (total % 10)
    ) % 10

    actual_check_digit = int(
        cleaned[12]
    )

    if expected_check_digit != actual_check_digit:
        return ISBNResult(
            original=original,
            cleaned=cleaned,
            valid=False,
            error="Invalid ISBN-13 check digit.",
        )

    return ISBNResult(
        original=original,
        cleaned=cleaned,
        valid=True,
        isbn13=cleaned,
    )


def _validate_isbn10(
    original: str,
    cleaned: str,
) -> ISBNResult:

    if not cleaned[:9].isdigit():
        return ISBNResult(
            original=original,
            cleaned=cleaned,
            valid=False,
            error="Invalid ISBN-10.",
        )

    if not (
        cleaned[9].isdigit()
        or cleaned[9] == "X"
    ):
        return ISBNResult(
            original=original,
            cleaned=cleaned,
            valid=False,
            error="Invalid ISBN-10 check digit.",
        )

    total = 0

    for index, character in enumerate(cleaned):
        value = 10 if character == "X" else int(character)
        total += value * (10 - index)

    if total % 11 != 0:
        return ISBNResult(
            original=original,
            cleaned=cleaned,
            valid=False,
            error="Invalid ISBN-10 check digit.",
        )

    isbn12 = "978" + cleaned[:9]

    total = 0

    for index, digit in enumerate(isbn12):
        multiplier = 1 if index % 2 == 0 else 3
        total += int(digit) * multiplier

    check_digit = (
        10 - (total % 10)
    ) % 10

    isbn13 = isbn12 + str(check_digit)

    return ISBNResult(
        original=original,
        cleaned=cleaned,
        valid=True,
        isbn13=isbn13,
    )
