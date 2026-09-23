from urllib.parse import quote_plus

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    db_connection: str = "mysql"
    db_host: str = "localhost"
    db_port: int = 3306
    db_database: str = "nana_lanches"
    db_username: str = "nana_lanches_user"
    db_password: str = ""
    secret_key: str = "change-me"
    focus_nfe_token: str = ""
    focus_nfe_ambiente: str = "homologacao"
    sefaz_certificado_path: str = ""
    sefaz_certificado_senha: str = ""
    sefaz_ambiente: str = "homologacao"
    # Série da NFC-e (cada série tem numeração própria). 1 a 889: as faixas 890-999
    # são reservadas pela Sefaz (contingência/uso especial).
    sefaz_serie: int = Field(default=1, ge=1, le=889)
    sefaz_csc_id: str = ""
    sefaz_csc_token: str = ""
    emitente_cnpj: str = ""
    emitente_razao_social: str = ""
    emitente_nome_fantasia: str = ""
    emitente_ie: str = ""
    emitente_endereco_logradouro: str = ""
    emitente_endereco_numero: str = ""
    emitente_endereco_bairro: str = ""
    emitente_endereco_municipio: str = ""
    emitente_endereco_uf: str = "DF"
    emitente_endereco_cep: str = ""
    emitente_telefone: str = ""
    mail_host: str = ""
    mail_port: int = 587
    mail_username: str = ""
    mail_password: str = ""
    mail_encryption: str = "tls"
    mail_from_address: str = ""
    mail_from_name: str = "Nana Lanches"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def database_url(self) -> str:
        # Usuário/senha são escapados (quote_plus) porque podem conter
        # caracteres especiais de URL (@, #, %, etc.) -- sem isso, uma senha
        # com "@" no meio, por exemplo, é lida como se fizesse parte do
        # endereço do servidor, quebrando a conexão de forma confusa.
        usuario = quote_plus(self.db_username)
        senha = quote_plus(self.db_password)
        return f"mysql+pymysql://{usuario}:{senha}@{self.db_host}:{self.db_port}/{self.db_database}"


settings = Settings()
