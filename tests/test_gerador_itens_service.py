import random

import pytest

from app.services import gerador_itens_service
from app.services.gerador_itens_service import Candidato, montar_itens

CARDAPIO = [
    Candidato(produto_id=1, chance=100, preco_min=3000, preco_max=4500),  # refeição
    Candidato(produto_id=2, chance=60, preco_min=600, preco_max=1000),  # bebida
    Candidato(produto_id=3, chance=30, preco_min=800, preco_max=1400),  # sobremesa
]


def _soma(itens):
    return sum(item.quantidade * item.preco_unitario for item in itens)


def _confere_regras(itens, candidatos, total):
    por_id = {c.produto_id: c for c in candidatos}
    assert itens, "a lista gerada não pode ser vazia"
    assert _soma(itens) == total
    for item in itens:
        candidato = por_id[item.produto_id]
        assert isinstance(item.quantidade, int) and item.quantidade >= 1
        assert candidato.preco_min <= item.preco_unitario <= candidato.preco_max


@pytest.mark.parametrize("total", [700, 3000, 4500, 6000, 9999, 14000, 14001, 25050, 55000])
def test_fecha_o_valor_exato_e_respeita_as_faixas_de_preco(total):
    for semente in range(40):
        itens = montar_itens(total, CARDAPIO, random.Random(semente))
        _confere_regras(itens, CARDAPIO, total)


def test_fecha_o_valor_exato_para_muitos_valores_diferentes():
    sorteio = random.Random(12345)
    for _ in range(300):
        total = sorteio.randint(600, 60000)
        itens = montar_itens(total, CARDAPIO, random.Random(sorteio.random()))
        _confere_regras(itens, CARDAPIO, total)


def test_mesma_semente_gera_o_mesmo_resultado():
    a = montar_itens(14000, CARDAPIO, random.Random(7))
    b = montar_itens(14000, CARDAPIO, random.Random(7))

    assert a == b


def test_sementes_diferentes_geram_combinacoes_diferentes():
    combinacoes = {tuple(montar_itens(14000, CARDAPIO, random.Random(s))) for s in range(30)}

    assert len(combinacoes) > 5


def test_produto_com_chance_100_aparece_sempre():
    for semente in range(50):
        itens = montar_itens(14000, CARDAPIO, random.Random(semente))

        assert 1 in {item.produto_id for item in itens}


def test_produto_com_chance_baixa_aparece_bem_menos_que_o_de_chance_alta():
    cardapio = [
        Candidato(produto_id=1, chance=100, preco_min=3000, preco_max=4500),
        Candidato(produto_id=2, chance=100, preco_min=600, preco_max=1000),
        Candidato(produto_id=3, chance=5, preco_min=800, preco_max=1400),
    ]
    aparicoes = {1: 0, 2: 0, 3: 0}
    for semente in range(200):
        for item in montar_itens(14000, cardapio, random.Random(semente)):
            aparicoes[item.produto_id] += 1

    assert aparicoes[3] < aparicoes[2] / 2


def test_um_unico_produto_flexivel_ainda_fecha_o_valor():
    cardapio = [Candidato(produto_id=1, chance=100, preco_min=3000, preco_max=4500)]
    for total in (14000, 14001, 14002, 9999):
        for semente in range(20):
            itens = montar_itens(total, cardapio, random.Random(semente))
            _confere_regras(itens, cardapio, total)


def test_produtos_de_preco_fixo_fecham_quando_a_conta_bate():
    cardapio = [Candidato(produto_id=1, chance=100, preco_min=600, preco_max=600)]

    itens = montar_itens(1800, cardapio, random.Random(1))

    assert itens == [itens[0]]
    assert itens[0].quantidade == 3 and itens[0].preco_unitario == 600


def test_produtos_de_preco_fixo_com_conta_impossivel_dao_erro_claro():
    cardapio = [Candidato(produto_id=1, chance=100, preco_min=600, preco_max=600)]

    with pytest.raises(ValueError, match="Não consegui fechar"):
        montar_itens(1000, cardapio, random.Random(1), tentativas=50)


def test_sem_candidatos_da_erro():
    with pytest.raises(ValueError, match="Nenhum produto"):
        montar_itens(14000, [])


def test_valor_zero_ou_negativo_da_erro():
    with pytest.raises(ValueError, match="maior que zero"):
        montar_itens(0, CARDAPIO)
    with pytest.raises(ValueError, match="maior que zero"):
        montar_itens(-100, CARDAPIO)


def test_valor_menor_que_o_produto_mais_barato_da_erro_com_o_preco():
    with pytest.raises(ValueError, match=r"mais barato .*6,00"):
        montar_itens(500, CARDAPIO)


def test_faixa_de_preco_invalida_da_erro():
    with pytest.raises(ValueError, match="inválido"):
        montar_itens(1000, [Candidato(produto_id=1, chance=100, preco_min=900, preco_max=500)])


@pytest.mark.parametrize("total", [8750, 9999, 14000, 25001, 60000])
def test_cardapio_comum_nunca_tem_uma_linha_com_quantidade_absurda(total):
    """Achado real de uso: pra fechar um valor alto com poucos produtos
    disponíveis, uma versão antiga do algoritmo inflava a quantidade de uma
    única linha (ex.: "18 sucos" pra fechar R$ 160) -- nada realista. Uma nota
    de verdade tem VÁRIOS itens (às vezes o mesmo produto em mais de uma
    linha, cada um com seu preço), não uma quantidade gigante numa linha só."""
    for semente in range(100):
        itens = montar_itens(total, CARDAPIO, random.Random(semente))

        assert all(item.quantidade <= gerador_itens_service.QTD_LINHA_MAXIMA for item in itens)


@pytest.mark.parametrize("total", [25001, 60000])
def test_cardapio_comum_com_valor_alto_ganha_mais_linhas_em_vez_de_mais_quantidade(total):
    """Complementa o teste acima: confirma que fechar um valor bem maior que
    o produto mais caro do cardápio resulta em MAIS linhas (o comportamento
    novo), e não numa única linha esticada."""
    linhas_por_tentativa = [
        len(montar_itens(total, CARDAPIO, random.Random(semente))) for semente in range(30)
    ]

    assert max(linhas_por_tentativa) > 2


@pytest.mark.parametrize("total", [700, 3000, 6000, 14000, 25000, 55000])
def test_preco_unitario_fecha_sempre_em_reais_inteiros_quando_o_total_e_inteiro(total):
    """Pedido real: preço unitário tipo "R$ 28,17" não é realista -- cada
    produto tem seu preço num número inteiro de reais. Só quando o VALOR
    TOTAL digitado tem centavos (não é o caso aqui) é que uma única linha
    pode sobrar com centavos, por necessidade matemática."""
    for semente in range(60):
        itens = montar_itens(total, CARDAPIO, random.Random(semente))

        assert all(item.preco_unitario % 100 == 0 for item in itens)


@pytest.mark.parametrize("total", [8750, 9999, 14001, 25050])
def test_preco_unitario_so_tem_centavos_em_no_maximo_uma_linha_quando_o_total_tem_centavos(total):
    """Quando o total tem centavos, é matematicamente necessário que UMA
    linha absorva essa diferença -- mas só uma, as outras continuam em reais
    inteiros."""
    for semente in range(60):
        itens = montar_itens(total, CARDAPIO, random.Random(semente))

        com_centavos = [item for item in itens if item.preco_unitario % 100 != 0]
        assert len(com_centavos) <= 1


def test_precos_tendem_pro_lado_barato_da_faixa_de_cada_produto():
    """Pedido real: pratos de menor valor tendem a vender mais -- o preço
    sorteado dentro da faixa de cada produto deve, na média (olhando várias
    notas com cardápios de verdade, várias linhas cada), ficar mais perto do
    mínimo do que do máximo, não distribuído por igual nem puxado pro topo.

    Usa o CARDAPIO com 3 produtos (não um só): com um único produto, a linha
    "balanceadora" (que fecha os centavos) fica sozinha e sem viés possível
    -- ela é só o troco do que sobrou --, o que mascararia o efeito. Com mais
    produtos, a balanceadora é só uma entre várias linhas, e o viés das
    outras aparece na média geral.
    """
    faixas = {c.produto_id: (c.preco_min, c.preco_max) for c in CARDAPIO if c.preco_max > c.preco_min}
    posicoes = []
    for total in (3000, 6000, 9000, 14000, 20000, 25000, 35000, 45000):
        for semente in range(80):
            for item in montar_itens(total, CARDAPIO, random.Random(semente * 1000 + total)):
                minimo, maximo = faixas.get(item.produto_id, (None, None))
                if minimo is not None:
                    posicoes.append((item.preco_unitario - minimo) / (maximo - minimo))

    media = sum(posicoes) / len(posicoes)
    assert media < 0.45, f"média da posição dentro da faixa ficou em {media:.2f}, esperava puxar pro lado barato"
