"""Monta o PDF do DANFE-NFCe (documento auxiliar impresso/entregue ao
cliente), reproduzindo fielmente o layout de notas reais emitidas pelo
sistema anterior da Nana Lanches (mesmo CNPJ) -- ver
`app/templates/vendas/danfe_pdf.html`. Usa `xhtml2pdf` (`pisa`), que
converte um HTML+CSS simples direto para bytes de PDF sem depender de
bibliotecas nativas externas (ao contrário de WeasyPrint, que exige GTK no
Windows).

Os valores monetários/quantidades são formatados em Python (vírgula como
separador decimal, padrão brasileiro) e passados já prontos para o
template -- evita fazer conta/formatação dentro do Jinja e garante que
"2,00"/"20,00" saem exatamente como nas notas reais usadas de referência
(que usam vírgula, não ponto).
"""

from decimal import Decimal
from io import BytesIO

from jinja2 import Environment, FileSystemLoader
from xhtml2pdf import pisa

from app.config import settings
from app.constants import FORMAS_PAGAMENTO_LABELS
from app.models.nota_fiscal import NotaFiscal
from app.models.venda import Venda
from app.services.fiscal.sefaz_direto import qrcode_builder
from app.services.fiscal.sefaz_direto.xml_builder import FUSO_BRASILIA

_env = Environment(loader=FileSystemLoader("app/templates"))

# xhtml2pdf (pisa) não suporta `@page { size: 80mm auto }` -- cai
# silenciosamente para o tamanho A4 padrão, o que deixava a folha
# gigantesca e cheia de espaço em branco embaixo. Como não há como pedir
# "altura automática" de verdade, calculamos uma altura fixa a partir da
# quantidade de itens (cada item novo empurra o restante do cupom pra
# baixo) -- não é uma medida exata, mas evita tanto o espaço em branco
# excessivo quanto o cupom estourar pra uma segunda página nos casos
# comuns (poucos itens).
_LARGURA_PAGINA_MM = 80
_ALTURA_BASE_MM = 252
_ALTURA_POR_ITEM_MM = 6

# Texto fixo do aviso da Lei 12.741/2012, reproduzido caractere por caractere
# (incluindo a grafia sem acentos e sem a barra em "12.741/2012") a partir de
# notas reais emitidas pelo sistema anterior da Nana Lanches -- os
# percentuais (7,54 / 4,98 / 2,56) são os mesmos em mais de uma nota real
# analisada, então são um valor fixo configurado naquele sistema (uma
# estimativa média, não calculada por venda), não um dado inventado aqui.
_AVISO_TRIBUTOS = (
    "EM ATENDIMENTO A LEI 12.7412012 (LEI DO IMPOSTO NA NOTA FISCAL), INFORMAMOS "
    "QUE O VALOR APROXIMADO DOS TRIBUTOS INCIDENTES SOBRE AS OPERACOES DESDE "
    "ESTABELECIMENTO E DE: 7,54. ASSIM DISTRIBUIDO: UNIAO 4,98, ESTADO 2,56 - "
    "PROCON 151 SCS Q. 08 ED. VENANCIO 2000 BL. B-60 SL. 240 CEP- 70.333-900 "
    "WWW.PROCON.DF.GOV.BR"
)


def _somente_digitos(valor: str | None) -> str:
    return "".join(c for c in (valor or "") if c.isdigit())


def _formatar_cnpj(cnpj: str | None) -> str:
    digitos = _somente_digitos(cnpj)
    if len(digitos) != 14:
        return cnpj or ""
    return f"{digitos[0:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:14]}"


def _formatar_chave(chave: str | None) -> str:
    if not chave:
        return ""
    return " ".join(chave[i : i + 4] for i in range(0, len(chave), 4))


def _valor(numero: Decimal | None) -> str:
    """Formata no padrão brasileiro (vírgula decimal) -- "20.00" -> "20,00"."""
    if numero is None:
        numero = Decimal("0")
    return f"{numero:.2f}".replace(".", ",")


def gerar_pdf_danfe(venda: Venda, nota: NotaFiscal) -> bytes:
    template = _env.get_template("vendas/danfe_pdf.html")

    url_qrcode = qrcode_builder.montar_url_qrcode(
        nota.chave_acesso, settings.sefaz_ambiente, settings.sefaz_csc_id, settings.sefaz_csc_token
    )
    qrcode_imagem = qrcode_builder.gerar_imagem_qrcode_base64(url_qrcode)

    # `dhEmi` (momento real da emissão) não é persistido hoje -- só o
    # momento em que a nota passou a "autorizada" (`nota.autorizado_em`).
    # Para NFC-e emitida de forma síncrona (indSinc=1, o único modo que este
    # sistema usa), os dois instantes são, na prática, o mesmo -- por isso
    # reusamos `autorizado_em` também na linha "NFCe n. ... Série ...".
    data_formatada = None
    if nota.autorizado_em:
        data_formatada = (nota.autorizado_em + FUSO_BRASILIA).strftime("%d/%m/%Y %H:%M:%S")

    itens = [
        {
            "codigo": item.produto.codigo_interno,
            "descricao": item.produto.nome,
            "unidade": item.produto.unidade,
            "quantidade_formatada": _valor(item.quantidade),
            "vl_unit_formatado": _valor(item.preco_unitario),
            "vl_total_formatado": _valor(item.quantidade * item.preco_unitario),
        }
        for item in venda.itens
    ]

    html = template.render(
        venda=venda,
        nota=nota,
        itens=itens,
        emitente_razao_social=settings.emitente_razao_social,
        emitente_cnpj_formatado=_formatar_cnpj(settings.emitente_cnpj),
        emitente_ie=settings.emitente_ie,
        emitente_endereco_logradouro=settings.emitente_endereco_logradouro,
        emitente_endereco_numero=settings.emitente_endereco_numero,
        emitente_endereco_bairro=settings.emitente_endereco_bairro,
        emitente_endereco_municipio=settings.emitente_endereco_municipio,
        emitente_endereco_uf=settings.emitente_endereco_uf,
        emitente_telefone=settings.emitente_telefone,
        qrcode_imagem=qrcode_imagem,
        chave_formatada=_formatar_chave(nota.chave_acesso),
        url_consulta=qrcode_builder.montar_url_consulta_chave(),
        forma_pagamento_label=FORMAS_PAGAMENTO_LABELS.get(venda.forma_pagamento, venda.forma_pagamento or "-"),
        qtde_total_itens=len(venda.itens),
        valor_total_formatado=_valor(venda.valor_total),
        valor_pago_formatado=_valor(venda.valor_pago if venda.valor_pago is not None else venda.valor_total),
        troco_formatado=_valor(venda.troco),
        data_formatada=data_formatada,
        aviso_tributos=_AVISO_TRIBUTOS,
        largura_pagina_mm=_LARGURA_PAGINA_MM,
        altura_pagina_mm=_ALTURA_BASE_MM + len(itens) * _ALTURA_POR_ITEM_MM,
    )

    buffer = BytesIO()
    resultado = pisa.CreatePDF(html, dest=buffer)
    if resultado.err:
        raise ValueError("Falha ao gerar o PDF do DANFE")
    return buffer.getvalue()
