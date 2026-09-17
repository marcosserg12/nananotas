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

    # Rotula a nota com o provedor que de fato a emitiu -- sem isso, toda
    # nota fica marcada com o default do model ("focus_nfe"), mesmo quando
    # emitida pela integração direta com a Sefaz (bundle item da revisão
    # final do branch). `NOME_PROVEDOR` é opcional por design (um
    # `FiscalProvider` de teste/fake não precisa declará-lo), então isso não
    # sobrescreve `nota.provedor` quando o provider ativo não o expõe.
    nome_provedor = getattr(provider, "NOME_PROVEDOR", None)
    if nome_provedor:
        nota.provedor = nome_provedor

    _aplicar_resultado(nota, resultado)
    db.commit()
    db.refresh(nota)
    return nota


def marcar_nota_emitida_manualmente(db: Session, venda_id: int, chave_acesso: str | None = None) -> NotaFiscal:
    venda = db.get(Venda, venda_id)
    if venda is None:
        raise ValueError("Venda não encontrada")
    if venda.status != StatusVenda.PAGO:
        raise ValueError("Venda ainda não foi paga — não é possível marcar nota fiscal")

    nota = db.query(NotaFiscal).filter(NotaFiscal.venda_id == venda_id).first()
    if nota is None:
        nota = NotaFiscal(venda_id=venda_id, referencia=f"manual-venda-{venda_id}")
        db.add(nota)

    nota.provedor = "manual"
    nota.status = StatusNota.AUTORIZADA
    nota.chave_acesso = chave_acesso or None
    nota.mensagem_erro = None
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

    try:
        resultado = provider.cancelar(nota.referencia, motivo)
    except NotImplementedError:
        raise ValueError(
            "Cancelamento de nota ainda não está disponível na integração direta "
            "com a Sefaz — funcionalidade pendente."
        )
    _aplicar_resultado(nota, resultado)
    db.commit()
    db.refresh(nota)
    return nota


def _aplicar_resultado(nota: NotaFiscal, resultado) -> None:
    nota.referencia = resultado.referencia
    nota.status = StatusNota(resultado.status)
    # `numero`/`serie`/`chave_acesso`/`protocolo`: só sobrescreve quando o
    # novo valor é "truthy" -- preserva o valor já persistido quando o
    # `provider` devolve None para eles (ex.: `SefazDiretoProvider.consultar`
    # numa falha/erro transitório de rede não tem como saber esses valores,
    # então devolve None -- ver `ResultadoFiscal` nesses ramos). Sem isso, uma
    # falha transiente ao CONSULTAR uma nota já autorizada apagava
    # permanentemente a chave de acesso/protocolo reais dela (quebrando,
    # inclusive, a rota do DANFE, que depende de `chave_acesso`) -- Important
    # #6 da revisão final do branch.
    #
    # `status`/`mensagem_erro` continuam sendo sempre sobrescritos pelo
    # resultado mais recente, mesmo em falha -- é exatamente o ponto de
    # "nunca deixar silenciosamente como pendente" (ver constraint global do
    # plano): o status precisa refletir a última tentativa, mesmo quando ela
    # falhou.
    nota.numero = resultado.numero or nota.numero
    nota.serie = resultado.serie or nota.serie
    nota.chave_acesso = resultado.chave_acesso or nota.chave_acesso
    nota.protocolo = resultado.protocolo or nota.protocolo
    nota.url_danfe = resultado.url_danfe
    nota.url_xml = resultado.url_xml
    nota.mensagem_erro = resultado.mensagem_erro
