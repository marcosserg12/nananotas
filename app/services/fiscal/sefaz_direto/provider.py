from app.config import settings
from app.database import SessionLocal
from app.models.nota_fiscal import NotaFiscal
from app.models.venda import Venda
from app.services.fiscal.base import FiscalProvider, ResultadoFiscal
from app.services.fiscal.sefaz_direto import assinatura, evento_cancelamento, webservice_client, xml_builder
from app.services.fiscal.sefaz_direto.numeracao import registrar_falha_apos_reserva, reservar_proximo_numero

_PREFIXO_REFERENCIA = "nfce-venda-"

# Mapeia o `status` devolvido por `webservice_client.consultar_protocolo` para o
# vocabulário de `ResultadoFiscal.status`. Qualquer status da Sefaz que não
# apareça aqui (`nao_encontrado`, `rejeitado`, `erro`) cai no `else` de
# `consultar` abaixo e vira "rejeitada" -- nunca "processando" (ver
# constraint global do plano).
_STATUS_CONSULTA_PARA_RESULTADO = {
    "autorizado": "autorizada",
    "cancelado": "cancelada",
}


def _venda_id_da_referencia(referencia: str) -> int:
    """Extrai o `venda.id` embutido em `referencia` (formato
    `f"nfce-venda-{venda.id}"`, montado em `emitir` abaixo).

    `FiscalProvider.consultar`/`.cancelar` só recebem `referencia` (uma
    string), não a `Venda` nem o `NotaFiscal` -- essa é a única informação
    disponível para religar a operação à nota fiscal já persistida (que tem
    `chave_acesso`/`protocolo`, exigidos pelo webservice de consulta/evento).
    Ver a discussão de design no brief da task 6.
    """
    if not referencia.startswith(_PREFIXO_REFERENCIA):
        raise ValueError(f"Referência em formato inesperado para SefazDiretoProvider: {referencia!r}")
    sufixo = referencia[len(_PREFIXO_REFERENCIA):]
    try:
        return int(sufixo)
    except ValueError as exc:
        raise ValueError(f"Referência em formato inesperado para SefazDiretoProvider: {referencia!r}") from exc


def _buscar_nota_por_referencia(referencia: str) -> NotaFiscal:
    """Busca o `NotaFiscal` persistido correspondente a `referencia`, abrindo
    sua própria sessão (mesmo padrão usado em `emitir` para a numeração --
    `FiscalProvider.consultar`/`.cancelar` não recebem uma `Session`)."""
    venda_id = _venda_id_da_referencia(referencia)
    db = SessionLocal()
    try:
        nota = db.query(NotaFiscal).filter(NotaFiscal.venda_id == venda_id).first()
    finally:
        db.close()
    if nota is None:
        raise ValueError(f"Nenhuma nota fiscal encontrada para a referência {referencia!r} (venda_id={venda_id}).")
    if not nota.chave_acesso:
        raise ValueError(
            f"Nota fiscal da referência {referencia!r} não possui chave de acesso registrada "
            "(a emissão pode não ter sido autorizada ainda)."
        )
    return nota


class SefazDiretoProvider(FiscalProvider):
    # Identificador persistido em `NotaFiscal.provedor` (ver
    # `notas_service.emitir_nota`) -- exposto como constante de classe para
    # que `notas_service` não precise adivinhar/hardcodar o nome do provedor
    # ativo a partir do nome da classe.
    NOME_PROVEDOR = "sefaz_direto"

    def __init__(
        self,
        certificado_path: str | None = None,
        certificado_senha: str | None = None,
        ambiente: str | None = None,
        serie: int | None = None,
    ):
        self.certificado_path = certificado_path or settings.sefaz_certificado_path
        self.certificado_senha = certificado_senha or settings.sefaz_certificado_senha
        self.ambiente = ambiente or settings.sefaz_ambiente
        self.serie = serie or settings.sefaz_serie

    def emitir(self, venda: Venda) -> ResultadoFiscal:
        referencia = f"nfce-venda-{venda.id}"
        # `numero` só é atribuído depois que a reserva (abaixo) tiver sucesso --
        # continua None se a própria reserva falhar, para que
        # `_registrar_falha_apos_reserva_se_necessario` (Important #3) saiba
        # distinguir "número nunca chegou a ser reservado" (nada a registrar)
        # de "número reservado, mas emissão falhou depois" (precisa registrar).
        numero: int | None = None
        try:
            db = SessionLocal()
            try:
                numero = reservar_proximo_numero(db, serie=self.serie)
            finally:
                db.close()

            xml_sem_assinar = xml_builder.montar_nfce_xml(venda, numero=numero, serie=self.serie)
            xml_assinado = assinatura.assinar_xml(xml_sem_assinar, self.certificado_path, self.certificado_senha)
            resultado_ws = webservice_client.autorizar(xml_assinado, ambiente=self.ambiente)
        except Exception as exc:
            self._registrar_falha_apos_reserva_se_necessario(numero)
            return ResultadoFiscal(referencia=referencia, status="rejeitada", mensagem_erro=str(exc))

        if resultado_ws["status"] == "autorizado":
            return ResultadoFiscal(
                referencia=referencia,
                status="autorizada",
                numero=str(numero),
                serie=str(self.serie),
                chave_acesso=resultado_ws.get("chave_acesso"),
                protocolo=resultado_ws.get("protocolo"),
                # Rota do DANFE local (Task 7) -- este provedor gera o cupom
                # localmente (QR Code próprio), ao contrário do Focus NFe, que
                # populava este campo com um link externo. Sem isso,
                # nota.html nunca mostra o link "Imprimir cupom" (Important #4).
                url_danfe=f"/vendas/{venda.id}/nota/danfe",
            )
        # Rejeitado pela Sefaz ou erro de comunicação depois que o número já
        # foi reservado: o número fica "queimado" (nunca será reenviado com
        # este mesmo nNF) e precisa ser rastreado para inutilização formal
        # futura junto à Sefaz -- ver Important #3.
        self._registrar_falha_apos_reserva_se_necessario(numero)
        return ResultadoFiscal(
            referencia=referencia,
            status="rejeitada",
            mensagem_erro=resultado_ws.get("mensagem") or "Falha desconhecida na emissão",
        )

    def _registrar_falha_apos_reserva_se_necessario(self, numero: int | None) -> None:
        """Marca `numero` (se um número já havia sido reservado) como
        pendente de inutilização -- ver `numeracao.registrar_falha_apos_reserva`
        e `numeracao.numeros_reservados_nao_emitidos`. Sem isso, todo número
        "queimado" por uma emissão que falhou depois da reserva (erro de
        assinatura, rede, ou rejeição da Sefaz) desaparecia silenciosamente,
        deixando o mecanismo de rastreamento de inutilização (Task 8) inerte
        em produção (Important #3 da revisão final do branch).

        Abre sua própria `Session` (mesmo padrão já usado para
        `reservar_proximo_numero`/`_buscar_nota_por_referencia` acima --
        `FiscalProvider.emitir` não recebe uma `Session` de fora). Qualquer
        falha ao REGISTRAR essa pendência (ex.: erro de banco) é engolida
        aqui de propósito -- é um registro de acompanhamento best-effort, e
        não deve mascarar/sobrescrever o resultado real (autorizada/rejeitada)
        da emissão que `emitir` está retornando.
        """
        if numero is None:
            return
        db = SessionLocal()
        try:
            registrar_falha_apos_reserva(db, serie=self.serie, numero=numero)
        except Exception:
            pass
        finally:
            db.close()

    def consultar(self, referencia: str) -> ResultadoFiscal:
        try:
            nota = _buscar_nota_por_referencia(referencia)
            resultado_ws = webservice_client.consultar_protocolo(nota.chave_acesso, ambiente=self.ambiente)
        except Exception as exc:
            return ResultadoFiscal(referencia=referencia, status="rejeitada", mensagem_erro=str(exc))

        status = _STATUS_CONSULTA_PARA_RESULTADO.get(resultado_ws["status"])
        if status is None:
            return ResultadoFiscal(
                referencia=referencia,
                status="rejeitada",
                numero=nota.numero,
                serie=nota.serie,
                mensagem_erro=resultado_ws.get("mensagem")
                or f"Falha ao consultar a nota na Sefaz (status={resultado_ws['status']!r})",
            )
        return ResultadoFiscal(
            referencia=referencia,
            status=status,
            numero=nota.numero,
            serie=nota.serie,
            chave_acesso=resultado_ws.get("chave_acesso") or nota.chave_acesso,
            protocolo=resultado_ws.get("protocolo") or nota.protocolo,
        )

    def cancelar(self, referencia: str, motivo: str) -> ResultadoFiscal:
        """Cancela a NFC-e na Sefaz (evento 110111): monta o evento, assina com
        o certificado A1 e envia. Só devolve `ResultadoFiscal` quando a Sefaz
        ACEITOU o cancelamento; qualquer outra coisa (justificativa curta demais,
        prazo vencido, erro de rede, rejeição) levanta `ValueError` com o motivo
        -- de propósito, pra o chamador NÃO gravar nada: a nota continua
        "autorizada" no sistema, porque na Sefaz ela continua valendo."""
        nota = _buscar_nota_por_referencia(referencia)
        try:
            evento = evento_cancelamento.montar_evento(
                chave_acesso=nota.chave_acesso,
                protocolo=nota.protocolo,
                justificativa=motivo,
                ambiente=self.ambiente,
            )
            evento_assinado = assinatura.assinar_xml(
                evento, self.certificado_path, self.certificado_senha, nome_elemento="infEvento"
            )
            envio = evento_cancelamento.montar_envio(evento_assinado, webservice_client._gerar_id_lote())
            resultado_ws = webservice_client.cancelar(
                nota.chave_acesso, nota.protocolo, motivo, envio, ambiente=self.ambiente
            )
        except ValueError:
            raise
        except Exception as exc:  # noqa: BLE001 -- nunca deixar erro cru vazar pra tela
            raise ValueError(f"Falha ao cancelar a nota: {exc}") from exc

        if resultado_ws["status"] != "cancelado":
            raise ValueError(
                "A Sefaz não aceitou o cancelamento: "
                f"{resultado_ws.get('mensagem') or 'sem motivo informado'}. A nota continua válida."
            )
        return ResultadoFiscal(
            referencia=referencia,
            status="cancelada",
            numero=nota.numero,
            serie=nota.serie,
            chave_acesso=nota.chave_acesso,
            protocolo=nota.protocolo,
            url_danfe=nota.url_danfe,
            protocolo_cancelamento=resultado_ws.get("protocolo"),
        )
