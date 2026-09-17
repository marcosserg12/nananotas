from app.config import Settings


def test_database_url_built_from_parts():
    settings = Settings(
        db_host="example.com",
        db_port=3306,
        db_database="testdb",
        db_username="user",
        db_password="secret",
    )
    assert settings.database_url == "mysql+pymysql://user:secret@example.com:3306/testdb"


def test_database_url_escapa_caracteres_especiais_na_senha():
    settings = Settings(
        db_host="example.com",
        db_port=3306,
        db_database="testdb",
        db_username="user",
        db_password="Fake_Pw&9@ex(2)t3stOnly",
    )
    assert settings.database_url == (
        "mysql+pymysql://user:Fake_Pw%269%40ex%282%29t3stOnly@example.com:3306/testdb"
    )


def test_settings_tem_valores_padrao_para_sefaz_direto():
    # `_env_file=None` isola este teste do `.env` real do projeto -- sem
    # isso, uma vez que exista um `.env` de verdade na raiz (necessário
    # pra rodar o sistema em produção), este teste passaria a depender do
    # que estiver configurado nele em vez dos valores padrão da classe.
    settings = Settings(_env_file=None)

    assert settings.sefaz_ambiente == "homologacao"
    assert settings.sefaz_certificado_path == ""
    assert settings.sefaz_csc_id == ""
