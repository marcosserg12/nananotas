from decimal import Decimal
from xml.etree import ElementTree

import pytest

from app.config import settings
from app.models.cliente import Cliente, TipoPessoa
from app.services import clientes_service, produtos_service, vendas_service
from app.services.fiscal.sefaz_direto import xml_builder

NS = {"nfe": "http://www.portalfiscal.inf.br/nfe"}


@pytest.fixture(autouse=True)
def emitente_configurado(monkeypatch):
    """Dados de emitente válidos (estruturalmente) para os testes.

    Não são segredos de produção -- CNPJ/endereço são os mesmos valores
    reais documentados em .env.example para o Nana Lanches; IE/CEP/número
    aqui são valores de teste porque o brief não forneceu esses dados.
    """
    monkeypatch.setattr(settings, "emitente_cnpj", "26.423.780/0001-76")
    monkeypatch.setattr(settings, "emitente_razao_social", "NANA LANCHES COMERCIO DE ALIMENTOS LTDA")
    monkeypatch.setattr(settings, "emitente_nome_fantasia", "Nana Lanches")
    monkeypatch.setattr(settings, "emitente_ie", "0000000000")
    monkeypatch.setattr(settings, "emitente_endereco_logradouro", "SRTVN Lote P Loja 145 - TERREO")
    monkeypatch.setattr(settings, "emitente_endereco_numero", "SN")
    monkeypatch.setattr(settings, "emitente_endereco_bairro", "Asa Norte")
    monkeypatch.setattr(settings, "emitente_endereco_municipio", "Brasília")
    monkeypatch.setattr(settings, "emitente_endereco_uf", "DF")
    monkeypatch.setattr(settings, "emitente_endereco_cep", "70719040")
    monkeypatch.setattr(settings, "sefaz_ambiente", "homologacao")
    return settings


def _venda_com_item(db_session):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = produtos_service.criar_produto(
        db_session,
        codigo_interno="1",
        nome="Lanche",
        categoria_nome="Diversos",
        ncm="21069090",
        unidade="UN",
        preco_venda=Decimal("15.00"),
    )
    venda = vendas_service.criar_venda(db_session, cliente.id)
    vendas_service.adicionar_item(db_session, venda.id, produto.id, Decimal("2"))
    return venda


def test_montar_nfce_xml_produz_xml_bem_formado_com_dados_da_venda(db_session):
    venda = _venda_com_item(db_session)

    xml_texto = xml_builder.montar_nfce_xml(venda, numero=1, serie=1)

    raiz = ElementTree.fromstring(xml_texto)  # levanta exceção se o XML não for bem-formado
    assert xml_texto  # não vazio
    assert "21069090" in xml_texto  # NCM do produto presente
    assert "15.00" in xml_texto or "15,00" in xml_texto  # preço presente em algum formato
    assert raiz.tag == "{http://www.portalfiscal.inf.br/nfe}NFe"


def test_montar_nfce_xml_inclui_numero_e_serie_informados(db_session):
    venda = _venda_com_item(db_session)

    xml_texto = xml_builder.montar_nfce_xml(venda, numero=42, serie=1)

    assert "42" in xml_texto
    raiz = ElementTree.fromstring(xml_texto)
    nnf = raiz.find(".//nfe:ide/nfe:nNF", NS)
    assert nnf.text == "42"
    serie_el = raiz.find(".//nfe:ide/nfe:serie", NS)
    assert serie_el.text == "1"


def test_montar_nfce_xml_mod_65_para_nfce(db_session):
    venda = _venda_com_item(db_session)

    xml_texto = xml_builder.montar_nfce_xml(venda, numero=1, serie=1)

    raiz = ElementTree.fromstring(xml_texto)
    mod = raiz.find(".//nfe:ide/nfe:mod", NS)
    assert mod.text == "65"


def test_montar_nfce_xml_usa_dados_do_emitente_configurado(db_session):
    venda = _venda_com_item(db_session)

    xml_texto = xml_builder.montar_nfce_xml(venda, numero=1, serie=1)

    raiz = ElementTree.fromstring(xml_texto)
    cnpj = raiz.find(".//nfe:emit/nfe:CNPJ", NS)
    assert cnpj.text == "26423780000176"
    x_nome = raiz.find(".//nfe:emit/nfe:xNome", NS)
    assert x_nome.text == "NANA LANCHES COMERCIO DE ALIMENTOS LTDA"


def test_montar_nfce_xml_omite_dest_para_consumidor_final(db_session):
    venda = _venda_com_item(db_session)

    xml_texto = xml_builder.montar_nfce_xml(venda, numero=1, serie=1)

    raiz = ElementTree.fromstring(xml_texto)
    assert raiz.find(".//nfe:dest", NS) is None


def test_montar_nfce_xml_inclui_dest_quando_cliente_identificado(db_session):
    cliente = Cliente(
        tipo_pessoa=TipoPessoa.PF,
        nome="Fulano de Tal",
        cpf_cnpj="11144477735",
        consumidor_final=False,
    )
    db_session.add(cliente)
    db_session.commit()
    produto = produtos_service.criar_produto(
        db_session,
        codigo_interno="2",
        nome="Suco",
        categoria_nome="Diversos",
        ncm="21069090",
        unidade="UN",
        preco_venda=Decimal("10.00"),
    )
    venda = vendas_service.criar_venda(db_session, cliente.id)
    vendas_service.adicionar_item(db_session, venda.id, produto.id, Decimal("1"))

    xml_texto = xml_builder.montar_nfce_xml(venda, numero=1, serie=1)

    raiz = ElementTree.fromstring(xml_texto)
    dest = raiz.find(".//nfe:dest", NS)
    assert dest is not None
    assert dest.find("nfe:CPF", NS).text == "11144477735"
    assert dest.find("nfe:xNome", NS).text == "Fulano de Tal"


def test_montar_nfce_xml_mapeia_forma_pagamento(db_session):
    venda = _venda_com_item(db_session)
    venda.forma_pagamento = "pix"
    db_session.commit()
    db_session.refresh(venda)

    xml_texto = xml_builder.montar_nfce_xml(venda, numero=1, serie=1)

    raiz = ElementTree.fromstring(xml_texto)
    tpag = raiz.find(".//nfe:pag/nfe:detPag/nfe:tPag", NS)
    assert tpag.text == "17"  # código Sefaz para PIX (mesma tabela do focus_nfe)


def test_montar_nfce_xml_nao_preenche_ibscbs_pendencia_registrada(db_session):
    """IBS/CBS (reforma tributária) é uma PENDÊNCIA aberta e documentada --
    ver docstring do módulo xml_builder e o relatório da task. Este teste
    apenas fixa o comportamento atual (grupo omitido) para que uma futura
    mudança intencional (preencher IBSCBS de verdade) precise atualizar este
    teste explicitamente, em vez de regredir silenciosamente."""
    venda = _venda_com_item(db_session)

    xml_texto = xml_builder.montar_nfce_xml(venda, numero=1, serie=1)

    assert "IBSCBS" not in xml_texto


def test_montar_nfce_xml_e_estruturalmente_valido_pelo_schema_da_nfelib(db_session):
    """Usa Nfe.schema_validation (CommonMixin, real -- ver referência da
    Task 1) para validar a saída contra o XSD oficial da NFe/NFC-e v4.00.

    O único erro esperado nesta etapa do pipeline é a ausência de
    `infNFeSupl`/`Signature` no elemento raiz `<NFe>` -- ambos são
    adicionados por etapas posteriores (Task 4: assinatura; Task 7: QR
    code), não por esta função. Qualquer OUTRO erro de schema indicaria um
    problema real na construção de ide/emit/dest/det/imposto/total/pag."""
    from nfelib.nfe.bindings.v4_0 import Nfe

    venda = _venda_com_item(db_session)
    xml_texto = xml_builder.montar_nfce_xml(venda, numero=1, serie=1)

    erros = Nfe.schema_validation(xml_texto)

    outros_erros = [e for e in erros if "infNFeSupl" not in e and "Signature" not in e]
    assert outros_erros == [], f"erros de schema inesperados: {outros_erros}"


def test_montar_nfce_xml_levanta_erro_claro_se_emitente_incompleto(db_session, monkeypatch):
    """Reprodução do achado do revisor: com EMITENTE_IE,
    EMITENTE_ENDERECO_BAIRRO e EMITENTE_ENDERECO_CEP em branco -- exatamente
    como .env.example os distribui -- montar_nfce_xml não deve retornar
    silenciosamente um XML bem-formado porém inválido pelo schema (xBairro
    abaixo do mínimo, CEP e IE fora do pattern). Deve falhar rápido com uma
    mensagem clara nomeando os campos faltantes."""
    monkeypatch.setattr(settings, "emitente_ie", "")
    monkeypatch.setattr(settings, "emitente_endereco_bairro", "")
    monkeypatch.setattr(settings, "emitente_endereco_cep", "")
    venda = _venda_com_item(db_session)

    with pytest.raises(ValueError) as exc_info:
        xml_builder.montar_nfce_xml(venda, numero=1, serie=1)

    mensagem = str(exc_info.value)
    assert "EMITENTE_IE" in mensagem
    assert "EMITENTE_ENDERECO_BAIRRO" in mensagem
    assert "EMITENTE_ENDERECO_CEP" in mensagem


def test_montar_nfce_xml_endereco_sem_numero_nao_e_tratado_como_faltante(db_session, monkeypatch):
    """`emitente_endereco_numero` em branco não deve disparar a validação de
    emitente incompleto -- _montar_emit já cai para "SN" (sem número) nesse
    caso, então não chega a produzir um campo obrigatório vazio no XML."""
    monkeypatch.setattr(settings, "emitente_endereco_numero", "")
    venda = _venda_com_item(db_session)

    xml_texto = xml_builder.montar_nfce_xml(venda, numero=1, serie=1)

    raiz = ElementTree.fromstring(xml_texto)
    nro = raiz.find(".//nfe:emit/nfe:enderEmit/nfe:nro", NS)
    assert nro.text == "SN"


def test_montar_nfce_xml_chave_de_acesso_tem_44_digitos_e_dv_correto(db_session):
    """Confirma que o DV (dígito verificador, módulo 11) da chave de acesso
    embutida em Id/cDV está matematicamente correto, usando o mesmo
    algoritmo confirmado contra a chave de acesso real do XML de amostra
    oficial da própria nfelib (ver docstring de
    xml_builder._calcular_dv_chave_acesso)."""
    venda = _venda_com_item(db_session)

    xml_texto = xml_builder.montar_nfce_xml(venda, numero=7, serie=1)

    raiz = ElementTree.fromstring(xml_texto)
    inf_nfe = raiz.find(".//nfe:infNFe", NS)
    chave = inf_nfe.attrib["Id"].replace("NFe", "")
    assert len(chave) == 44
    assert chave.isdigit()
    assert xml_builder._calcular_dv_chave_acesso(chave[:-1]) == chave[-1]
