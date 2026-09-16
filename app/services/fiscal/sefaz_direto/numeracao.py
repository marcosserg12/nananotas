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


def numeros_reservados_nao_emitidos(db: Session, serie: int = 1) -> list[int]:
    return []
