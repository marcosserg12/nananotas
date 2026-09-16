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
