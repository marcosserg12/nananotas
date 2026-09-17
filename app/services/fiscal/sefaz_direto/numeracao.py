from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.numeracao_nfce import NumeracaoNFCe


def reservar_proximo_numero(db: Session, serie: int = 1) -> int:
    # Use with_for_update() to acquire a row-level lock for atomicity on the read-modify-write.
    # This prevents concurrent requests from reading the same numero_ultimo value and both
    # incrementing to the same result. On MySQL/InnoDB, this translates to real locks that block
    # concurrent transactions; SQLite ignores it gracefully (no-op), which is fine for testing.
    contador = db.query(NumeracaoNFCe).filter(NumeracaoNFCe.serie == serie).with_for_update().first()
    if contador is None:
        contador = NumeracaoNFCe(serie=serie, ultimo_numero=0)
        db.add(contador)
        try:
            db.commit()
        except IntegrityError:
            # Two concurrent requests both tried to INSERT for the same serie.
            # Roll back this transaction and re-query to get the row created by the other request,
            # then lock it and proceed to the increment.
            db.rollback()
        # Re-fetch with lock to ensure atomicity from this point forward.
        # After rollback, the row may now exist (created by a concurrent request).
        contador = db.query(NumeracaoNFCe).filter(NumeracaoNFCe.serie == serie).with_for_update().first()

    contador.ultimo_numero += 1
    db.commit()
    db.refresh(contador)
    return contador.ultimo_numero


def registrar_falha_apos_reserva(db: Session, serie: int, numero: int) -> None:
    """Marca `numero` (já reservado por `reservar_proximo_numero`) como
    pendente de inutilização -- usado quando a emissão falhou depois que o
    número já havia sido reservado (falha de assinatura, erro de rede antes
    da resposta da Sefaz, etc.), deixando um "buraco" na numeração que
    precisa ser formalmente inutilizado junto à Sefaz."""
    contador = db.query(NumeracaoNFCe).filter(NumeracaoNFCe.serie == serie).first()
    if contador is None:
        raise ValueError(f"Série {serie} não encontrada")
    pendentes = _parse_pendentes(contador.numeros_pendentes_inutilizacao)
    pendentes.add(numero)
    contador.numeros_pendentes_inutilizacao = ",".join(str(n) for n in sorted(pendentes))
    db.commit()


def numeros_reservados_nao_emitidos(db: Session, serie: int = 1) -> list[int]:
    """Lista os números da série ainda pendentes de inutilização (reservados
    mas nunca autorizados -- ver `registrar_falha_apos_reserva`)."""
    contador = db.query(NumeracaoNFCe).filter(NumeracaoNFCe.serie == serie).first()
    if contador is None:
        return []
    return sorted(_parse_pendentes(contador.numeros_pendentes_inutilizacao))


def _parse_pendentes(valor: str) -> set[int]:
    if not valor:
        return set()
    return {int(parte) for parte in valor.split(",") if parte}
