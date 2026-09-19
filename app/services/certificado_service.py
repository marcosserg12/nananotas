"""Permite trocar o certificado digital (A1, .pfx) usado pra assinar as
NFC-e sem precisar de acesso ao servidor -- o certificado da Nana Lanches
vence e precisa ser renovado periodicamente (certificados ICP-Brasil A1 são
válidos por um período limitado), e antes disso só dava pra trocar
entrando no servidor na mão."""

import shutil
from datetime import datetime
from pathlib import Path

from erpbrasil.assinatura.certificado import Certificado

from app.config import settings


def info_certificado_atual() -> dict:
    caminho = Path(settings.sefaz_certificado_path) if settings.sefaz_certificado_path else None
    existe = caminho is not None and caminho.is_file()
    if not existe:
        return {"existe": False, "caminho": str(caminho) if caminho else None, "tamanho_kb": None, "modificado_em": None}
    estatisticas = caminho.stat()
    info = {
        "existe": True,
        "caminho": str(caminho),
        "tamanho_kb": round(estatisticas.st_size / 1024, 1),
        "modificado_em": datetime.fromtimestamp(estatisticas.st_mtime).strftime("%d/%m/%Y %H:%M"),
        "proprietario": None,
        "cnpj_cpf": None,
        "emissor": None,
        "valido_ate": None,
        "expirado": None,
        "erro_leitura": None,
    }
    try:
        certificado = Certificado(str(caminho), settings.sefaz_certificado_senha, raise_expirado=False)
        info["proprietario"] = certificado.proprietario
        info["cnpj_cpf"] = certificado.cnpj_cpf
        info["emissor"] = certificado.emissor
        info["valido_ate"] = certificado.fim_validade.astimezone().strftime("%d/%m/%Y")
        info["expirado"] = certificado.expirado
    except Exception:
        info["erro_leitura"] = "Não foi possível ler os detalhes do certificado com a senha salva."
    return info


def substituir_certificado(conteudo: bytes, senha: str, caminho_env: Path | None = None) -> None:
    """Valida o certificado novo (arquivo + senha, abrindo de verdade com
    `erpbrasil.assinatura`) ANTES de substituir o atual -- um upload errado
    nunca deve deixar o sistema sem conseguir emitir nota nenhuma. Guarda
    uma cópia do certificado anterior (sufixo `.bak`) pra poder reverter na
    mão se precisar.

    `caminho_env` é injetável só pra teste (aponta pra um `.env` de mentira
    em vez do real) -- por padrão é o `.env` de verdade do projeto."""
    if not conteudo:
        raise ValueError("Nenhum arquivo enviado")
    if not settings.sefaz_certificado_path:
        raise ValueError("SEFAZ_CERTIFICADO_PATH não está configurado no .env")

    caminho_destino = Path(settings.sefaz_certificado_path)
    caminho_temp = caminho_destino.with_name(caminho_destino.name + ".novo")
    caminho_temp.write_bytes(conteudo)

    try:
        Certificado(str(caminho_temp), senha).cert_chave()
    except Exception as exc:
        caminho_temp.unlink(missing_ok=True)
        raise ValueError(
            "Não foi possível abrir o certificado com a senha informada -- confira o arquivo e a senha."
        ) from exc

    if caminho_destino.is_file():
        caminho_backup = caminho_destino.with_name(caminho_destino.name + ".bak")
        shutil.copy2(caminho_destino, caminho_backup)

    caminho_temp.replace(caminho_destino)

    _atualizar_senha_no_env(senha, caminho_env or Path(".env"))
    settings.sefaz_certificado_senha = senha


def _atualizar_senha_no_env(nova_senha: str, caminho_env: Path) -> None:
    """Atualiza `SEFAZ_CERTIFICADO_SENHA` no `.env` em disco, pra a senha
    nova sobreviver a um reinício do servidor -- sem isso, a mudança só
    valeria até o próximo `systemctl restart`, quando o `.env` antigo seria
    recarregado por cima. Se o `.env` não existir (ex.: alguns ambientes de
    teste), não faz nada -- não é papel desta função criar o arquivo do
    zero."""
    if not caminho_env.is_file():
        return
    linhas = caminho_env.read_text(encoding="utf-8").splitlines()
    chave = "SEFAZ_CERTIFICADO_SENHA="
    for indice, linha in enumerate(linhas):
        if linha.startswith(chave):
            linhas[indice] = f"{chave}{nova_senha}"
            break
    else:
        linhas.append(f"{chave}{nova_senha}")
    caminho_env.write_text("\n".join(linhas) + "\n", encoding="utf-8")
