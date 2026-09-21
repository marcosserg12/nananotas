from decimal import Decimal

import pytest

from app.dinheiro import parse_reais


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("140", "140.00"),
        ("140,5", "140.50"),
        ("140,50", "140.50"),
        ("140.50", "140.50"),
        ("R$ 140,50", "140.50"),
        ("1.400", "1400.00"),
        ("1.400,50", "1400.50"),
        ("12.345.678", "12345678.00"),
        ("10.999", "10999.00"),
        ("0,01", "0.01"),
        ("  99  ", "99.00"),
    ],
)
def test_parse_reais_aceita_formatos_brasileiros(texto, esperado):
    assert parse_reais(texto) == Decimal(esperado)


@pytest.mark.parametrize("texto", ["", "   ", "abc", "12,3,4", "1,234", "1.4001", "NaN", "Infinity", "--5"])
def test_parse_reais_recusa_entradas_invalidas(texto):
    with pytest.raises(ValueError):
        parse_reais(texto)
