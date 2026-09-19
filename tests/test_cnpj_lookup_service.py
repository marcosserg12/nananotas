import httpx
import pytest

from app.services import cnpj_lookup_service


class _RespostaFalsa:
    def __init__(self, status_code, corpo=None):
        self.status_code = status_code
        self._corpo = corpo or {}

    def json(self):
        return self._corpo


def test_buscar_dados_cnpj_com_formato_invalido_levanta_erro():
    with pytest.raises(ValueError, match="inválido"):
        cnpj_lookup_service.buscar_dados_cnpj("123")


def test_buscar_dados_cnpj_sucesso_mapeia_campos(monkeypatch):
    corpo = {
        "razao_social": "OPEN KNOWLEDGE BRASIL",
        "nome_fantasia": "REDE PELO CONHECIMENTO LIVRE",
        "logradouro": "PAULISTA",
        "numero": "37",
        "complemento": "ANDAR 4",
        "bairro": "BELA VISTA",
        "municipio": "SAO PAULO",
        "uf": "SP",
        "cep": "01311902",
    }
    monkeypatch.setattr(httpx, "get", lambda url, timeout=10: _RespostaFalsa(200, corpo))

    dados = cnpj_lookup_service.buscar_dados_cnpj("19.131.243/0001-97")

    assert dados["razao_social"] == "OPEN KNOWLEDGE BRASIL"
    assert dados["cidade"] == "SAO PAULO"
    assert dados["uf"] == "SP"
    assert dados["cep"] == "01311902"


def test_buscar_dados_cnpj_nao_encontrado_levanta_erro(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda url, timeout=10: _RespostaFalsa(404))

    with pytest.raises(ValueError, match="não encontrado"):
        cnpj_lookup_service.buscar_dados_cnpj("11222333000181")


def test_buscar_dados_cnpj_erro_de_rede_levanta_erro_claro(monkeypatch):
    def levantar(*args, **kwargs):
        raise httpx.ConnectError("falha de conexão")

    monkeypatch.setattr(httpx, "get", levantar)

    with pytest.raises(ValueError):
        cnpj_lookup_service.buscar_dados_cnpj("11222333000181")
