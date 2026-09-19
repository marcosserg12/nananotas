from datetime import datetime
from decimal import Decimal
from io import BytesIO

import pytest
from pypdf import PdfReader

from app.config import settings
from app.models.nota_fiscal import NotaFiscal, StatusNota
from app.services import clientes_service, danfe_pdf_service, produtos_service, vendas_service


@pytest.fixture(autouse=True)
def emitente_configurado(monkeypatch):
    monkeypatch.setattr(settings, "emitente_cnpj", "26.423.780/0001-76")
    monkeypatch.setattr(settings, "emitente_razao_social", "NANA LANCHES COMERCIO DE ALIMENTOS LTDA - ME")
    monkeypatch.setattr(settings, "emitente_ie", "0733240500173")
    monkeypatch.setattr(settings, "emitente_endereco_logradouro", "SRTVN Lote P Loja 145 - TERREO")
    monkeypatch.setattr(settings, "emitente_endereco_numero", "0")
    monkeypatch.setattr(settings, "emitente_endereco_bairro", "Asa Norte")
    monkeypatch.setattr(settings, "emitente_endereco_municipio", "BRASILIA")
    monkeypatch.setattr(settings, "emitente_endereco_uf", "DF")
    monkeypatch.setattr(settings, "sefaz_ambiente", "homologacao")
    monkeypatch.setattr(settings, "sefaz_csc_id", "1")
    monkeypatch.setattr(settings, "sefaz_csc_token", "ABCDEF0123456789ABCDEF0123456789")
    return settings


def _texto_do_pdf(pdf_bytes: bytes) -> str:
    """Extrai o texto e normaliza espaços/quebras de linha -- o PDF quebra
    linha onde o texto não cabe na largura da página, então comparar contra
    substrings com espaço simples (em vez da quebra de linha real) é o que
    reflete como o conteúdo de fato aparece pra quem lê o cupom."""
    leitor = PdfReader(BytesIO(pdf_bytes))
    texto_bruto = "\n".join(pagina.extract_text() for pagina in leitor.pages)
    return " ".join(texto_bruto.split())


def _venda_com_nota(db_session, bandeira=None, forma_pagamento="cartao_credito", preco="10.00", quantidade="2"):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="2", nome="LANCHES DIVERSOS", categoria_nome="Diversos",
        ncm="21069090", unidade="UN", preco_venda=Decimal(preco),
    )
    venda = vendas_service.criar_venda(db_session, cliente.id)
    vendas_service.adicionar_item(db_session, venda.id, produto.id, Decimal(quantidade))
    venda.forma_pagamento = forma_pagamento
    venda.bandeira = bandeira
    venda.valor_pago = venda.valor_total
    venda.troco = Decimal("0.00")
    db_session.commit()
    db_session.refresh(venda)

    nota = NotaFiscal(
        venda_id=venda.id,
        provedor="sefaz_direto",
        referencia=f"venda-{venda.id}",
        status=StatusNota.AUTORIZADA,
        numero="39763",
        serie="1",
        chave_acesso="5" * 44,
        protocolo="2532603262580 75",
        autorizado_em=datetime(2026, 6, 10, 20, 22, 25),  # 17:22:25 em Brasília
    )
    db_session.add(nota)
    db_session.commit()
    db_session.refresh(nota)
    return venda, nota


def test_gerar_pdf_danfe_produz_pdf_valido(db_session):
    venda, nota = _venda_com_nota(db_session)

    pdf_bytes = danfe_pdf_service.gerar_pdf_danfe(venda, nota)

    assert pdf_bytes.startswith(b"%PDF")


def test_gerar_pdf_danfe_cabe_em_uma_unica_pagina(db_session):
    """Regressão: `@page { size: 80mm auto }` não é suportado pelo
    xhtml2pdf (cai pro tamanho A4 padrão, deixando a folha enorme e cheia
    de espaço em branco) -- a altura da página é calculada a partir da
    quantidade de itens para caber tudo numa página só, sem sobrar espaço
    em branco excessivo."""
    venda, nota = _venda_com_nota(db_session)

    pdf_bytes = danfe_pdf_service.gerar_pdf_danfe(venda, nota)

    leitor = PdfReader(BytesIO(pdf_bytes))
    assert len(leitor.pages) == 1


def test_gerar_pdf_danfe_reproduz_layout_da_nota_real_de_referencia(db_session):
    """Reproduz fielmente o DANFE de uma nota real emitida pelo sistema
    anterior da Nana Lanches (mesmo CNPJ, pagamento em cartão) -- conferido
    campo a campo com o PDF real fornecido como referência."""
    venda, nota = _venda_com_nota(db_session, forma_pagamento="cartao_credito", preco="10.00", quantidade="2")

    texto = _texto_do_pdf(danfe_pdf_service.gerar_pdf_danfe(venda, nota))

    assert "NANA LANCHES COMERCIO DE ALIMENTOS LTDA - ME" in texto
    assert "CNPJ: 26.423.780/0001-76 IE: 0733240500173" in texto
    assert "Documento Auxiliar da Nota Fiscal de Consumidor Eletronica" in texto  # sem acento, igual ao real
    assert "LANCHES DIVERSOS" in texto
    assert "2,00" in texto  # quantidade com vírgula, não ponto
    assert "20,00" in texto  # valor total com vírgula
    assert "Frete" not in texto  # a nota real não tem essa linha
    assert "Cartão de Crédito" in texto  # rótulo legível, não o código interno "cartao_credito"
    assert "CONSUMIDOR NÃO IDENTIFICADO" in texto
    assert "NFCe n. 39763 Série 1" in texto
    assert "Protocolo de Autorização: 2532603262580 75" in texto
    assert "Data de Autorização: 10/06/2026 17:22:25" in texto
    assert "www.fazenda.df.gov.br/nfce/consulta" in texto
    assert "EM ATENDIMENTO A LEI 12.7412012" in texto
    assert "UNIAO 4,98, ESTADO 2,56" in texto
    assert "WWW.PROCON.DF.GOV.BR" in texto


def test_gerar_pdf_danfe_nao_mostra_bandeira_no_texto_do_cupom(db_session):
    """A bandeira do cartão vai só para o XML fiscal (`tBand`) -- o DANFE
    real não a exibe, então o nosso também não deve."""
    venda, nota = _venda_com_nota(db_session, bandeira="06")

    texto = _texto_do_pdf(danfe_pdf_service.gerar_pdf_danfe(venda, nota))

    assert "Elo" not in texto


def test_formatar_chave_agrupa_de_4_em_4():
    chave = "5" * 44
    resultado = danfe_pdf_service._formatar_chave(chave)

    assert resultado == " ".join(["5555"] * 11)


def test_formatar_cnpj_aplica_mascara():
    resultado = danfe_pdf_service._formatar_cnpj("26423780000176")

    assert resultado == "26.423.780/0001-76"


def test_valor_formata_com_virgula_decimal():
    assert danfe_pdf_service._valor(Decimal("20.00")) == "20,00"
    assert danfe_pdf_service._valor(None) == "0,00"
