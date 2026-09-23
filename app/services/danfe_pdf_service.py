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
from reportlab.pdfbase.pdfmetrics import stringWidth
from xhtml2pdf import pisa

from app.config import settings
from app.constants import FORMAS_PAGAMENTO_LABELS
from app.models.nota_fiscal import NotaFiscal
from app.models.venda import Venda
from app.services.fiscal.sefaz_direto import qrcode_builder
from app.services.fiscal.sefaz_direto.xml_builder import FUSO_BRASILIA

_env = Environment(loader=FileSystemLoader("app/templates"))

# xhtml2pdf (pisa) não suporta `@page { size: 80mm auto }` -- cai
# silenciosamente para o tamanho A4 padrão, o que deixava a folha gigantesca
# e cheia de espaço em branco embaixo. Como não há como pedir "altura
# automática" de verdade, calculamos uma altura fixa antes de renderizar.
#
# A primeira versão dessa conta assumia 1 linha por item (uma "altura por
# item" fixa em mm) -- e estourava pra uma segunda página sempre que a
# DESCRIÇÃO DE ALGUM ITEM QUEBRAVA EM MAIS DE UMA LINHA (nome de produto
# comprido para a coluna), porque cada linha extra que o navegador/pisa
# desenhava não tinha sido contabilizada. Como a maioria dos nomes de
# lanchonete tem mais de uma palavra, isso acontecia com bastante
# frequência, não só com "muitos itens".
#
# A conta abaixo resolve isso quebrando o MESMO texto que vai pro HTML com a
# métrica de fonte real do reportlab (o motor que o xhtml2pdf usa por baixo
# dos panos pra desenhar texto) -- ou seja, contamos as linhas do jeito que
# o renderizador final vai efetivamente quebrar, em vez de arriscar um
# "número de caracteres por linha" chutado. Fazemos isso pra todo texto de
# tamanho variável do cupom (nome de produto, nome de cliente, razão social,
# endereço do emitente), não só pros itens -- qualquer um deles pode ser
# longo o bastante pra quebrar em mais de uma linha.
_LARGURA_PAGINA_MM = 80
_MM_POR_PONTO = 25.4 / 72
_LARGURA_CONTEUDO_MM = 72.0  # 80mm de página menos as margens de 4mm de cada lado do @page
_LARGURA_ITEM_MM = 70.0  # coluna de descrição do item, descontando um pequeno respiro interno

# Calibrados renderizando o template real com o xhtml2pdf e medindo a altura
# de conteúdo efetivamente usada (ver relatório da tarefa) -- não são
# "chutes", mas também não precisam ser exatos: `_MARGEM_SEGURANCA_MM`
# absorve a diferença residual entre esta conta e o motor de layout real.
_ALTURA_ESQUELETO_MM = 192.0  # tudo que não depende de item nenhum, assumindo 1 linha p/ cada texto variável
_ALTURA_POR_ITEM_MM = 11.5  # por item: 1 linha do nome + 1 linha de qtde/valor
_ALTURA_LINHA_EXTRA_MM = 6.0  # cada linha ALÉM da primeira, em qualquer texto de tamanho variável
_MARGEM_SEGURANCA_MM = 8.0

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


def _contar_linhas(texto: str, largura_mm: float, fonte: str, tamanho_pt: float) -> int:
    """Conta em quantas linhas o `texto` vai quebrar quando o xhtml2pdf
    desenhar ele numa caixa de `largura_mm` -- usando a mesma métrica de
    fonte (reportlab) que o próprio xhtml2pdf usa internamente, em vez de
    estimar "caracteres por linha" no escuro."""
    texto = (texto or "").strip()
    if not texto:
        return 1
    largura_pt = largura_mm / _MM_POR_PONTO
    palavras = texto.split()
    linhas = 1
    linha_atual = palavras[0]
    for palavra in palavras[1:]:
        candidata = f"{linha_atual} {palavra}"
        if stringWidth(candidata, fonte, tamanho_pt) <= largura_pt:
            linha_atual = candidata
        else:
            linhas += 1
            linha_atual = palavra
    return linhas


def _linhas_extras(texto: str, largura_mm: float, fonte: str, tamanho_pt: float) -> int:
    """Quantas linhas o texto ocupa ALÉM da primeira -- é só essa parte que
    precisa ser somada na altura da página, já que a primeira linha de cada
    campo já está contabilizada em `_ALTURA_ESQUELETO_MM`."""
    return max(0, _contar_linhas(texto, largura_mm, fonte, tamanho_pt) - 1)


def _calcular_altura_pagina_mm(
    *,
    razao_social: str,
    cnpj_ie_linha: str,
    endereco_linha: str,
    municipio_fone_linha: str,
    cliente_linha: str,
    itens: list[dict],
) -> float:
    linhas_extras_texto = (
        _linhas_extras(razao_social, _LARGURA_CONTEUDO_MM, "Courier-Bold", 11)
        + _linhas_extras(cnpj_ie_linha, _LARGURA_CONTEUDO_MM, "Courier", 8)
        + _linhas_extras(endereco_linha, _LARGURA_CONTEUDO_MM, "Courier", 8)
        + _linhas_extras(municipio_fone_linha, _LARGURA_CONTEUDO_MM, "Courier", 8)
        + _linhas_extras(cliente_linha, _LARGURA_CONTEUDO_MM, "Courier", 7.5)
        + _linhas_extras(_AVISO_TRIBUTOS, _LARGURA_CONTEUDO_MM, "Courier", 7.5)
    )
    linhas_extras_itens = sum(
        _linhas_extras(f"{item['codigo']}  {item['descricao']}", _LARGURA_ITEM_MM, "Courier-Bold", 8)
        for item in itens
    )
    return (
        _ALTURA_ESQUELETO_MM
        + _ALTURA_POR_ITEM_MM * len(itens)
        + _ALTURA_LINHA_EXTRA_MM * (linhas_extras_texto + linhas_extras_itens)
        + _MARGEM_SEGURANCA_MM
    )


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

    emitente_cnpj_formatado = _formatar_cnpj(settings.emitente_cnpj)

    # Estas strings precisam espelhar EXATAMENTE o texto que o template
    # monta em cada linha (mesmos espaços/separadores) -- é sobre elas que
    # `_calcular_altura_pagina_mm` mede a quebra de linha real.
    cnpj_ie_linha = f"CNPJ: {emitente_cnpj_formatado}"
    if settings.emitente_ie:
        cnpj_ie_linha += f"  IE: {settings.emitente_ie}"
    endereco_linha = settings.emitente_endereco_logradouro
    if settings.emitente_endereco_numero:
        endereco_linha += f", {settings.emitente_endereco_numero}"
    if settings.emitente_endereco_bairro:
        endereco_linha += f" - {settings.emitente_endereco_bairro}"
    municipio_fone_linha = f"{settings.emitente_endereco_municipio}-{settings.emitente_endereco_uf}"
    if settings.emitente_telefone:
        municipio_fone_linha += f"  Fone: {settings.emitente_telefone}"
    if venda.cliente and not venda.cliente.consumidor_final and venda.cliente.cpf_cnpj:
        cliente_linha = f"{venda.cliente.nome} — {venda.cliente.cpf_cnpj}"
    else:
        cliente_linha = "CONSUMIDOR NÃO IDENTIFICADO"

    altura_pagina_mm = _calcular_altura_pagina_mm(
        razao_social=settings.emitente_razao_social,
        cnpj_ie_linha=cnpj_ie_linha,
        endereco_linha=endereco_linha,
        municipio_fone_linha=municipio_fone_linha,
        cliente_linha=cliente_linha,
        itens=itens,
    )

    html = template.render(
        venda=venda,
        nota=nota,
        itens=itens,
        emitente_razao_social=settings.emitente_razao_social,
        emitente_cnpj_formatado=emitente_cnpj_formatado,
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
        altura_pagina_mm=altura_pagina_mm,
    )

    buffer = BytesIO()
    resultado = pisa.CreatePDF(html, dest=buffer)
    if resultado.err:
        raise ValueError("Falha ao gerar o PDF do DANFE")
    return buffer.getvalue()
