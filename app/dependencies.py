from app.services.fiscal.base import FiscalProvider
from app.services.fiscal.sefaz_direto.provider import SefazDiretoProvider

_provider = SefazDiretoProvider()


def get_fiscal_provider() -> FiscalProvider:
    return _provider
