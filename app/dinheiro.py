import re
from decimal import Decimal, InvalidOperation

_MILHAR_SEM_VIRGULA = re.compile(r"^\d{1,3}(\.\d{3})+$")


def parse_reais(texto: str) -> Decimal:
    """Converte o que a pessoa digitou ("140", "140,50", "R$ 1.400,50") em
    `Decimal` com no máximo 2 casas. O ponto sozinho é tratado como separador
    de milhar só quando tem cara de milhar ("1.400"); "140.50" continua sendo
    decimal."""
    limpo = (texto or "").replace("R$", "").replace(" ", "").strip()
    if not limpo:
        raise ValueError("Informe um valor")
    if "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    elif _MILHAR_SEM_VIRGULA.match(limpo):
        limpo = limpo.replace(".", "")
    try:
        valor = Decimal(limpo)
    except InvalidOperation:
        raise ValueError(f"Valor inválido: {texto!r}")
    if not valor.is_finite():
        raise ValueError(f"Valor inválido: {texto!r}")
    if valor != valor.quantize(Decimal("0.01")):
        raise ValueError("Use no máximo 2 casas decimais (centavos)")
    return valor.quantize(Decimal("0.01"))
