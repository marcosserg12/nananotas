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
    monkeypatch.setattr(settings, "sefaz_csc_id", "1")
    monkeypatch.setattr(settings, "sefaz_csc_token", "ABCDEF0123456789ABCDEF0123456789")
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
    `Signature` no elemento raiz `<NFe>` -- adicionada por uma etapa
    posterior (Task 4: assinatura), não por esta função. `infNFeSupl` NÃO
    entra mais nesse filtro (correção da revisão final do branch: este
    grupo obrigatório agora é preenchido por `montar_nfce_xml` -- ver
    `test_montar_nfce_xml_inclui_infnfesupl_com_qrcode_obrigatorio` abaixo).
    Qualquer OUTRO erro de schema indicaria um problema real na construção
    de ide/emit/dest/det/imposto/total/pag/infNFeSupl."""
    from nfelib.nfe.bindings.v4_0 import Nfe

    venda = _venda_com_item(db_session)
    xml_texto = xml_builder.montar_nfce_xml(venda, numero=1, serie=1)

    erros = Nfe.schema_validation(xml_texto)

    outros_erros = [e for e in erros if "Signature" not in e]
    assert outros_erros == [], f"erros de schema inesperados: {outros_erros}"


def test_montar_nfce_xml_inclui_infnfesupl_com_qrcode_obrigatorio(db_session):
    """Critical #1 da revisão final do branch: `infNFeSupl`/`qrCode` é
    obrigatório em NFC-e (a razão de existir do CSC) e antes não era
    preenchido -- toda submissão real ficava sem esse grupo. Confirma que
    `montar_nfce_xml` agora monta `infNFeSupl` com uma URL de QR Code
    não-vazia contendo a chave de acesso, e `urlChave` preenchido."""
    venda = _venda_com_item(db_session)

    xml_texto = xml_builder.montar_nfce_xml(venda, numero=1, serie=1)

    raiz = ElementTree.fromstring(xml_texto)
    inf_nfe_supl = raiz.find(".//nfe:infNFeSupl", NS)
    assert inf_nfe_supl is not None

    qrcode_el = inf_nfe_supl.find("nfe:qrCode", NS)
    assert qrcode_el is not None
    assert qrcode_el.text
    assert qrcode_el.text.startswith("http")
    assert "p=" in qrcode_el.text

    inf_nfe = raiz.find(".//nfe:infNFe", NS)
    chave = inf_nfe.attrib["Id"].replace("NFe", "")
    assert chave in qrcode_el.text

    url_chave_el = inf_nfe_supl.find("nfe:urlChave", NS)
    assert url_chave_el is not None
    assert url_chave_el.text


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


def test_montar_nfce_xml_vpag_e_vnf_concordam_mesmo_com_valor_total_divergente(db_session):
    """Important #7 da revisão final do branch: `_montar_pag` antes usava
    `venda.valor_total` diretamente para `vPag` -- calculado por
    `vendas_service.recalcular_total` somando `quantidade * preco_unitario`
    SEM quantizar por item antes de gravar (colunas `Numeric(10,2)`, mas o
    produto pode carregar até 4 casas decimais antes de ser arredondado no
    armazenamento), enquanto `vNF` (em `_montar_total`) soma os `vProd` já
    quantizados por item -- os dois podiam divergir em um centavo, e Sefaz
    rejeita quando a soma de `vPag` não bate com `vNF`.

    Prova o fix corrompendo deliberadamente `venda.valor_total` em memória
    (simulando exatamente esse tipo de divergência de um centavo que
    `recalcular_total` podia produzir) e confirmando que `vPag` e `vNF` do
    XML gerado CONTINUAM idênticos, e iguais ao valor correto (soma dos
    `vProd` por item) -- porque `_montar_pag` não lê mais `venda.valor_total`
    de jeito nenhum, e sim o mesmo `Decimal` já quantizado que
    `_montar_total` usa. Os dois concordam por construção, não porque
    `venda.valor_total` calhou de estar certo."""
    venda = _venda_com_item(db_session)  # 2 unidades a 15.00 = 30.00 (vProd corretamente quantizado)
    assert venda.valor_total == Decimal("30.00")

    # Divergência deliberada de 1 centavo -- o tipo de valor "quase certo"
    # que o cálculo naive (sem quantizar por item) de recalcular_total podia
    # produzir em memória antes de um reload.
    venda.valor_total = Decimal("30.01")

    xml_texto = xml_builder.montar_nfce_xml(venda, numero=1, serie=1)

    raiz = ElementTree.fromstring(xml_texto)
    v_nf = raiz.find(".//nfe:total/nfe:ICMSTot/nfe:vNF", NS).text
    v_pag = raiz.find(".//nfe:pag/nfe:detPag/nfe:vPag", NS).text

    assert v_nf == "30.00"  # correto: soma dos vProd por item, ignora o valor_total corrompido
    assert v_pag == "30.00"
    assert v_pag == v_nf


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
