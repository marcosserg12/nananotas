from app.config import settings
from app.database import SessionLocal
from app.models.nota_fiscal import NotaFiscal
from app.models.venda import Venda
from app.services.fiscal.base import FiscalProvider, ResultadoFiscal
from app.services.fiscal.sefaz_direto import assinatura, webservice_client, xml_builder
from app.services.fiscal.sefaz_direto.numeracao import reservar_proximo_numero

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
    def __init__(
        self,
        certificado_path: str | None = None,
        certificado_senha: str | None = None,
        ambiente: str | None = None,
    ):
        self.certificado_path = certificado_path or settings.sefaz_certificado_path
        self.certificado_senha = certificado_senha or settings.sefaz_certificado_senha
        self.ambiente = ambiente or settings.sefaz_ambiente

    def emitir(self, venda: Venda) -> ResultadoFiscal:
        referencia = f"nfce-venda-{venda.id}"
        try:
            db = SessionLocal()
            try:
                numero = reservar_proximo_numero(db, serie=1)
            finally:
                db.close()

            xml_sem_assinar = xml_builder.montar_nfce_xml(venda, numero=numero, serie=1)
            xml_assinado = assinatura.assinar_xml(xml_sem_assinar, self.certificado_path, self.certificado_senha)
            resultado_ws = webservice_client.autorizar(xml_assinado, ambiente=self.ambiente)
        except Exception as exc:
            return ResultadoFiscal(referencia=referencia, status="rejeitada", mensagem_erro=str(exc))

        if resultado_ws["status"] == "autorizado":
            return ResultadoFiscal(
                referencia=referencia,
                status="autorizada",
                numero=str(numero),
                serie="1",
                chave_acesso=resultado_ws.get("chave_acesso"),
                protocolo=resultado_ws.get("protocolo"),
            )
        return ResultadoFiscal(
            referencia=referencia,
            status="rejeitada",
            mensagem_erro=resultado_ws.get("mensagem") or "Falha desconhecida na emissão",
        )

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
        """NÃO IMPLEMENTADO -- bloqueio concreto identificado nesta task, não
        uma pendência mecânica de "wiring".

        `webservice_client.cancelar` (Task 5) já funciona e só precisa de
        `chave_acesso`/`protocolo_autorizacao` (resolvidos via
        `_buscar_nota_por_referencia`, igual a `consultar` acima) e de
        `xml_assinado_evento`: o XML do evento de cancelamento (schema do
        evento nacional NFe/NFC-e, `tpEvento=110111`), assinado.

        Esse XML não pode ser montado nem assinado hoje com o que existe no
        projeto:

        1. `xml_builder.py` (Task 3) só monta o XML da própria NFC-e
           (`infNFe`) -- não existe nenhuma função para montar o XML do
           *evento* de cancelamento (`infEvento`/`detEvento`).
        2. A `nfelib` instalada neste ambiente (verificado nesta task via
           `dataclasses.fields`) expõe `Tevento`/`Tevento.InfEvento`, mas
           `Tevento.InfEvento.DetEvento` é um grupo `xs:any` sem tipagem
           (campos `any_element`/`any_attributes`) -- ou seja, ao contrário
           do XML da NFC-e (Task 3, com classes tipadas para cada grupo), o
           conteúdo específico do cancelamento (`evCancNFe` com
           `descEvento`/`nProt`/`xJust`) precisaria ser montado manualmente
           como XML bruto (lxml), sem o mesmo grau de confiança que a Task 3
           teve para o XML da NFC-e (round-trip contra amostra oficial da
           própria `nfelib`). Também não há, neste módulo do pacote, uma
           classe de envelope pronta (`envEvento`) análoga a `Nfe` para a
           NFC-e.
        3. `assinatura.assinar_xml` (Task 4) tem `_localizar_inf_nfe`
           **fixo** em procurar a tag `{http://www.portalfiscal.inf.br/nfe}infNFe`
           -- não localiza `infEvento`. Reusá-la como está para assinar um
           evento falha (ou assina o elemento errado, silenciosamente, se o
           documento contiver por acaso uma tag `infNFe`). Assinar o evento
           corretamente exigiria generalizar essa função para aceitar o nome
           do elemento/atributo `Id` a referenciar -- uma mudança na Task 4,
           fora do escopo de "wiring" desta task.

        Implementar isso direito é, na prática, uma miniatura das Tasks 3+4
        para um documento diferente (evento, não NFe), com o mesmo rigor que
        elas tiveram (validação de schema, verificação criptográfica
        independente da assinatura) -- não algo que deveria ser
        "encaixado" às pressas aqui só para não deixar `NotImplementedError`.
        Por isso esta task entrega `consultar` funcional de verdade (não
        precisa de XML novo, só de `chave_acesso`, já resolvida acima) e
        deixa `cancelar` como stub explícito, documentado, para uma task de
        acompanhamento -- ver relatório desta task.
        """
        raise NotImplementedError(
            "SefazDiretoProvider.cancelar ainda não está implementado: falta um "
            "construtor de XML para o evento de cancelamento (tpEvento=110111) e "
            "assinatura.assinar_xml não suporta assinar infEvento (só infNFe). "
            "Ver docstring deste método para os detalhes do bloqueio."
        )
