"""Tabelas de códigos fixos usadas em mais de um lugar do sistema (UI e XML
fiscal), para não duplicar o mapeamento código -> rótulo."""

# Tabela oficial de bandeiras de cartão usada no campo `tBand` do XML da
# NFC-e (grupo `Pag.detPag.card`) -- mesma tabela usada no sistema antigo,
# confirmada com o usuário a partir de imagens de referência.
BANDEIRAS_CARTAO = {
    "01": "Visa",
    "02": "Mastercard",
    "03": "American Express",
    "04": "Sorocred",
    "05": "Diners Club",
    "06": "Elo",
    "07": "Hipercard",
    "08": "Aura",
    "09": "Cabal",
    "99": "Outros",
}

# Formas de pagamento (chave usada em `Venda.forma_pagamento`) para as quais
# faz sentido perguntar a bandeira do cartão.
FORMAS_PAGAMENTO_COM_BANDEIRA = {"cartao_credito", "cartao_debito"}

# Rótulo legível para exibição (DANFE, resumo da venda) a partir da chave
# interna gravada em `Venda.forma_pagamento`.
FORMAS_PAGAMENTO_LABELS = {
    "dinheiro": "Dinheiro",
    "cartao_credito": "Cartão de Crédito",
    "cartao_debito": "Cartão de Débito",
    "pix": "Pix",
}
