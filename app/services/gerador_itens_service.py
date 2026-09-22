"""Monta uma lista de produtos (quantidade + preço unitário) cuja soma dá
EXATAMENTE um valor-alvo, respeitando, por produto, a chance de aparecer e a
faixa de preço (mínimo/máximo). Serve pra quem hoje fica somando produtos na
calculadora até chegar no valor que o cliente pagou.

Tudo aqui trabalha em CENTAVOS (int) pra nunca ter erro de arredondamento --
a conversão de/para `Decimal` fica com quem chama.

Como funciona, em resumo:
1. Cada produto do gerador "sorteia" se entra na lista, com a chance
   configurada (1-100%).
2. Pra fechar o valor, prefere ADICIONAR mais produtos (variedade) a inflar a
   quantidade de um só -- cada linha fica pequena (no máximo
   `QTD_LINHA_MAXIMA`), como um pedido de verdade. Um mesmo produto pode
   aparecer em mais de uma linha (ex.: duas refeições em dias diferentes de
   preço), mas nunca "18 sucos iguais" numa linha só só pra bater o total.
3. Uma linha de quantidade 1 fica reservada como "balanceadora": os preços
   das outras linhas são escolhidos dentro das faixas e a balanceadora absorve
   os centavos que sobrarem, fechando a conta certinho.
"""

import random
from collections import Counter
from dataclasses import dataclass

# Tetos pequenos de propósito: uma nota de verdade não tem "18 sucos" numa
# linha só (QTD_LINHA_MAXIMA), nem 23 linhas separadas do mesmo suco pra
# fechar um valor alto (LINHAS_POR_PRODUTO_MAXIMA) -- ela tem vários itens
# DIFERENTES. Ver o loop de variedade em `_tentar` abaixo.
QTD_LINHA_MAXIMA = 3
LINHAS_POR_PRODUTO_MAXIMA = 3
TENTATIVAS = 600


@dataclass(frozen=True)
class Candidato:
    produto_id: int
    chance: int  # 1..100
    preco_min: int  # centavos
    preco_max: int  # centavos


@dataclass(frozen=True)
class ItemGerado:
    produto_id: int
    quantidade: int
    preco_unitario: int  # centavos


class _Linha:
    __slots__ = ("cand", "q")

    def __init__(self, cand: Candidato, q: int = 1):
        self.cand = cand
        self.q = q

    @property
    def flexivel(self) -> bool:
        return self.cand.preco_max > self.cand.preco_min

    @property
    def folga(self) -> int:
        return self.cand.preco_max - self.cand.preco_min


def _sortear_ponderado(rng: random.Random, itens: list, peso):
    pesos = [max(int(peso(item)), 1) for item in itens]
    return rng.choices(itens, weights=pesos, k=1)[0]


def _minimo(linhas: list[_Linha]) -> int:
    return sum(linha.q * linha.cand.preco_min for linha in linhas)


def _maximo(linhas: list[_Linha]) -> int:
    return sum(linha.q * linha.cand.preco_max for linha in linhas)


def _d_multiplo_de_100(d_min: int, d_max: int, alvo: int, verificar=None) -> int | None:
    """Múltiplo de 100 dentro de [d_min, d_max] mais perto de `alvo` --
    garante que o preço unitário (`preco_min + d`) sempre feche em reais
    inteiros, nunca em centavos aleatórios tipo "R$ 28,17". `verificar`
    (opcional) filtra ainda mais os candidatos -- usado só quando a
    balanceadora tem mais de uma unidade (ver mais abaixo), pra achar um `d`
    cuja sobra dê certo dividida entre as unidades dela."""
    primeiro = -(-d_min // 100) * 100
    ultimo = (d_max // 100) * 100
    if primeiro > ultimo:
        return None
    candidatos = range(primeiro, ultimo + 1, 100)
    if verificar is not None:
        candidatos = [d for d in candidatos if verificar(d)]
        if not candidatos:
            return None
    return min(candidatos, key=lambda d: abs(d - alvo))


def _formatar_reais(centavos: int) -> str:
    return f"{centavos / 100:.2f}".replace(".", ",")


def montar_itens(
    total: int,
    candidatos: list[Candidato],
    rng: random.Random | None = None,
    tentativas: int = TENTATIVAS,
) -> list[ItemGerado]:
    rng = rng or random.Random()
    if total <= 0:
        raise ValueError("Informe um valor maior que zero")
    if not candidatos:
        raise ValueError(
            "Nenhum produto tem preço mínimo e máximo definidos. Em Produtos > Gerador de valor, "
            "preencha a faixa de preço dos produtos."
        )
    for c in candidatos:
        if c.preco_min <= 0 or c.preco_max < c.preco_min:
            raise ValueError("Há produto do gerador com preço mínimo/máximo inválido")

    mais_barato = min(c.preco_min for c in candidatos)
    if mais_barato > total:
        raise ValueError(
            f"O valor é menor que o produto mais barato do gerador (R$ {_formatar_reais(mais_barato)})."
        )

    limite_sem_dividir = int(tentativas * 0.7)
    for numero in range(tentativas):
        itens = _tentar(total, candidatos, rng, permitir_dividir=numero >= limite_sem_dividir)
        if itens is not None:
            return itens

    raise ValueError(
        "Não consegui fechar exatamente esse valor com os produtos do gerador. Tente aumentar a "
        "diferença entre o preço mínimo e o máximo de algum produto, ou liberar mais produtos."
    )


def _tentar(
    total: int, candidatos: list[Candidato], rng: random.Random, permitir_dividir: bool
) -> list[ItemGerado] | None:
    acessiveis = [c for c in candidatos if c.preco_min <= total]
    flexiveis = [c for c in acessiveis if c.preco_max > c.preco_min]

    linhas = [_Linha(c) for c in acessiveis if rng.random() * 100 < c.chance]
    if flexiveis and not any(linha.flexivel for linha in linhas):
        # Sem nenhum produto de preço flexível não dá pra acertar os centavos.
        linhas.append(_Linha(_sortear_ponderado(rng, flexiveis, lambda c: c.chance)))
    if not linhas:
        linhas.append(_Linha(_sortear_ponderado(rng, acessiveis, lambda c: c.chance)))

    while _minimo(linhas) > total:
        flexiveis_na_lista = [linha for linha in linhas if linha.flexivel]
        removiveis = [
            linha for linha in linhas if not (linha.flexivel and len(flexiveis_na_lista) == 1)
        ]
        if not removiveis:
            return None
        linhas.remove(rng.choice(removiveis))

    # Onde o valor-alvo deve cair dentro da faixa de preços possível: perto de
    # 0 = muitos itens com preço perto do mínimo; perto de 1 = poucos itens com
    # preço perto do máximo. Sorteado a cada tentativa pra variar a composição.
    posicao_alvo = rng.uniform(0.15, 0.85)
    contagem_linhas = Counter(linha.cand.produto_id for linha in linhas)

    while True:
        minimo, maximo = _minimo(linhas), _maximo(linhas)
        if maximo >= total and (total - minimo) <= posicao_alvo * (maximo - minimo):
            break

        # 1) Primeiro tenta aumentar a quantidade de uma linha que já está na
        #    nota (até o teto pequeno) -- é o jeito "padrão" de crescer, e
        #    mantém a composição que o sorteio inicial (a chance de cada
        #    produto) já decidiu.
        opcoes = [
            linha for linha in linhas if linha.q < QTD_LINHA_MAXIMA and minimo + linha.cand.preco_min <= total
        ]
        if opcoes:
            escolhida = _sortear_ponderado(rng, opcoes, lambda l: l.cand.chance * l.cand.preco_max)
            escolhida.q += 1
            continue

        # 2) Todas as linhas atuais já estão no teto de quantidade: em vez de
        #    trazer um produto que nem tinha sido sorteado pra esta nota,
        #    prefere abrir uma NOVA linha de um produto que a nota JÁ tem
        #    (com seu próprio preço, sorteado depois) -- é o que dá "duas
        #    refeições em preços diferentes" em vez de inflar quantidade, sem
        #    forçar produto de chance baixa a aparecer sem necessidade. Mas só
        #    até `LINHAS_POR_PRODUTO_MAXIMA`: sem esse teto, um valor alto com
        #    poucos produtos sorteados virava uma nota inteira de "23 linhas
        #    de suco" -- também nada realista, só trocando "quantidade demais"
        #    por "linhas demais" do mesmo item.
        ja_usados = {linha.cand.produto_id for linha in linhas}
        repetiveis = [
            c
            for c in acessiveis
            if c.produto_id in ja_usados
            and contagem_linhas[c.produto_id] < LINHAS_POR_PRODUTO_MAXIMA
            and minimo + c.preco_min <= total
        ]
        if repetiveis:
            escolhido = _sortear_ponderado(rng, repetiveis, lambda c: c.chance)
            linhas.append(_Linha(escolhido))
            contagem_linhas[escolhido.produto_id] += 1
            continue

        # 3) Nenhum produto já usado consegue mais espaço (atingiu o teto de
        #    linhas) -- agora sim traz um produto que a nota ainda não tinha,
        #    o que mantém a nota variada em vez de repetir os mesmos 1 ou 2
        #    produtos indefinidamente.
        novos = [c for c in acessiveis if c.produto_id not in ja_usados and minimo + c.preco_min <= total]
        if novos:
            escolhido = _sortear_ponderado(rng, novos, lambda c: c.chance)
            linhas.append(_Linha(escolhido))
            contagem_linhas[escolhido.produto_id] += 1
            continue

        if maximo >= total:
            break
        return None

    balanceadora: _Linha | None = None
    linhas_flexiveis = [linha for linha in linhas if linha.flexivel]
    if linhas_flexiveis:
        com_qtd_um = [linha for linha in linhas_flexiveis if linha.q == 1]
        if permitir_dividir:
            if com_qtd_um:
                balanceadora = _sortear_ponderado(rng, com_qtd_um, lambda l: 1_000_000 // l.cand.preco_max)
            else:
                # Último recurso: separa 1 unidade de uma linha flexível pra
                # servir de balanceadora (o mesmo produto aparece em duas
                # linhas, com preços unitários levemente diferentes).
                origem = _sortear_ponderado(rng, linhas_flexiveis, lambda l: 1_000_000 // l.cand.preco_max)
                origem.q -= 1
                balanceadora = _Linha(origem.cand, 1)
                linhas.append(balanceadora)
        else:
            # Prefere balanceadora de quantidade 1 (sempre consegue acertar os
            # centavos), mas aceita outra: se os centavos não fecharem, a
            # tentativa falha e o sorteio recomeça.
            balanceadora = _sortear_ponderado(
                rng, linhas_flexiveis, lambda l: (1_000_000 // l.cand.preco_max) // (l.q * l.q)
            )

    outras = [linha for linha in linhas if linha is not balanceadora]
    rng.shuffle(outras)
    outras.sort(key=lambda linha: -linha.q)

    qtd_balanceadora = balanceadora.q if balanceadora else 1
    extra_restante = total - _minimo(linhas)
    folga_balanceadora = qtd_balanceadora * balanceadora.folga if balanceadora else 0
    folga_das_proximas = sum(linha.q * linha.folga for linha in outras)

    precos: dict[int, int] = {}
    for indice, linha in enumerate(outras):
        folga_linha = linha.q * linha.folga
        folga_das_proximas -= folga_linha

        minimo_desta = extra_restante - folga_balanceadora - folga_das_proximas
        d_min = max(0, -(-minimo_desta // linha.q))
        d_max = min(linha.folga, extra_restante // linha.q)
        if d_min > d_max:
            return None

        # Preço-alvo dentro da faixa DESTE produto, com viés pro lado mais
        # barato: pratos de menor valor tendem a vender mais, então a maioria
        # das notas usa preços perto do mínimo de cada produto, só de vez em
        # quando perto do máximo (Beta assimétrica, não uniforme). O `d_min`
        # calculado acima já garante que o valor final feche certinho mesmo
        # quando o viés baixo não é suficiente pra chegar no total.
        alvo = round(linha.folga * rng.betavariate(1.2, 3.0))

        eh_ultima = indice == len(outras) - 1
        if eh_ultima and balanceadora is not None and qtd_balanceadora > 1:
            # A balanceadora tem várias unidades: o que sobrar pra ela precisa
            # ser múltiplo da quantidade dela, então esta última linha só pode
            # assumir os preços (múltiplos de 100) que deixam essa sobra
            # "redonda".
            d = _d_multiplo_de_100(
                d_min, d_max, alvo,
                verificar=lambda d: (extra_restante - linha.q * d) % qtd_balanceadora == 0,
            )
        else:
            d = _d_multiplo_de_100(d_min, d_max, alvo)
        if d is None:
            return None

        precos[id(linha)] = linha.cand.preco_min + d
        extra_restante -= linha.q * d

    if balanceadora is not None:
        if extra_restante % qtd_balanceadora != 0:
            return None
        d_balanceadora = extra_restante // qtd_balanceadora
        # Mesmo com `extra_restante` batendo um número redondo de reais,
        # dividir por uma quantidade > 1 pode não dar outro número redondo
        # (ex.: R$ 1,00 sobrando pra 2 unidades = R$ 0,50 cada) -- rejeita
        # esse caso em vez de aceitar um preço quebrado; a tentativa seguinte
        # tende a usar uma balanceadora de quantidade 1, que sempre resolve.
        # Com quantidade 1 não tem esse risco: o que sobrar é, por definição,
        # exatamente o troco do valor total (que pode ter centavos de verdade
        # quando o total digitado também tem).
        if qtd_balanceadora > 1 and d_balanceadora % 100 != 0:
            return None
        if not 0 <= d_balanceadora <= balanceadora.folga:
            return None
        precos[id(balanceadora)] = balanceadora.cand.preco_min + d_balanceadora
    elif extra_restante != 0:
        return None

    itens = [ItemGerado(linha.cand.produto_id, linha.q, precos[id(linha)]) for linha in linhas]
    if sum(item.quantidade * item.preco_unitario for item in itens) != total:
        return None
    itens.sort(key=lambda item: -(item.quantidade * item.preco_unitario))
    return itens
