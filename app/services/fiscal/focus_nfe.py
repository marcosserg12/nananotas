from decimal import Decimal

import httpx

from app.config import settings
from app.models.venda import Venda
from app.services.fiscal.base import FiscalProvider, ResultadoFiscal

BASE_URLS = {
    "homologacao": "https://homologacao.focusnfe.com.br",
    "producao": "https://api.focusnfe.com.br",
}

STATUS_MAP = {
    "processando_autorizacao": "processando",
    "autorizado": "autorizada",
    "erro_autorizacao": "rejeitada",
    "cancelado": "cancelada",
}

FORMAS_PAGAMENTO_CODIGOS = {
    "dinheiro": "01",
    "cartao_credito": "03",
    "cartao_debito": "04",
    "pix": "17",
}

MENSAGEM_ERRO_PADRAO = "Erro desconhecido na emissão"

DUAS_CASAS = Decimal("0.01")


def montar_payload(venda: Venda) -> dict:
    cliente = venda.cliente
    payload = {
        "natureza_operacao": "Venda",
        "data_emissao": venda.data_venda.strftime("%Y-%m-%dT%H:%M:%S-03:00"),
        "presenca_comprador": "1",
        "modalidade_frete": "9",
        "items": [
            {
                "numero_item": str(index),
                "codigo_produto": item.produto.codigo_interno,
                "descricao": item.produto.nome,
                "ncm": item.produto.ncm,
                "cfop": "5102",
                "unidade_comercial": item.produto.unidade,
                "quantidade_comercial": str(item.quantidade),
                "valor_unitario_comercial": str(item.preco_unitario),
                "valor_bruto": str((item.quantidade * item.preco_unitario).quantize(DUAS_CASAS)),
                "unidade_tributavel": item.produto.unidade,
                "quantidade_tributavel": str(item.quantidade),
                "valor_unitario_tributavel": str(item.preco_unitario),
                "icms_origem": "0",
                "icms_situacao_tributaria": "102",
                "pis_situacao_tributaria": "49",
                "cofins_situacao_tributaria": "49",
            }
            for index, item in enumerate(venda.itens, start=1)
        ],
        "formas_pagamento": [
            {
                "forma_pagamento": FORMAS_PAGAMENTO_CODIGOS.get(venda.forma_pagamento, "99"),
                "valor_pagamento": str(venda.valor_total),
            }
        ],
    }
    if cliente is not None and not cliente.consumidor_final and cliente.cpf_cnpj:
        documento = cliente.cpf_cnpj
        if len(documento) <= 11:
            payload["cpf"] = documento
        else:
            payload["cnpj"] = documento
        payload["nome_destinatario"] = cliente.nome
    return payload


class FocusNFeProvider(FiscalProvider):
    def __init__(self, token: str | None = None, ambiente: str | None = None, client: httpx.Client | None = None):
        self.token = token or settings.focus_nfe_token
        self.ambiente = ambiente or settings.focus_nfe_ambiente
        if self.ambiente not in BASE_URLS:
            raise ValueError(
                f"FOCUS_NFE_AMBIENTE inválido: {self.ambiente!r} (use 'homologacao' ou 'producao')"
            )
        self.base_url = BASE_URLS[self.ambiente]
        self.client = client or httpx.Client(base_url=self.base_url, auth=(self.token, ""))

    def emitir(self, venda: Venda) -> ResultadoFiscal:
        referencia = f"venda-{venda.id}"
        payload = montar_payload(venda)
        response = self.client.post(f"/v2/nfce?ref={referencia}", json=payload)
        return self._parse(referencia, self._parse_json(response))

    def consultar(self, referencia: str) -> ResultadoFiscal:
        response = self.client.get(f"/v2/nfce/{referencia}")
        return self._parse(referencia, self._parse_json(response))

    def cancelar(self, referencia: str, motivo: str) -> ResultadoFiscal:
        response = self.client.request(
            "DELETE", f"/v2/nfce/{referencia}", json={"justificativa": motivo}
        )
        return self._parse(referencia, self._parse_json(response))

    @staticmethod
    def _parse_json(response: httpx.Response) -> dict:
        try:
            return response.json()
        except ValueError:
            return {}

    @staticmethod
    def _parse(referencia: str, data: dict) -> ResultadoFiscal:
        status = STATUS_MAP.get(data.get("status"), "rejeitada")
        mensagem_erro = data.get("mensagem_sefaz") or data.get("mensagem")
        if status == "rejeitada" and not mensagem_erro:
            mensagem_erro = MENSAGEM_ERRO_PADRAO
        return ResultadoFiscal(
            referencia=referencia,
            status=status,
            numero=data.get("numero"),
            serie=data.get("serie"),
            chave_acesso=data.get("chave_nfe"),
            protocolo=data.get("protocolo_autorizacao"),
            url_danfe=data.get("caminho_danfe") or data.get("url_danfe"),
            url_xml=data.get("caminho_xml_nota_fiscal") or data.get("url_xml"),
            mensagem_erro=mensagem_erro,
        )
