from datetime import date, datetime, time

from sqlalchemy.orm import Session

from app.models.cliente import Cliente
from app.models.nota_fiscal import NotaFiscal, StatusNota
from app.models.venda import StatusVenda, Venda
from app.services import email_service
from app.services.fiscal.base import FiscalProvider
from app.services.fiscal.sefaz_direto.xml_builder import FUSO_BRASILIA


def listar_notas(db: Session, cliente: str | None = None, data: date | None = None) -> list[NotaFiscal]:
    """`cliente` filtra pelo nome do cliente da venda (substring, sem
    diferenciar caixa); `data` filtra pela data de autorização da nota,
    observada em Brasília -- mesma janela dia-local -> UTC usada em
    `dashboard_service.vendas_do_dia`. Notas sem `autorizado_em` (ainda não
    autorizadas) nunca aparecem quando `data` é informada, porque não têm
    uma data real pra comparar."""
    query = db.query(NotaFiscal).join(Venda, NotaFiscal.venda_id == Venda.id)

    if cliente:
        query = query.join(Cliente, Venda.cliente_id == Cliente.id).filter(Cliente.nome.ilike(f"%{cliente}%"))

    if data:
        inicio_local = datetime.combine(data, time.min)
        fim_local = datetime.combine(data, time.max)
        inicio_utc = inicio_local - FUSO_BRASILIA
        fim_utc = fim_local - FUSO_BRASILIA
        query = query.filter(NotaFiscal.autorizado_em >= inicio_utc, NotaFiscal.autorizado_em <= fim_utc)

    return query.order_by(NotaFiscal.id.desc()).all()


def formatar_data_hora_local(momento_utc: datetime | None) -> str | None:
    """Converte `autorizado_em` (gravado em UTC) para a hora exibida em
    Brasília -- mesma conversão usada no DANFE (`danfe_pdf_service`)."""
    if momento_utc is None:
        return None
    return (momento_utc + FUSO_BRASILIA).strftime("%d/%m/%Y %H:%M")


def emitir_nota(db: Session, venda_id: int, provider: FiscalProvider) -> NotaFiscal:
    venda = db.get(Venda, venda_id)
    if venda is None:
        raise ValueError("Venda não encontrada")
    if venda.status != StatusVenda.PAGO:
        raise ValueError("Venda ainda não foi paga — não é possível emitir nota fiscal")

    nota = db.query(NotaFiscal).filter(NotaFiscal.venda_id == venda_id).first()
    # Sem esta guarda, chamar `emitir_nota` de novo para uma venda que já tem
    # uma nota com chave de acesso (mesmo que o status guardado seja
    # "rejeitada" por uma falha transitória ao CONSULTAR depois -- ver
    # `_aplicar_resultado`) chamaria `provider.emitir` outra vez: para o
    # `SefazDiretoProvider` real, isso reserva um número novo, monta um XML
    # novo e manda uma NFC-e de verdade, DISTINTA, pra Sefaz -- uma segunda
    # nota fiscal real para a mesma venda. A tela já esconde o botão nesse
    # caso, mas isso só protege contra clique acidental, não contra um
    # duplo-post (duplo clique, F5 num form, retry de rede) chegando direto
    # nesta rota. Só bloqueamos quando já existe uma chave de acesso de
    # verdade -- uma nota "processando" (sem chave ainda) continua podendo
    # ser retentada, é o caminho legítimo já coberto pelos testes existentes.
    if nota is not None and nota.chave_acesso:
        raise ValueError(
            "Esta venda já tem uma nota fiscal com chave de acesso -- emitir de novo criaria uma "
            "segunda nota fiscal real para a mesma venda. Para corrigir algo, cancele a nota "
            "existente antes de tentar de novo."
        )

    resultado = provider.emitir(venda)

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


def enviar_email_nota(db: Session, venda_id: int) -> NotaFiscal:
    """Envia (ou reenvia) o cupom fiscal por e-mail pro cliente da venda --
    usada tanto pelo envio automático logo após a emissão (best-effort,
    silenciosamente ignorado pelo chamador quando falha) quanto pelo botão
    manual de reenvio (onde a falha deve aparecer pro usuário)."""
    nota = db.query(NotaFiscal).filter(NotaFiscal.venda_id == venda_id).first()
    if nota is None or not nota.chave_acesso:
        raise ValueError("Nota fiscal ainda não autorizada -- não é possível enviar por e-mail")

    email_service.enviar_nota_por_email(nota.venda, nota)

    nota.email_enviado_em = datetime.utcnow()
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
    nota.protocolo_cancelamento = resultado.protocolo_cancelamento
    nota.cancelada_em = datetime.utcnow()
    nota.motivo_cancelamento = motivo
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
    nota.url_danfe = resultado.url_danfe or nota.url_danfe
    nota.url_xml = resultado.url_xml or nota.url_xml
    nota.mensagem_erro = resultado.mensagem_erro
    if nota.status == StatusNota.AUTORIZADA and nota.autorizado_em is None:
        nota.autorizado_em = datetime.utcnow()
