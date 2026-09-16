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

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.db_username}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_database}"
        )


settings = Settings()
