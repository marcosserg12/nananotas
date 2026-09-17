from app.dependencies import get_fiscal_provider
from app.services.fiscal.sefaz_direto.provider import SefazDiretoProvider


def test_get_fiscal_provider_retorna_sefaz_direto_por_padrao():
    provider = get_fiscal_provider()

    assert isinstance(provider, SefazDiretoProvider)
