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

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.db_username}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_database}"
        )


settings = Settings()
