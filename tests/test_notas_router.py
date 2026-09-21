from decimal import Decimal

import pytest

from app.database import get_db
from app.dependencies import get_fiscal_provider
from app.main import app
from app.models.cliente import TipoPessoa
from app.models.nota_fiscal import NotaFiscal
from app.services.fiscal.base import FiscalProvider, ResultadoFiscal
from app.services import clientes_service, email_service, parcelas_service, produtos_service, vendas_service


class FiscalProviderFalso(FiscalProvider):
    def __init__(self):
        self.emitidas = []
        self.canceladas = []

    def emitir(self, venda):
        self.emitidas.append(venda.id)
        return ResultadoFiscal(
            referencia=f"venda-{venda.id}",
            status="autorizada",
            numero="1",
            serie="1",
            chave_acesso="1" * 44,
            protocolo="abc123",
            url_danfe="https://exemplo.com/danfe/1",
        )

    def consultar(self, referencia):
        return ResultadoFiscal(referencia=referencia, status="autorizada", numero="1")

    def cancelar(self, referencia, motivo):
        self.canceladas.append((referencia, motivo))
        return ResultadoFiscal(referencia=referencia, status="cancelada")


class FiscalProviderFalsoCancelarNaoImplementado(FiscalProvider):
    """Fake provider mimicking `SefazDiretoProvider.cancelar`, which raises
    `NotImplementedError` because the cancellation-event XML builder doesn't
    exist yet (see `app/services/fiscal/sefaz_direto/provider.py`). Used to
    confirm the router/service layer turns that into a clean error response
    instead of an unhandled 500."""

    def emitir(self, venda):
        return ResultadoFiscal(
            referencia=f"venda-{venda.id}",
            status="autorizada",
            numero="1",
            serie="1",
            chave_acesso="1" * 44,
            protocolo="abc123",
            url_danfe="https://exemplo.com/danfe/1",
        )

    def consultar(self, referencia):
        return ResultadoFiscal(referencia=referencia, status="autorizada", numero="1")

    def cancelar(self, referencia, motivo):
        raise NotImplementedError("SefazDiretoProvider.cancelar ainda não está implementado")


class FiscalProviderFalsoRejeitando(FiscalProvider):
    """Fake provider cujo `emitir` sempre devolve "rejeitada" -- usado para
    testar o caminho de retentativa de uma nota rejeitada em nota.html
    (Important #5)."""

    def emitir(self, venda):
        return ResultadoFiscal(
            referencia=f"venda-{venda.id}", status="rejeitada", mensagem_erro="Rejeicao: Falha no Schema XML"
        )

    def consultar(self, referencia):
        raise NotImplementedError

    def cancelar(self, referencia, motivo):
        raise NotImplementedError


class FiscalProviderFalsoComFalhaTransitoriaNaConsulta(FiscalProvider):
    """Fake provider cujo `consultar` simula uma falha transitória (ex.: erro
    de rede) -- não sabe a chave de acesso/protocolo da nota, então devolve
    None para ambos, como `SefazDiretoProvider.consultar` faz em seus ramos
    de erro. Usado para reproduzir o achado do Important #6: uma falha
    transitória ao consultar não pode apagar a chave/protocolo reais já
    persistidos de uma nota já autorizada."""

    def emitir(self, venda):
        raise NotImplementedError  # não usado neste teste -- emissão via FiscalProviderFalso

    def consultar(self, referencia):
        return ResultadoFiscal(
            referencia=referencia,
            status="rejeitada",
            mensagem_erro="Falha de comunicação com a Sefaz: timeout",
        )

    def cancelar(self, referencia, motivo):
        raise NotImplementedError


class FiscalProviderFalsoDuasEtapas(FiscalProvider):
    """Fake provider whose first `emitir` call comes back "processando" and whose
    second comes back "autorizada" — used to exercise the create-then-update path
    of `notas_service.emitir_nota` when a note is re-emitted for the same venda."""

    def __init__(self):
        self.chamadas = 0

    def emitir(self, venda):
        self.chamadas += 1
        if self.chamadas == 1:
            return ResultadoFiscal(referencia=f"venda-{venda.id}", status="processando")
        return ResultadoFiscal(
            referencia=f"venda-{venda.id}",
            status="autorizada",
            numero="2",
            serie="1",
            chave_acesso="2" * 44,
            protocolo="def456",
            url_danfe="https://exemplo.com/danfe/2",
        )

    def consultar(self, referencia):
        raise NotImplementedError

    def cancelar(self, referencia, motivo):
        raise NotImplementedError


@pytest.fixture()
def venda_paga(db_session):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Lanche", categoria_nome="Diversos",
        ncm="21069090", unidade="UN", preco_venda=Decimal("10.00"), estoque_atual=Decimal("5"),
    )
    venda = vendas_service.criar_venda(db_session, cliente.id)
    vendas_service.adicionar_item(db_session, venda.id, produto.id, Decimal("1"))
    parcelas_service.gerar_parcelas(db_session, venda.id, "dinheiro", 1)
    parcelas_service.confirmar_venda(db_session, venda.id, Decimal("10.00"))
    return venda


@pytest.fixture()
def venda_nao_paga(db_session):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="2", nome="Refrigerante", categoria_nome="Diversos",
        ncm="22021000", unidade="UN", preco_venda=Decimal("5.00"), estoque_atual=Decimal("5"),
    )
    venda = vendas_service.criar_venda(db_session, cliente.id)
    vendas_service.adicionar_item(db_session, venda.id, produto.id, Decimal("1"))
    return venda


@pytest.fixture()
def authed_client_com_provider_falso(authed_client, db_session):
    provider_falso = FiscalProviderFalso()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_fiscal_provider] = lambda: provider_falso
    yield authed_client, provider_falso
    del app.dependency_overrides[get_fiscal_provider]


class FiscalProviderFalsoComNomeProvedor(FiscalProvider):
    """Fake provider que declara `NOME_PROVEDOR` (mesmo mecanismo exposto por
    `SefazDiretoProvider.NOME_PROVEDOR`), para testar o wiring de
    `notas_service.emitir_nota` sem depender do `SefazDiretoProvider` real
    (que exigiria certificado/CSC/webservice mockados) -- o ponto sob teste
    é só "o `provedor` da nota é preenchido a partir do atributo do
    provider", não o `SefazDiretoProvider` em si (já coberto por
    `tests/test_sefaz_direto_provider.py`)."""

    NOME_PROVEDOR = "sefaz_direto"

    def emitir(self, venda):
        return ResultadoFiscal(referencia=f"venda-{venda.id}", status="autorizada", numero="1", serie="1")

    def consultar(self, referencia):
        raise NotImplementedError

    def cancelar(self, referencia, motivo):
        raise NotImplementedError


def test_emitir_nota_marca_provedor_a_partir_do_nome_provedor_do_provider(
    authed_client_com_provider_falso, venda_paga, db_session
):
    """Bundle item da revisão final do branch: `NotaFiscal.provedor` tem
    default "focus_nfe" no model e `_aplicar_resultado` nunca o alterava --
    notas emitidas pela integração direta com a Sefaz ficavam mal rotuladas
    no banco. Confirma que `emitir_nota` grava `provedor` a partir do
    atributo `NOME_PROVEDOR` do provider ativo quando ele existe, e mantém o
    default para providers que não o declaram (ex.: `FiscalProviderFalso`,
    usado nos demais testes deste arquivo).

    Usa duas vendas distintas (uma por provider) em vez de emitir duas vezes
    para a mesma venda -- depois do achado da auditoria geral (ver teste
    `test_emitir_nota_ja_autorizada_e_bloqueado...`), emitir de novo para uma
    venda que já tem nota com chave de acesso é bloqueado de propósito."""
    client, _ = authed_client_com_provider_falso
    client.post(f"/vendas/{venda_paga.id}/nota/emitir")
    nota = db_session.query(NotaFiscal).filter(NotaFiscal.venda_id == venda_paga.id).first()
    assert nota.provedor == "focus_nfe"  # default do model, provider fake não declara NOME_PROVEDOR

    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="9", nome="Suco", categoria_nome="Diversos",
        ncm="21069090", unidade="UN", preco_venda=Decimal("5.00"), estoque_atual=Decimal("5"),
    )
    outra_venda = vendas_service.criar_venda(db_session, cliente.id)
    vendas_service.adicionar_item(db_session, outra_venda.id, produto.id, Decimal("1"))
    parcelas_service.confirmar_venda(db_session, outra_venda.id, Decimal("5.00"))

    app.dependency_overrides[get_fiscal_provider] = lambda: FiscalProviderFalsoComNomeProvedor()
    client.post(f"/vendas/{outra_venda.id}/nota/emitir")

    outra_nota = db_session.query(NotaFiscal).filter(NotaFiscal.venda_id == outra_venda.id).first()
    assert outra_nota.provedor == "sefaz_direto"


def test_emitir_nota_grava_dados_retornados_pelo_provedor(authed_client_com_provider_falso, venda_paga):
    client, provider_falso = authed_client_com_provider_falso

    response = client.post(f"/vendas/{venda_paga.id}/nota/emitir", follow_redirects=False)

    assert response.status_code == 303
    assert provider_falso.emitidas == [venda_paga.id]

    pagina = client.get(f"/vendas/{venda_paga.id}/nota")
    assert "autorizada" in pagina.text
    assert "https://exemplo.com/danfe/1" in pagina.text


def test_emitir_nota_ja_autorizada_e_bloqueado_nao_emite_uma_segunda_nota_real(
    authed_client_com_provider_falso, venda_paga
):
    """Achado da auditoria geral: nada impedia um duplo-post (duplo clique,
    F5 num form, retry de rede) de chamar `emitir_nota` outra vez para uma
    venda que já tinha nota autorizada -- o `SefazDiretoProvider` real
    trataria isso como uma emissão nova de verdade (número novo, XML novo),
    criando uma segunda NFC-e real pra mesma venda. A tela só escondia o
    botão, o que não protege contra um post direto na rota."""
    client, provider_falso = authed_client_com_provider_falso
    primeira = client.post(f"/vendas/{venda_paga.id}/nota/emitir", follow_redirects=False)
    assert primeira.status_code == 303
    assert provider_falso.emitidas == [venda_paga.id]

    segunda = client.post(f"/vendas/{venda_paga.id}/nota/emitir", follow_redirects=False)

    assert segunda.status_code == 400
    assert "segunda nota fiscal real" in segunda.text
    assert provider_falso.emitidas == [venda_paga.id]  # não chamou o provedor de novo


@pytest.fixture()
def venda_paga_cliente_com_email(db_session):
    cliente = clientes_service.criar_cliente(
        db_session, tipo_pessoa=TipoPessoa.PF, nome="Cliente Com Email", email="cliente@exemplo.com",
    )
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="3", nome="Combo", categoria_nome="Diversos",
        ncm="21069090", unidade="UN", preco_venda=Decimal("20.00"), estoque_atual=Decimal("5"),
    )
    venda = vendas_service.criar_venda(db_session, cliente.id)
    vendas_service.adicionar_item(db_session, venda.id, produto.id, Decimal("1"))
    parcelas_service.gerar_parcelas(db_session, venda.id, "dinheiro", 1)
    parcelas_service.confirmar_venda(db_session, venda.id, Decimal("20.00"))
    return venda


def test_emitir_nota_envia_email_automaticamente_quando_cliente_tem_email(
    authed_client_com_provider_falso, venda_paga_cliente_com_email, monkeypatch
):
    client, _ = authed_client_com_provider_falso
    chamadas = []
    monkeypatch.setattr(email_service, "enviar_nota_por_email", lambda v, n: chamadas.append(v.id))

    client.post(f"/vendas/{venda_paga_cliente_com_email.id}/nota/emitir")

    assert chamadas == [venda_paga_cliente_com_email.id]
    pagina = client.get(f"/vendas/{venda_paga_cliente_com_email.id}/nota")
    assert "Cupom enviado por e-mail" in pagina.text


def test_emitir_nota_sem_email_do_cliente_nao_quebra_a_emissao(authed_client_com_provider_falso, venda_paga):
    """`venda_paga` usa o cliente "AO CONSUMIDOR" (sem e-mail) -- confirma
    que a tentativa automática de envio (melhor esforço) não derruba a
    emissão, que já teve sucesso."""
    client, provider_falso = authed_client_com_provider_falso

    response = client.post(f"/vendas/{venda_paga.id}/nota/emitir", follow_redirects=False)

    assert response.status_code == 303
    assert provider_falso.emitidas == [venda_paga.id]


def test_reenviar_email_sem_login_redireciona(client, venda_paga):
    response = client.post(f"/vendas/{venda_paga.id}/nota/reenviar-email", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_reenviar_email_com_sucesso_redireciona_com_flag_de_sucesso(
    authed_client_com_provider_falso, venda_paga_cliente_com_email, monkeypatch
):
    client, _ = authed_client_com_provider_falso
    monkeypatch.setattr(email_service, "enviar_nota_por_email", lambda v, n: None)
    client.post(f"/vendas/{venda_paga_cliente_com_email.id}/nota/emitir")

    response = client.post(
        f"/vendas/{venda_paga_cliente_com_email.id}/nota/reenviar-email", follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/vendas/{venda_paga_cliente_com_email.id}/nota?email_enviado=1"


def test_reenviar_email_sem_nota_autorizada_retorna_400(authed_client_com_provider_falso, venda_paga):
    client, _ = authed_client_com_provider_falso

    response = client.post(f"/vendas/{venda_paga.id}/nota/reenviar-email", follow_redirects=False)

    assert response.status_code == 400


def test_cancelar_nota_chama_provedor_com_motivo(authed_client_com_provider_falso, venda_paga):
    client, provider_falso = authed_client_com_provider_falso
    client.post(f"/vendas/{venda_paga.id}/nota/emitir")

    response = client.post(
        f"/vendas/{venda_paga.id}/nota/cancelar",
        data={"motivo": "Erro de digitação"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert provider_falso.canceladas == [(f"venda-{venda_paga.id}", "Erro de digitação")]


def test_consultar_nota_inexistente_retorna_400(authed_client_com_provider_falso, venda_paga):
    client, _ = authed_client_com_provider_falso

    response = client.post(f"/vendas/{venda_paga.id}/nota/consultar", follow_redirects=False)

    assert response.status_code == 400


def test_emitir_nota_com_venda_nao_paga_retorna_400(authed_client_com_provider_falso, venda_nao_paga):
    client, provider_falso = authed_client_com_provider_falso

    response = client.post(f"/vendas/{venda_nao_paga.id}/nota/emitir", follow_redirects=False)

    assert response.status_code == 400
    assert provider_falso.emitidas == []


def test_cancelar_nota_ja_cancelada_retorna_400(authed_client_com_provider_falso, venda_paga):
    client, provider_falso = authed_client_com_provider_falso
    client.post(f"/vendas/{venda_paga.id}/nota/emitir")
    client.post(f"/vendas/{venda_paga.id}/nota/cancelar", data={"motivo": "Erro de digitação"})

    response = client.post(
        f"/vendas/{venda_paga.id}/nota/cancelar",
        data={"motivo": "Tentativa de cancelamento duplicada"},
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert provider_falso.canceladas == [(f"venda-{venda_paga.id}", "Erro de digitação")]


def test_cancelar_nota_com_provedor_sem_suporte_retorna_erro_limpo(authed_client_com_provider_falso, venda_paga):
    client, _ = authed_client_com_provider_falso
    provider_sem_cancelar = FiscalProviderFalsoCancelarNaoImplementado()
    app.dependency_overrides[get_fiscal_provider] = lambda: provider_sem_cancelar
    client.post(f"/vendas/{venda_paga.id}/nota/emitir")

    response = client.post(
        f"/vendas/{venda_paga.id}/nota/cancelar",
        data={"motivo": "Erro de digitação"},
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "ainda não está disponível" in response.text


def test_listar_notas_mostra_notas_emitidas_com_link_de_impressao(authed_client_com_provider_falso, venda_paga):
    client, _ = authed_client_com_provider_falso
    client.post(f"/vendas/{venda_paga.id}/nota/emitir")

    response = client.get("/vendas/notas")

    assert response.status_code == 200
    assert str(venda_paga.numero_orcamento) in response.text
    assert "autorizada" in response.text
    assert f'href="/vendas/{venda_paga.id}/nota/danfe"' in response.text


def test_listar_notas_sem_chave_de_acesso_nao_mostra_link_de_impressao(
    authed_client_com_provider_falso, venda_paga
):
    client, _ = authed_client_com_provider_falso
    app.dependency_overrides[get_fiscal_provider] = lambda: FiscalProviderFalsoRejeitando()
    client.post(f"/vendas/{venda_paga.id}/nota/emitir")

    response = client.get("/vendas/notas")

    assert response.status_code == 200
    assert f'href="/vendas/{venda_paga.id}/nota/danfe"' not in response.text


def test_listar_notas_vazia_mostra_mensagem(authed_client_com_provider_falso):
    client, _ = authed_client_com_provider_falso

    response = client.get("/vendas/notas")

    assert response.status_code == 200
    assert "Nenhuma nota fiscal emitida ainda." in response.text


def test_listar_notas_mostra_data_hora_convertida_para_brasilia(
    authed_client_com_provider_falso, venda_paga, db_session
):
    from datetime import datetime

    client, _ = authed_client_com_provider_falso
    client.post(f"/vendas/{venda_paga.id}/nota/emitir")

    nota = db_session.query(NotaFiscal).filter(NotaFiscal.venda_id == venda_paga.id).first()
    nota.autorizado_em = datetime(2026, 9, 18, 14, 30)
    db_session.commit()

    response = client.get("/vendas/notas")

    assert "18/09/2026 11:30" in response.text
    assert "14:30" not in response.text


def test_listar_notas_filtra_por_cliente(authed_client_com_provider_falso, venda_paga, db_session):
    from app.models.cliente import TipoPessoa
    from app.services import clientes_service, parcelas_service, produtos_service, vendas_service

    client, _ = authed_client_com_provider_falso
    client.post(f"/vendas/{venda_paga.id}/nota/emitir")  # cliente "AO CONSUMIDOR"

    outro_cliente = clientes_service.criar_cliente(db_session, tipo_pessoa=TipoPessoa.PF, nome="Carlos Pereira")
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="9", nome="Suco", categoria_nome="Diversos",
        ncm="21069090", unidade="UN", preco_venda=Decimal("5.00"), estoque_atual=Decimal("5"),
    )
    outra_venda = vendas_service.criar_venda(db_session, outro_cliente.id)
    vendas_service.adicionar_item(db_session, outra_venda.id, produto.id, Decimal("1"))
    parcelas_service.confirmar_venda(db_session, outra_venda.id, Decimal("5.00"))
    client.post(f"/vendas/{outra_venda.id}/nota/emitir")

    response = client.get("/vendas/notas", params={"cliente": "Carlos"})

    assert response.status_code == 200
    assert "Carlos Pereira" in response.text
    assert "AO CONSUMIDOR" not in response.text


def test_listar_notas_com_data_invalida_retorna_400(authed_client_com_provider_falso):
    client, _ = authed_client_com_provider_falso

    response = client.get("/vendas/notas", params={"data": "não-é-uma-data"})

    assert response.status_code == 400


def test_listar_notas_mantem_filtro_preenchido_no_formulario(authed_client_com_provider_falso):
    client, _ = authed_client_com_provider_falso

    response = client.get("/vendas/notas", params={"cliente": "Carlos", "data": "2026-09-18"})

    assert response.status_code == 200
    assert 'value="Carlos"' in response.text
    assert 'value="2026-09-18"' in response.text
    assert "Limpar filtro" in response.text


def test_pagina_da_nota_nao_menciona_mais_sebrae(authed_client_com_provider_falso, venda_paga):
    """Regressão: a tela chegou a mostrar, como caminho principal, um resumo
    "pra digitar no Emissor Gratuito do SEBRAE" com um link externo -- resto
    de uma versão anterior do sistema, de antes da integração direta com a
    Sefaz existir. O caminho principal agora é sempre emitir direto."""
    client, _ = authed_client_com_provider_falso

    response = client.get(f"/vendas/{venda_paga.id}/nota")

    assert "SEBRAE" not in response.text
    assert "sebrae.com.br" not in response.text


def test_pagina_da_nota_promove_gerar_cupom_fiscal_como_acao_principal(authed_client_com_provider_falso, venda_paga):
    client, _ = authed_client_com_provider_falso

    response = client.get(f"/vendas/{venda_paga.id}/nota")

    assert response.status_code == 200
    assert "Resumo da venda" in response.text
    assert "Gerar Cupom Fiscal" in response.text
    assert f'action="/vendas/{venda_paga.id}/nota/emitir"' in response.text
    assert f'href="/vendas/{venda_paga.id}"' in response.text  # botão Voltar


def test_pagina_da_nota_antes_de_emitir_nao_oferece_excluir_e_aponta_para_orcamentos(
    authed_client_com_provider_falso, venda_paga
):
    """A exclusão de uma venda ainda não faturada agora se faz na tela
    separada de Orçamentos, não misturada com as ações de emissão fiscal
    -- ver /vendas/orcamentos."""
    client, _ = authed_client_com_provider_falso

    response = client.get(f"/vendas/{venda_paga.id}/nota")

    assert response.status_code == 200
    assert f'action="/vendas/{venda_paga.id}/excluir"' not in response.text
    assert 'href="/vendas/orcamentos"' in response.text


def test_pagina_da_nota_autorizada_explica_que_nao_pode_mais_excluir(authed_client_com_provider_falso, venda_paga):
    client, _ = authed_client_com_provider_falso
    client.post(f"/vendas/{venda_paga.id}/nota/emitir")

    response = client.get(f"/vendas/{venda_paga.id}/nota")

    assert response.status_code == 200
    assert f'action="/vendas/{venda_paga.id}/excluir"' not in response.text
    assert "não pode mais ser excluída" in response.text
    assert "Cancelar nota" in response.text


def test_pagina_da_nota_mostra_bandeira_quando_pagamento_em_cartao(authed_client_com_provider_falso, venda_paga, db_session):
    client, _ = authed_client_com_provider_falso
    venda_paga.forma_pagamento = "cartao_credito"
    venda_paga.bandeira = "06"
    db_session.commit()

    response = client.get(f"/vendas/{venda_paga.id}/nota")

    assert "Elo" in response.text


def test_pagina_da_nota_mostra_as_parcelas_geradas(authed_client_com_provider_falso, venda_paga):
    client, _ = authed_client_com_provider_falso

    response = client.get(f"/vendas/{venda_paga.id}/nota")

    assert response.status_code == 200
    assert "dinheiro" in response.text
    assert "10.00" in response.text
    assert "Em aberto" in response.text


def test_pagina_da_nota_sem_parcelas_nao_mostra_a_tabela(authed_client_com_provider_falso, venda_nao_paga):
    client, _ = authed_client_com_provider_falso

    response = client.get(f"/vendas/{venda_nao_paga.id}/nota")

    assert response.status_code == 200
    assert "Vencimento" not in response.text


def test_marcar_nota_emitida_manualmente_com_chave_de_acesso(authed_client_com_provider_falso, venda_paga):
    client, provider_falso = authed_client_com_provider_falso

    response = client.post(
        f"/vendas/{venda_paga.id}/nota/marcar-manual",
        data={"chave_acesso": "1" * 44},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert provider_falso.emitidas == []

    pagina = client.get(f"/vendas/{venda_paga.id}/nota")
    assert "autorizada" in pagina.text
    assert "1" * 44 in pagina.text
    assert "manualmente" in pagina.text


def test_marcar_nota_emitida_manualmente_sem_chave_tambem_funciona(authed_client_com_provider_falso, venda_paga):
    client, _ = authed_client_com_provider_falso

    response = client.post(f"/vendas/{venda_paga.id}/nota/marcar-manual", follow_redirects=False)

    assert response.status_code == 303

    pagina = client.get(f"/vendas/{venda_paga.id}/nota")
    assert "autorizada" in pagina.text


def test_marcar_nota_emitida_manualmente_em_venda_nao_paga_retorna_400(authed_client_com_provider_falso, venda_nao_paga):
    client, _ = authed_client_com_provider_falso

    response = client.post(f"/vendas/{venda_nao_paga.id}/nota/marcar-manual", follow_redirects=False)

    assert response.status_code == 400


def test_ver_danfe_com_nota_autorizada_devolve_pdf(authed_client_com_provider_falso, venda_paga):
    """Regressão: a tela do cupom era uma página HTML dentro do próprio site
    (herdando o menu/nav do app) -- agora é um PDF de verdade, aberto
    diretamente pelo navegador, igual ao DANFE do sistema anterior."""
    client, _ = authed_client_com_provider_falso
    client.post(f"/vendas/{venda_paga.id}/nota/emitir")

    response = client.get(f"/vendas/{venda_paga.id}/nota/danfe")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")


def test_ver_danfe_sem_nota_autorizada_retorna_404(authed_client_com_provider_falso, venda_paga):
    client, _ = authed_client_com_provider_falso

    response = client.get(f"/vendas/{venda_paga.id}/nota/danfe")

    assert response.status_code == 404


def test_pagina_da_nota_rejeitada_mostra_formulario_de_retentativa_e_mensagem_de_erro(
    authed_client_com_provider_falso, venda_paga
):
    """Important #5 da revisão final do branch: `nota.html` só mostrava o
    formulário/botão de emissão quando `nota is none` -- uma nota já com
    status "rejeitada" ficava sem NENHUM caminho de UI para tentar de novo
    (o botão "Atualizar status" chama `consultar`, que precisa de uma
    `chave_acesso` que uma nota rejeitada nunca teve). Confirma que a página
    agora mostra o formulário de emissão (retentativa) e a mensagem de erro
    da tentativa anterior quando a nota está rejeitada."""
    client, _ = authed_client_com_provider_falso
    app.dependency_overrides[get_fiscal_provider] = lambda: FiscalProviderFalsoRejeitando()

    client.post(f"/vendas/{venda_paga.id}/nota/emitir")
    pagina = client.get(f"/vendas/{venda_paga.id}/nota")

    assert pagina.status_code == 200
    assert "rejeitada" in pagina.text
    assert "Falha no Schema" in pagina.text  # mensagem_erro da tentativa anterior, visível para quem for retentar
    assert f'/vendas/{venda_paga.id}/nota/emitir' in pagina.text  # formulário de retentativa presente


def test_consultar_nota_com_falha_transitoria_preserva_chave_e_protocolo_ja_persistidos(
    authed_client_com_provider_falso, venda_paga, db_session
):
    """Important #6 da revisão final do branch: `_aplicar_resultado` (em
    `notas_service.py`) sobrescrevia incondicionalmente `chave_acesso`/
    `protocolo` com o que o `ResultadoFiscal` trouxesse -- inclusive `None`
    nos ramos de erro de `SefazDiretoProvider.consultar`. Uma falha
    transitória (ex.: blip de rede) ao consultar uma nota JÁ autorizada
    apagava permanentemente a chave/protocolo reais dela. Confirma que isso
    não acontece mais: só `status`/`mensagem_erro` refletem a falha."""
    client, _ = authed_client_com_provider_falso
    client.post(f"/vendas/{venda_paga.id}/nota/emitir")

    nota = db_session.query(NotaFiscal).filter(NotaFiscal.venda_id == venda_paga.id).first()
    assert nota.chave_acesso == "1" * 44
    assert nota.protocolo == "abc123"

    app.dependency_overrides[get_fiscal_provider] = lambda: FiscalProviderFalsoComFalhaTransitoriaNaConsulta()
    response = client.post(f"/vendas/{venda_paga.id}/nota/consultar", follow_redirects=False)
    assert response.status_code == 303

    db_session.refresh(nota)
    assert nota.chave_acesso == "1" * 44  # preservado, não apagado
    assert nota.protocolo == "abc123"  # preservado, não apagado
    assert nota.status.value == "rejeitada"  # status reflete a falha mais recente, nunca "pendente" silenciosamente
    assert nota.mensagem_erro


def test_emitir_nota_duas_vezes_atualiza_registro_existente_em_vez_de_duplicar(
    authed_client_com_provider_falso, venda_paga, db_session
):
    client, _ = authed_client_com_provider_falso
    provider_duas_etapas = FiscalProviderFalsoDuasEtapas()
    app.dependency_overrides[get_fiscal_provider] = lambda: provider_duas_etapas

    primeira = client.post(f"/vendas/{venda_paga.id}/nota/emitir", follow_redirects=False)
    segunda = client.post(f"/vendas/{venda_paga.id}/nota/emitir", follow_redirects=False)

    assert primeira.status_code == 303
    assert segunda.status_code == 303
    assert provider_duas_etapas.chamadas == 2

    notas = db_session.query(NotaFiscal).filter(NotaFiscal.venda_id == venda_paga.id).all()
    assert len(notas) == 1
    assert notas[0].status.value == "autorizada"
    assert notas[0].numero == "2"


class FiscalProviderFalsoConsultaSemUrlDanfe(FiscalProvider):
    """Fake provider cujo `consultar` reflete `SefazDiretoProvider.consultar`
    na parte que motivou o Important #1 da re-revisão do fix wave final:
    devolve `status="autorizada"` mas SEM `url_danfe` (essa integração não
    recebe um link externo de DANFE de nenhum provedor -- o link é sempre o
    da própria rota `/nota/danfe` deste app, atribuído só no `emitir`)."""

    def emitir(self, venda):
        return ResultadoFiscal(
            referencia=f"venda-{venda.id}",
            status="autorizada",
            numero="1",
            serie="1",
            chave_acesso="1" * 44,
            protocolo="abc123",
            url_danfe=f"/vendas/{venda.id}/nota/danfe",
        )

    def consultar(self, referencia):
        return ResultadoFiscal(referencia=referencia, status="autorizada", numero="1")

    def cancelar(self, referencia, motivo):
        raise NotImplementedError


def test_consultar_com_sucesso_nao_apaga_url_danfe_ja_gravado(authed_client_com_provider_falso, venda_paga):
    """Regressão do Important #1 encontrado na re-revisão do fix wave final:
    `_aplicar_resultado` sobrescrevia `nota.url_danfe` incondicionalmente, e
    como `SefazDiretoProvider.consultar` nunca preenche esse campo, o link
    "Imprimir cupom" desaparecia pra sempre no primeiro clique em "Atualizar
    status" -- mesmo numa consulta bem-sucedida."""
    client, _ = authed_client_com_provider_falso
    app.dependency_overrides[get_fiscal_provider] = lambda: FiscalProviderFalsoConsultaSemUrlDanfe()

    client.post(f"/vendas/{venda_paga.id}/nota/emitir")
    pagina_apos_emitir = client.get(f"/vendas/{venda_paga.id}/nota")
    assert "Imprimir cupom" in pagina_apos_emitir.text

    client.post(f"/vendas/{venda_paga.id}/nota/consultar")
    pagina_apos_consultar = client.get(f"/vendas/{venda_paga.id}/nota")

    assert "Imprimir cupom" in pagina_apos_consultar.text


class FiscalProviderFalsoFalhaTransitoriaNaConsulta(FiscalProvider):
    """Fake provider cujo `consultar` simula uma falha transitória de rede
    (retorna `status="rejeitada"` sem chave/protocolo) -- o mesmo formato
    que `SefazDiretoProvider.consultar` devolve nesse caso, per Important #6
    da revisão final do branch."""

    def emitir(self, venda):
        return ResultadoFiscal(
            referencia=f"venda-{venda.id}",
            status="autorizada",
            numero="1",
            serie="1",
            chave_acesso="1" * 44,
            protocolo="abc123",
            url_danfe=f"/vendas/{venda.id}/nota/danfe",
        )

    def consultar(self, referencia):
        return ResultadoFiscal(referencia=referencia, status="rejeitada", mensagem_erro="Falha de conexão: timeout")

    def cancelar(self, referencia, motivo):
        raise NotImplementedError


def test_falha_transitoria_na_consulta_nao_oferece_emitir_nota_de_novo(authed_client_com_provider_falso, venda_paga):
    """Regressão do Important #2 encontrado na re-revisão do fix wave final:
    a condição de retry do template ('nota is none or status == rejeitada')
    reagia também a uma nota já AUTORIZADA que só falhou transitoriamente ao
    consultar -- oferecendo "emitir de novo" pra uma venda que já tinha uma
    NFC-e válida, arriscando duplicar a nota. A condição precisa considerar
    que uma nota "rejeitada" com `chave_acesso` preenchida já foi autorizada
    de verdade em algum momento e não deve ser re-emitida."""
    client, _ = authed_client_com_provider_falso
    app.dependency_overrides[get_fiscal_provider] = lambda: FiscalProviderFalsoFalhaTransitoriaNaConsulta()

    client.post(f"/vendas/{venda_paga.id}/nota/emitir")
    client.post(f"/vendas/{venda_paga.id}/nota/consultar")
    pagina = client.get(f"/vendas/{venda_paga.id}/nota")

    assert "Chave de acesso" in pagina.text
    assert "Atualizar status" in pagina.text
    assert "Gerar Cupom Fiscal" not in pagina.text
