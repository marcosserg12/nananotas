from app.services.fiscal.sefaz_direto import numeracao


def test_reservar_proximo_numero_comeca_em_1(db_session):
    numero = numeracao.reservar_proximo_numero(db_session, serie=1)

    assert numero == 1


def test_reservar_proximo_numero_incrementa_sequencialmente(db_session):
    primeiro = numeracao.reservar_proximo_numero(db_session, serie=1)
    segundo = numeracao.reservar_proximo_numero(db_session, serie=1)
    terceiro = numeracao.reservar_proximo_numero(db_session, serie=1)

    assert [primeiro, segundo, terceiro] == [1, 2, 3]


def test_series_diferentes_tem_contadores_independentes(db_session):
    numero_serie_1 = numeracao.reservar_proximo_numero(db_session, serie=1)
    numero_serie_2 = numeracao.reservar_proximo_numero(db_session, serie=2)

    assert numero_serie_1 == 1
    assert numero_serie_2 == 1
