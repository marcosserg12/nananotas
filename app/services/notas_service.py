from sqlalchemy.orm import Session

from app.models.nota_fiscal import NotaFiscal, StatusNota
from app.models.venda import StatusVenda, Venda
from app.services.fiscal.base import FiscalProvider


def emitir_nota(db: Session, venda_id: int, provider: FiscalProvider) -> NotaFiscal:
    venda = db.get(Venda, venda_id)
    if venda is None:
        raise ValueError("Venda não encontrada")
    if venda.status != StatusVenda.PAGO:
        raise ValueError("Venda ainda não foi paga — não é possível emitir nota fiscal")

    resultado = provider.emitir(venda)

    nota = db.query(NotaFiscal).filter(NotaFiscal.venda_id == venda_id).first()
    if nota is None:
        nota = NotaFiscal(venda_id=venda_id, referencia=resultado.referencia)
        db.add(nota)

    _aplicar_resultado(nota, resultado)
    db.commit()
    db.refresh(nota)
    return nota


def consultar_nota(db: Session, venda_id: int, provider: FiscalProvider) -> NotaFiscal:
    nota = db.query(NotaFiscal).filter(NotaFiscal.venda_id == venda_id).first()
    if nota is None:
        raise ValueError("Nota fiscal não encontrada para esta venda")

    resultado = provider.consultar(nota.referencia)
    _aplicar_resultado(nota, resultado)
    db.commit()
    db.refresh(nota)
    return nota


def cancelar_nota(db: Session, venda_id: int, motivo: str, provider: FiscalProvider) -> NotaFiscal:
    nota = db.query(NotaFiscal).filter(NotaFiscal.venda_id == venda_id).first()
    if nota is None:
        raise ValueError("Nota fiscal não encontrada para esta venda")
    if nota.status != StatusNota.AUTORIZADA:
        raise ValueError("Apenas notas autorizadas podem ser canceladas")

    resultado = provider.cancelar(nota.referencia, motivo)
    _aplicar_resultado(nota, resultado)
    db.commit()
    db.refresh(nota)
    return nota


def _aplicar_resultado(nota: NotaFiscal, resultado) -> None:
    nota.referencia = resultado.referencia
    nota.status = StatusNota(resultado.status)
    nota.numero = resultado.numero
    nota.serie = resultado.serie
    nota.chave_acesso = resultado.chave_acesso
    nota.protocolo = resultado.protocolo
    nota.url_danfe = resultado.url_danfe
    nota.url_xml = resultado.url_xml
    nota.mensagem_erro = resultado.mensagem_erro
