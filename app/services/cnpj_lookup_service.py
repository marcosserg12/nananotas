"""Busca dados cadastrais de uma empresa a partir do CNPJ, usando a BrasilAPI
(https://brasilapi.com.br) -- API pública e gratuita, sem necessidade de
chave/cadastro. Usada para preencher automaticamente o formulário de cliente
PJ, evitando digitação manual de razão social/endereço.

IMPORTANT: o campo `codigo_municipio` que a BrasilAPI devolve é o código de
município da Receita Federal (TOM), NÃO o código IBGE de 7 dígitos que a
NFC-e exige em `Tendereco.cMun` -- os dois são numeração diferente. Por isso
esta função não tenta preencher `cMun`; ver
`app/services/fiscal/sefaz_direto/xml_builder.py::_montar_dest`.
"""

import httpx

BASE_URL = "https://brasilapi.com.br/api/cnpj/v1"


def buscar_dados_cnpj(cnpj: str) -> dict:
    """Retorna um dict com os campos do cliente já no formato esperado pelo
    formulário (`razao_social`, `nome_fantasia`, `logradouro`, `numero`,
    `complemento`, `bairro`, `cidade`, `uf`, `cep`), ou levanta `ValueError`
    com uma mensagem em português se o CNPJ não for encontrado ou a consulta
    falhar."""
    cnpj_digitos = "".join(c for c in cnpj if c.isdigit())
    if len(cnpj_digitos) != 14:
        raise ValueError("CNPJ inválido: precisa ter 14 dígitos")

    try:
        resposta = httpx.get(f"{BASE_URL}/{cnpj_digitos}", timeout=10)
    except httpx.HTTPError as exc:
        raise ValueError(f"Não foi possível consultar o CNPJ: {exc}") from exc

    if resposta.status_code == 404:
        raise ValueError("CNPJ não encontrado")
    if resposta.status_code != 200:
        raise ValueError(f"Consulta de CNPJ falhou (HTTP {resposta.status_code})")

    dados = resposta.json()
    return {
        "razao_social": dados.get("razao_social") or "",
        "nome_fantasia": dados.get("nome_fantasia") or "",
        "logradouro": dados.get("logradouro") or "",
        "numero": dados.get("numero") or "",
        "complemento": dados.get("complemento") or "",
        "bairro": dados.get("bairro") or "",
        "cidade": dados.get("municipio") or "",
        "uf": dados.get("uf") or "",
        "cep": dados.get("cep") or "",
    }
