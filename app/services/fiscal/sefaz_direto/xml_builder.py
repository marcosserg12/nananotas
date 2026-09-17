"""Monta o XML (não assinado) da NFC-e a partir de uma `Venda`.

As classes usadas aqui vêm da `nfelib` (v2.5.2) e foram confirmadas contra o
pacote de fato instalado neste ambiente -- ver
`docs/superpowers/notas-tecnicas/nfelib-api-referencia.md` para a inspeção
completa (leitura do código-fonte gerado por `xsdata` + teste de round-trip
com o XML de amostra oficial do próprio pacote). Nenhum nome de classe/campo
abaixo foi inventado; cada um foi confirmado via
`python -c "from nfelib... import ...; import dataclasses; ..."` neste mesmo
ambiente antes de ser usado.

CORREÇÃO (revisão final do branch) -- `infNFeSupl`/`qrCode`: este módulo
antes deixava de preencher `Tnfe.InfNfeSupl`, um grupo obrigatório para
NFC-e (a razão de existir do CSC). O texto abaixo dizia que isso tinha sido
"deferred to Task 7", mas a Task 7 só renderizou o QR Code no HTML local do
DANFE (`qrcode_builder.gerar_imagem_qrcode_base64`), nunca escreveu
`infNFeSupl` no XML de verdade. Corrigido: `montar_nfce_xml` agora monta
`infNFeSupl` via `_montar_inf_nfe_supl`, reusando
`qrcode_builder.montar_url_qrcode` (mesma função da Task 7) -- ver essa
função e `montar_nfce_xml` abaixo.

PENDÊNCIA EM ABERTO -- IBS/CBS (reforma tributária, obrigatório desde
2026-08-03): a versão instalada da `nfelib` modela os campos de IBS/CBS
(`Imposto.IBSCBS: Optional[TtribNfe]`, `Total.IBSCBSTot`), mas o XSD marca
esse grupo inteiro como opcional (sem `required=True`), e não há, neste
ambiente, o texto da Nota Técnica/MOC vigente da Sefaz para confirmar se a
obrigatoriedade é aplicada como regra de negócio além do XSD. Esta função
**não preenche** `Imposto.IBSCBS`/`Total.IBSCBSTot` -- preenchê-los com
valores fabricados (zerados) seria pior do que omiti-los, porque pareceria
"correto" sem ter sido calculado a partir de uma classificação tributária
(`cClassTrib`) real para os produtos da Nana Lanches, que também não foi
pesquisada. Isso é uma lacuna de conformidade real e rastreada -- ver o
README (Task 9) e o relatório desta task para o item de acompanhamento.
"""

import random
from decimal import Decimal, ROUND_HALF_UP

from nfelib.nfe.bindings.v4_0 import Nfe
from nfelib.nfe.bindings.v4_0.leiaute_nfe_v4_00 import (
    CofinsoutrCst,
    DestIndIedest,
    EmitCrt,
    IdeIdDest,
    IdeIndFinal,
    IdeIndPres,
    IdeTpEmis,
    IdeTpImp,
    IdeTpNf,
    Icmssn102Csosn,
    PisoutrCst,
    ProdIndTot,
    TenderEmi,
    TfinNfe,
    Tnfe,
    Torig,
    TprocEmi,
    TranspModFrete,
)
from nfelib.nfe.bindings.v4_0.tipos_basico_v4_00 import Tamb, Tmod, TcodUfIbge, TufEmi

from app.config import settings
from app.models.venda import Venda
from app.services.fiscal.focus_nfe import FORMAS_PAGAMENTO_CODIGOS
from app.services.fiscal.sefaz_direto import qrcode_builder

CFOP_VENDA_DENTRO_DO_ESTADO = "5102"
NATUREZA_OPERACAO = "Venda de mercadoria"
VERSAO_LEIAUTE = "4.00"

DUAS_CASAS = Decimal("0.01")

# O emitente (Nana Lanches) é fixo no Distrito Federal -- ver
# app.config.settings.emitente_endereco_uf (default "DF") e o campo cUF/cMunFG
# abaixo. 5300108 é o código IBGE do município de Brasília-DF (dado público,
# não sensível), usado tanto para o endereço do emitente quanto para o
# município do fato gerador (cMunFG).
CUF_EMITENTE = TcodUfIbge.VALUE_53
CMUNFG_EMITENTE = "5300108"

_AMBIENTES = {"homologacao": Tamb.VALUE_2, "producao": Tamb.VALUE_1}

_PESOS_MODULO_11 = [2, 3, 4, 5, 6, 7, 8, 9]

# Dados do emitente que o schema exige preenchidos (xBairro/CEP/IE/etc. têm
# patterns obrigatórios no XSD -- vazios produzem um XML bem-formado mas
# inválido, sem levantar exceção nenhuma se não for checado explicitamente).
# `emitente_endereco_numero` fica de fora: _montar_emit já cai para "SN"
# (sem número) quando está vazio, então nunca chega a virar um campo
# obrigatório vazio. `emitente_endereco_uf` também fica de fora: tem default
# não vazio ("DF") em Settings, por ser consumido como Enum (TufEmi).
# `emitente_nome_fantasia` é opcional no schema (xFant), por isso não entra.
_CAMPOS_EMITENTE_OBRIGATORIOS = {
    "EMITENTE_CNPJ": "emitente_cnpj",
    "EMITENTE_RAZAO_SOCIAL": "emitente_razao_social",
    "EMITENTE_IE": "emitente_ie",
    "EMITENTE_ENDERECO_LOGRADOURO": "emitente_endereco_logradouro",
    "EMITENTE_ENDERECO_BAIRRO": "emitente_endereco_bairro",
    "EMITENTE_ENDERECO_MUNICIPIO": "emitente_endereco_municipio",
    "EMITENTE_ENDERECO_CEP": "emitente_endereco_cep",
}

# CSC (Código de Segurança do Contribuinte) -- necessário para montar o hash
# de segurança do QR Code (`infNFeSupl.qrCode`, grupo obrigatório em NFC-e,
# ver `_montar_inf_nfe_supl` abaixo). Validado separadamente dos campos do
# emitente porque é uma credencial distinta (por CSC, não por CNPJ) e para
# que a mensagem de erro aponte exatamente para o que falta configurar.
_CAMPOS_CSC_OBRIGATORIOS = {
    "SEFAZ_CSC_ID": "sefaz_csc_id",
    "SEFAZ_CSC_TOKEN": "sefaz_csc_token",
}


def _validar_emitente_configurado() -> None:
    """Falha rápido com um ValueError claro se algum dado obrigatório do
    emitente não foi configurado via .env, em vez de deixar
    `montar_nfce_xml` retornar silenciosamente um XML bem-formado mas
    inválido pelo schema -- exatamente o tipo de falha silenciosa que este
    plano inteiro existe para evitar (aqui aplicado a "nunca produzir
    silenciosamente um documento não conforme", a mesma lógica de "nunca
    reportar silenciosamente uma emissão como bem-sucedida quando falhou").
    """
    faltando = [
        chave_env
        for chave_env, atributo in _CAMPOS_EMITENTE_OBRIGATORIOS.items()
        if not getattr(settings, atributo)
    ]
    if faltando:
        raise ValueError(
            "Dados do emitente incompletos no .env: "
            f"{', '.join(faltando)}. Preencha esses valores antes de emitir NFC-e."
        )


def _validar_csc_configurado() -> None:
    """Mesma lógica de `_validar_emitente_configurado`, aplicada ao CSC: sem
    `SEFAZ_CSC_ID`/`SEFAZ_CSC_TOKEN`, o QR Code montado teria um cIdToken
    vazio e um hash de segurança calculado sobre um token vazio -- um
    `infNFeSupl.qrCode` bem-formado mas inútil (e, no caso de cIdToken
    vazio, inválido pelo próprio pattern do schema), não um erro claro."""
    faltando = [
        chave_env for chave_env, atributo in _CAMPOS_CSC_OBRIGATORIOS.items() if not getattr(settings, atributo)
    ]
    if faltando:
        raise ValueError(
            "Configuração do CSC (Código de Segurança do Contribuinte) incompleta no .env: "
            f"{', '.join(faltando)}. Necessária para montar o grupo obrigatório "
            "infNFeSupl/qrCode antes de emitir NFC-e."
        )


def _somente_digitos(valor: str | None) -> str:
    return "".join(c for c in (valor or "") if c.isdigit())


def _calcular_dv_chave_acesso(chave_43_digitos: str) -> str:
    """Dígito verificador (módulo 11) da chave de acesso de 44 posições.

    Algoritmo padrão Sefaz: soma cada dígito (da direita para a esquerda)
    multiplicado por pesos que ciclam de 2 a 9; resto da divisão por 11 menor
    que 2 dá DV 0, senão DV = 11 - resto.

    Verificado neste ambiente contra a chave de acesso real do XML de
    amostra que a própria `nfelib` distribui
    (`nfelib/nfe/samples/v4_0/leiauteNFe/nfe_reforma_tributaria.xml`,
    chave `152312...15088`, DV `8`) -- a função reproduz o DV correto.
    """
    soma = 0
    for indice, digito in enumerate(reversed(chave_43_digitos)):
        soma += int(digito) * _PESOS_MODULO_11[indice % len(_PESOS_MODULO_11)]
    resto = soma % 11
    return "0" if resto < 2 else str(11 - resto)


def _gerar_codigo_numerico_aleatorio() -> str:
    return f"{random.randint(0, 99_999_999):08d}"


def _tpamb() -> Tamb:
    try:
        return _AMBIENTES[settings.sefaz_ambiente]
    except KeyError:
        raise ValueError(
            f"SEFAZ_AMBIENTE inválido: {settings.sefaz_ambiente!r} (use 'homologacao' ou 'producao')"
        )


def _montar_chave_acesso(numero: int, serie: int, cnf: str, tp_emis: str, venda: Venda) -> str:
    cnpj = _somente_digitos(settings.emitente_cnpj)
    aamm = venda.data_venda.strftime("%y%m")
    chave_43 = (
        "53"  # cUF (Distrito Federal)
        + aamm
        + cnpj.zfill(14)
        + "65"  # mod (NFC-e)
        + str(serie).zfill(3)
        + str(numero).zfill(9)
        + tp_emis
        + cnf
    )
    return chave_43 + _calcular_dv_chave_acesso(chave_43)


def _montar_ide(venda: Venda, numero: int, serie: int, cnf: str, chave: str) -> "Tnfe.InfNfe.Ide":
    return Tnfe.InfNfe.Ide(
        cUF=CUF_EMITENTE,
        cNF=cnf,
        natOp=NATUREZA_OPERACAO,
        mod=Tmod.VALUE_65,
        serie=str(serie),
        nNF=str(numero),
        dhEmi=venda.data_venda.strftime("%Y-%m-%dT%H:%M:%S-03:00"),
        tpNF=IdeTpNf.VALUE_1,  # saída
        idDest=IdeIdDest.VALUE_1,  # operação interna (dentro do DF)
        cMunFG=CMUNFG_EMITENTE,
        tpImp=IdeTpImp.VALUE_4,  # DANFE NFC-e
        tpEmis=IdeTpEmis.VALUE_1,  # emissão normal (sem contingência)
        cDV=chave[-1],
        tpAmb=_tpamb(),
        finNFe=TfinNfe.VALUE_1,  # NFC-e normal
        indFinal=IdeIndFinal.VALUE_1,  # sempre consumidor final em NFC-e
        # Não há hoje, no modelo Venda, um campo que distinga venda presencial
        # de delivery/online -- assume-se presencial (ponto de venda físico
        # do restaurante). Se um canal não presencial for adicionado no
        # futuro, este valor precisa ser derivado da venda, não fixo.
        indPres=IdeIndPres.VALUE_1,  # operação presencial
        procEmi=TprocEmi.VALUE_0,  # emissão com aplicativo do contribuinte
        verProc="1.0.0",
    )


def _montar_emit() -> "Tnfe.InfNfe.Emit":
    ie = (settings.emitente_ie or "").strip()
    ender_emit = TenderEmi(
        xLgr=settings.emitente_endereco_logradouro,
        nro=settings.emitente_endereco_numero or "SN",
        xBairro=settings.emitente_endereco_bairro,
        cMun=CMUNFG_EMITENTE,
        xMun=settings.emitente_endereco_municipio,
        UF=TufEmi(settings.emitente_endereco_uf),
        CEP=_somente_digitos(settings.emitente_endereco_cep),
    )
    return Tnfe.InfNfe.Emit(
        CNPJ=_somente_digitos(settings.emitente_cnpj),
        xNome=settings.emitente_razao_social,
        xFant=settings.emitente_nome_fantasia or None,
        enderEmit=ender_emit,
        IE="ISENTO" if ie.upper() == "ISENTO" else _somente_digitos(ie),
        # Simples Nacional -- inferido do uso pré-existente de códigos CSOSN
        # em focus_nfe.py (CSOSN é específico do Simples Nacional), NÃO
        # confirmado de forma independente com o negócio. Verificar antes de
        # emitir em produção.
        CRT=EmitCrt.VALUE_1,
    )


def _montar_dest(venda: Venda) -> "Tnfe.InfNfe.Dest | None":
    cliente = venda.cliente
    if cliente is None or cliente.consumidor_final or not cliente.cpf_cnpj:
        return None

    documento = _somente_digitos(cliente.cpf_cnpj)
    kwargs: dict = {"xNome": cliente.nome}
    if len(documento) <= 11:
        kwargs["CPF"] = documento
    else:
        kwargs["CNPJ"] = documento

    if cliente.ie:
        kwargs["IE"] = _somente_digitos(cliente.ie)
        kwargs["indIEDest"] = DestIndIedest.VALUE_1  # contribuinte ICMS
    else:
        kwargs["indIEDest"] = DestIndIedest.VALUE_9  # não contribuinte

    # `enderDest` é opcional no schema (Tnfe.InfNfe.Dest.enderDest: Optional).
    # O modelo Cliente hoje só guarda um campo de texto livre (`endereco`),
    # sem logradouro/número/bairro/município/UF separados -- não há como
    # popular Tendereco corretamente a partir dele, então o grupo é omitido
    # (opção válida, não um atalho às pressas).
    return Tnfe.InfNfe.Dest(**kwargs)


def _montar_det(item, n_item: int) -> "Tnfe.InfNfe.Det":
    produto = item.produto
    v_prod = (item.quantidade * item.preco_unitario).quantize(DUAS_CASAS, rounding=ROUND_HALF_UP)

    prod = Tnfe.InfNfe.Det.Prod(
        cProd=produto.codigo_interno,
        cEAN="SEM GTIN",
        xProd=produto.nome,
        NCM=produto.ncm,
        CFOP=CFOP_VENDA_DENTRO_DO_ESTADO,
        uCom=produto.unidade,
        qCom=str(item.quantidade),
        vUnCom=str(item.preco_unitario),
        vProd=str(v_prod),
        cEANTrib="SEM GTIN",
        uTrib=produto.unidade,
        qTrib=str(item.quantidade),
        vUnTrib=str(item.preco_unitario),
        indTot=ProdIndTot.VALUE_1,  # valor do item compõe o total da NFC-e
    )

    # Códigos de situação tributária: mesmo ponto de partida que já existia
    # em focus_nfe.montar_payload (icms_situacao_tributaria "102" -- que é,
    # na verdade, um CSOSN do Simples Nacional, não um CST -- e pis/cofins
    # "49"), mapeados para os grupos reais da nfelib. CRT=1 (Simples
    # Nacional) em _montar_emit é consistente com o uso de CSOSN aqui.
    imposto = Tnfe.InfNfe.Det.Imposto(
        ICMS=Tnfe.InfNfe.Det.Imposto.Icms(
            ICMSSN102=Tnfe.InfNfe.Det.Imposto.Icms.Icmssn102(
                orig=Torig.VALUE_0,
                CSOSN=Icmssn102Csosn.VALUE_102,
            )
        ),
        PIS=Tnfe.InfNfe.Det.Imposto.Pis(
            PISOutr=Tnfe.InfNfe.Det.Imposto.Pis.Pisoutr(
                CST=PisoutrCst.VALUE_49, vBC="0.00", pPIS="0.00", vPIS="0.00"
            )
        ),
        COFINS=Tnfe.InfNfe.Det.Imposto.Cofins(
            COFINSOutr=Tnfe.InfNfe.Det.Imposto.Cofins.Cofinsoutr(
                CST=CofinsoutrCst.VALUE_49, vBC="0.00", pCOFINS="0.00", vCOFINS="0.00"
            )
        ),
        # IBSCBS deliberadamente omitido -- ver PENDÊNCIA no docstring do módulo.
    )

    return Tnfe.InfNfe.Det(nItem=str(n_item), prod=prod, imposto=imposto)


def _montar_total(valor_produtos: Decimal) -> "Tnfe.InfNfe.Total":
    valor = str(valor_produtos.quantize(DUAS_CASAS, rounding=ROUND_HALF_UP))
    icms_tot = Tnfe.InfNfe.Total.Icmstot(
        vBC="0.00",
        vICMS="0.00",
        vICMSDeson="0.00",
        vFCP="0.00",
        vBCST="0.00",
        vST="0.00",
        vFCPST="0.00",
        vFCPSTRet="0.00",
        vProd=valor,
        vFrete="0.00",
        vSeg="0.00",
        vDesc="0.00",
        vII="0.00",
        vIPI="0.00",
        vIPIDevol="0.00",
        vPIS="0.00",
        vCOFINS="0.00",
        vOutro="0.00",
        vNF=valor,
    )
    return Tnfe.InfNfe.Total(ICMSTot=icms_tot)


def _montar_inf_nfe_supl(chave: str) -> "Tnfe.InfNfeSupl":
    """Monta o grupo `infNFeSupl` (`qrCode` + `urlChave`) -- obrigatório em
    NFC-e (modelo 65), corrigido nesta task (ver docstring do módulo).
    Reusa `qrcode_builder.montar_url_qrcode` (a mesma função já usada pela
    rota do DANFE local, Task 7) em vez de duplicar a lógica de hash do CSC.
    Campos confirmados via `dataclasses.fields(Tnfe.InfNfeSupl)` nesta
    ambiente: ambos `str`, obrigatórios, com pattern próprio no XSD."""
    url_qrcode = qrcode_builder.montar_url_qrcode(
        chave, settings.sefaz_ambiente, settings.sefaz_csc_id, settings.sefaz_csc_token
    )
    return Tnfe.InfNfeSupl(qrCode=url_qrcode, urlChave=qrcode_builder.montar_url_consulta_chave())


def _montar_pag(venda: Venda, valor_produtos: Decimal) -> "Tnfe.InfNfe.Pag":
    """`valor_produtos` precisa ser o MESMO valor (já somado a partir dos
    `vProd` quantizados por item) usado em `_montar_total` para `vNF` --
    nunca `venda.valor_total` diretamente. `vendas_service.recalcular_total`
    soma `quantidade * preco_unitario` sem quantizar antes de gravar
    (colunas `Numeric(10,2)`, mas o `Decimal` em memória antes de um reload
    pode carregar até 4 casas decimais); usar `venda.valor_total` aqui podia
    fazer `vPag` (pagamento) divergir de `vNF` (total dos produtos) em um
    centavo -- exatamente o tipo de inconsistência que a Sefaz rejeita.
    Recebendo o mesmo `Decimal` já quantizado que `_montar_total` usa, os
    dois grupos concordam por construção, não por coincidência (Important
    #7 da revisão final do branch)."""
    codigo = FORMAS_PAGAMENTO_CODIGOS.get(venda.forma_pagamento, "99")
    valor = str(valor_produtos.quantize(DUAS_CASAS, rounding=ROUND_HALF_UP))
    det_pag = Tnfe.InfNfe.Pag.DetPag(tPag=codigo, vPag=valor)
    return Tnfe.InfNfe.Pag(detPag=[det_pag])


def montar_nfce_xml(venda: Venda, numero: int, serie: int = 1) -> str:
    """Monta o XML (não assinado) da NFC-e a partir de uma `Venda` paga.

    Inclui `infNFeSupl` (`qrCode`/`urlChave`) -- grupo obrigatório em NFC-e,
    preenchido nesta correção (antes só era renderizado no DANFE HTML local
    pela Task 7, nunca no próprio XML enviado à Sefaz). Não inclui
    `Signature` (Task 4), adicionada por uma etapa posterior do pipeline de
    emissão. Por isso, `Nfe.schema_validation()` sobre a saída desta função
    aponta exatamente um erro esperado: falta `Signature` no elemento raiz
    `<NFe>`. Isso foi confirmado manualmente nesta task e não é um defeito
    de construção -- ver o relatório da task.
    """
    _validar_emitente_configurado()
    _validar_csc_configurado()

    cnf = _gerar_codigo_numerico_aleatorio()
    chave = _montar_chave_acesso(numero, serie, cnf, tp_emis="1", venda=venda)

    itens_det = [
        _montar_det(item, n_item=index) for index, item in enumerate(venda.itens, start=1)
    ]
    valor_produtos = sum(
        (item.quantidade * item.preco_unitario).quantize(DUAS_CASAS, rounding=ROUND_HALF_UP)
        for item in venda.itens
    )

    inf_nfe = Tnfe.InfNfe(
        ide=_montar_ide(venda, numero, serie, cnf, chave),
        emit=_montar_emit(),
        dest=_montar_dest(venda),
        det=itens_det,
        total=_montar_total(valor_produtos),
        transp=Tnfe.InfNfe.Transp(modFrete=TranspModFrete.VALUE_9),  # sem transporte
        pag=_montar_pag(venda, valor_produtos),
        versao=VERSAO_LEIAUTE,
        Id=f"NFe{chave}",
    )

    nfe = Nfe(infNFe=inf_nfe, infNFeSupl=_montar_inf_nfe_supl(chave))
    return nfe.to_xml()
