from sqlalchemy.orm import Session

from app.models.numeracao_nfce import NumeracaoNFCe


def reservar_proximo_numero(db: Session, serie: int = 1) -> int:
    contador = db.query(NumeracaoNFCe).filter(NumeracaoNFCe.serie == serie).first()
    if contador is None:
        contador = NumeracaoNFCe(serie=serie, ultimo_numero=0)
        db.add(contador)
        db.flush()

    contador.ultimo_numero += 1
    db.commit()
    db.refresh(contador)
    return contador.ultimo_numero


def numeros_reservados_nao_emitidos(db: Session, serie: int = 1) -> list[int]:
    return []
