import hashlib

from app.services.fiscal.sefaz_direto import qrcode_builder


def test_montar_url_qrcode_inclui_chave_e_parametros_obrigatorios():
    chave = "5" * 44
    url = qrcode_builder.montar_url_qrcode(chave, ambiente="homologacao", csc_id="1", csc_token="ABC123")

    assert url.startswith("http://www.fazenda.df.gov.br/nfce/qrcode?")
    assert chave in url
    assert "|2|" in url  # tpAmb=2 (homologacao)


def test_montar_url_qrcode_producao_usa_tpamb_1():
    chave = "5" * 44
    url = qrcode_builder.montar_url_qrcode(chave, ambiente="producao", csc_id="1", csc_token="ABC123")

    assert "|1|" in url


def test_montar_url_qrcode_hash_bate_com_formula_sha1_maiuscula():
    chave = "5" * 44
    url = qrcode_builder.montar_url_qrcode(chave, ambiente="homologacao", csc_id="1", csc_token="ABC123")

    parametros_sem_hash = f"{chave}|2|2|1"
    hash_esperado = hashlib.sha1(f"{parametros_sem_hash}ABC123".encode("utf-8")).hexdigest().upper()

    assert url == f"http://www.fazenda.df.gov.br/nfce/qrcode?p={parametros_sem_hash}|{hash_esperado}"


def test_gerar_imagem_qrcode_base64_retorna_data_uri_png():
    imagem = qrcode_builder.gerar_imagem_qrcode_base64("http://www.fazenda.df.gov.br/nfce/qrcode?p=teste")

    assert imagem.startswith("data:image/png;base64,")
