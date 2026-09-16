from app.services.fiscal.base import FiscalProvider
from app.services.fiscal.focus_nfe import FocusNFeProvider

_provider = FocusNFeProvider()


def get_fiscal_provider() -> FiscalProvider:
    return _provider
