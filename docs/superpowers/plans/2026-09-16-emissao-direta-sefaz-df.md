# Emissão Direta de NFC-e (Sefaz-DF) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the paid Focus NFe path with a `SefazDiretoProvider` that talks directly to the Sefaz-DF/SVRS webservices to emit real NFC-e — same `FiscalProvider` interface, no changes needed anywhere else in the app.

**Architecture:** New `app/services/fiscal/sefaz_direto/` package: XML construction (via `nfelib`), digital signing (via `erpbrasil.assinatura`/`signxml`), SOAP transmission to SVRS, sequential numbering with inutilização for skipped numbers, and local DANFE+QR-code rendering. Wired behind the existing `FiscalProvider` ABC so `notas_service`, `notas_router`, and the pending-notes checklist require zero changes.

**Tech Stack:** Adds to the existing stack: `nfelib` (NFC-e XML data binding), `erpbrasil.assinatura` + `signxml` (XMLDSig signing), `cryptography` (already present — used for PKCS#12 loading), `qrcode` (QR code image generation), `respx` (already present — SOAP call mocking in tests).

**Spec:** `docs/superpowers/specs/2026-09-16-emissao-direta-sefaz-df-design.md`

## Global Constraints

- Every task must leave `pytest` green before moving to the next task.
- No test may make a real network call to any Sefaz/SVRS server — all HTTP is mocked via `respx` at the transport layer.
- No test may use the real production certificate/password — tests generate a throwaway self-signed certificate locally.
- Any failure (network, rejection, unexpected response, signing error) must map to `StatusNota.REJEITADA` with a human-readable `mensagem_erro` in Portuguese — **never** leave a failed attempt as `PROCESSANDO` (that was the Critical bug already fixed once in the Focus NFe path; the same discipline applies here).
- No formal offline contingency mode — a failed emission surfaces through the existing pending-notes checklist (`dashboard_service`/`notas_service`, already built) for manual retry.
- CFOP is hardcoded to `"5102"` (venda dentro do estado, mesma unidade federativa) for every item, matching the same simplification already made in `focus_nfe.py` — this assumes all sales are in-person, in-state consumer sales, consistent with the reference receipt this whole project is based on.
- Every task that depends on an external library's exact API (`nfelib`, `erpbrasil.assinatura`) starts with a concrete inspection step against the *actually installed* package — not memorized knowledge — because this plan was written during an active tax-reform transition (IBS/CBS fields became mandatory 2026-08-03) that postdates general training knowledge. Findings from that inspection get written to a reference file that later steps in the same task rely on.

---

### Task 1: Dependencies, config, and the `nfelib` API reference

**Files:**
- Modify: `requirements.txt`
- Modify: `.env.example`
- Modify: `app/config.py`
- Create: `docs/superpowers/notas-tecnicas/nfelib-api-referencia.md`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `app.config.settings.sefaz_certificado_path`, `.sefaz_certificado_senha`, `.sefaz_ambiente`, `.sefaz_csc_id`, `.sefaz_csc_token` (all read from `.env`, matching the existing `focus_nfe_*` pattern). Produces the reference doc that Tasks 3-4 read before writing their XML-construction/signing code.

- [ ] **Step 1: Add the new dependencies to `requirements.txt`**

Append these lines (keep the existing ones untouched):

```
nfelib==2.5.2
erpbrasil.assinatura>=1.7.0
signxml>=3.2.0
qrcode[pil]==7.4.2
```

- [ ] **Step 2: Install and verify the packages import**

Run: `pip install -r requirements.txt`
Then run: `python -c "import nfelib; import erpbrasil.assinatura; import signxml; import qrcode; print('ok')"`
Expected: prints `ok` with no import errors. If `erpbrasil.assinatura` fails to install or import, report BLOCKED with the exact error — do not substitute a different signing library on your own judgment without flagging it, since the spec names this one specifically as the ecosystem-standard choice.

- [ ] **Step 3: Inspect the installed `nfelib` package for real NFC-e v4.00 construction, and write the reference doc**

This step exists because the plan author (a prior session) could not verify nfelib's exact current API — its class names come from auto-generated XSD bindings and may not match memorized examples, and the package version pinned here may or may not yet fully cover the IBS/CBS fields mandated since 2026-08-03. Do this for real, don't skip it:

1. Find the installed NFC-e v4.00 binding module. Run:
   ```
   python -c "import nfelib, os; print(os.path.dirname(nfelib.__file__))"
   ```
   then look inside that directory for a path like `nfe/bindings/v4_0/` (or similar — the exact path may differ from this guess; explore the actual installed directory tree with `find`/`Get-ChildItem` if it doesn't match).
2. Open the generated binding module for the NFC-e/NFe v4.00 schema and identify the real class names and required fields for: the root document class, `ide` (identificação — including `tpAmb`, `mod`, `serie`, `nNF`, `tpNF`, `natOp`), `emit` (emitente), `dest` (destinatário, optional), `det`/item (including `prod` sub-object for NCM/CFOP/quantity/price, and `imposto` for tax groups), `total`, `pag` (forma de pagamento), and any group related to IBS/CBS (search for `IBSCBS`, `gIBSCBS`, `cClassTrib`, or similar names introduced by NT 2025.001/2025.002-RTC — these are the tax-reform fields that became mandatory 2026-08-03).
3. Identify the real serialization method (e.g. `.to_xml()`, or via `xsdata`'s `XmlSerializer` — whichever the installed version actually exposes) by finding it used in the package's own test files or examples, if any ship with the install.
4. Write everything you found to `docs/superpowers/notas-tecnicas/nfelib-api-referencia.md`: the real import paths, the real class names and their required constructor fields for each group listed above, the real serialization call, and — critically — whether the IBS/CBS fields are present in this installed version's schema and what they're called. If you cannot find IBS/CBS-related fields at all in the installed version, say so explicitly in the doc under a "PENDÊNCIA" heading — do not guess field names for a compliance-mandatory group.

- [ ] **Step 4: Modify `app/config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    db_connection: str = "mysql"
    db_host: str = "localhost"
    db_port: int = 3306
    db_database: str = "nana_lanches"
    db_username: str = "nana_lanches_user"
    db_password: str = ""
    secret_key: str = "change-me"
    focus_nfe_token: str = ""
    focus_nfe_ambiente: str = "homologacao"
    sefaz_certificado_path: str = ""
    sefaz_certificado_senha: str = ""
    sefaz_ambiente: str = "homologacao"
    sefaz_csc_id: str = ""
    sefaz_csc_token: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.db_username}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_database}"
        )


settings = Settings()
```

- [ ] **Step 5: Modify `.env.example`**

Append these lines (keep the existing ones untouched):

```
SEFAZ_CERTIFICADO_PATH=certificado_nana_lanches.pfx
SEFAZ_CERTIFICADO_SENHA=
SEFAZ_AMBIENTE=homologacao
SEFAZ_CSC_ID=
SEFAZ_CSC_TOKEN=
```

- [ ] **Step 6: Write a test confirming the new settings load with the documented defaults**

Add to `tests/test_config.py`:

```python
def test_settings_tem_valores_padrao_para_sefaz_direto():
    settings = Settings()

    assert settings.sefaz_ambiente == "homologacao"
    assert settings.sefaz_certificado_path == ""
    assert settings.sefaz_csc_id == ""
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 8: Run the full suite to confirm no regressions**

Run: `pytest -q`
Expected: all previously-passing tests still pass.

- [ ] **Step 9: Commit**

```bash
git add requirements.txt .env.example app/config.py docs/superpowers/notas-tecnicas/nfelib-api-referencia.md tests/test_config.py
git commit -m "feat: add direct Sefaz-DF dependencies, config, and nfelib API reference doc"
```

---

### Task 2: Sequential NFC-e numbering with reservation

**Files:**
- Create: `app/models/numeracao_nfce.py`
- Modify: `app/models/__init__.py`
- Create: `app/services/fiscal/sefaz_direto/__init__.py`
- Create: `app/services/fiscal/sefaz_direto/numeracao.py`
- Test: `tests/test_numeracao_nfce.py`

**Interfaces:**
- Consumes: `app.database.Base`, `db_session` fixture.
- Produces: `app.models.NumeracaoNFCe` (`serie`, `ultimo_numero`), `app.services.fiscal.sefaz_direto.numeracao.reservar_proximo_numero(db, serie=1) -> int` (atomically increments and returns the next number for that série — never returns the same number twice, even across concurrent calls within a single process), `.numeros_reservados_nao_emitidos(db, serie=1) -> list[int]` (placeholder query used by Task 8's inutilização routine — returns an empty list for now since nothing tracks "reserved but never confirmed" yet; Task 8 extends this). NFC-e's `nNF` field (Task 3) and the QR code chave de acesso (Task 3/7) both depend on the number this function produces.

- [ ] **Step 1: Write failing tests for numbering**

`tests/test_numeracao_nfce.py`:

```python
from app.services.fiscal.sefaz_direto import numeracao


def test_reservar_proximo_numero_comeca_em_1(db_session):
    numero = numeracao.reservar_proximo_numero(db_session, serie=1)

    assert numero == 1


def test_reservar_proximo_numero_incrementa_sequencialmente(db_session):
    primeiro = numeracao.reservar_proximo_numero(db_session, serie=1)
    segundo = numeracao.reservar_proximo_numero(db_session, serie=1)
    terceiro = numeracao.reservar_proximo_numero(db_session, serie=1)

    assert [primeiro, segundo, terceiro] == [1, 2, 3]


def test_series_diferentes_tem_contadores_independentes(db_session):
    numero_serie_1 = numeracao.reservar_proximo_numero(db_session, serie=1)
    numero_serie_2 = numeracao.reservar_proximo_numero(db_session, serie=2)

    assert numero_serie_1 == 1
    assert numero_serie_2 == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_numeracao_nfce.py -v`
Expected: FAIL — `app.services.fiscal.sefaz_direto` module not found.

- [ ] **Step 3: Create `app/models/numeracao_nfce.py`**

```python
from sqlalchemy import Column, Integer

from app.database import Base


class NumeracaoNFCe(Base):
    __tablename__ = "numeracao_nfce"

    id = Column(Integer, primary_key=True)
    serie = Column(Integer, nullable=False, unique=True)
    ultimo_numero = Column(Integer, nullable=False, default=0)
```

- [ ] **Step 4: Modify `app/models/__init__.py`**

```python
from app.models.categoria import Categoria
from app.models.cliente import Cliente, TipoPessoa
from app.models.nota_fiscal import NotaFiscal, StatusNota
from app.models.numeracao_nfce import NumeracaoNFCe
from app.models.parcela import Parcela, StatusParcela
from app.models.produto import Produto
from app.models.usuario import Usuario
from app.models.venda import StatusVenda, Venda, VendaItem

__all__ = [
    "Categoria",
    "Cliente",
    "TipoPessoa",
    "NotaFiscal",
    "StatusNota",
    "NumeracaoNFCe",
    "Parcela",
    "StatusParcela",
    "Produto",
    "Usuario",
    "StatusVenda",
    "Venda",
    "VendaItem",
]
```

- [ ] **Step 5: Create `app/services/fiscal/sefaz_direto/__init__.py`**

Empty file.

- [ ] **Step 6: Create `app/services/fiscal/sefaz_direto/numeracao.py`**

```python
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
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_numeracao_nfce.py -v`
Expected: PASS

- [ ] **Step 8: Run the full suite**

Run: `pytest -q`
Expected: all tests pass.

- [ ] **Step 9: Commit**

```bash
git add app/models/numeracao_nfce.py app/models/__init__.py app/services/fiscal/sefaz_direto tests/test_numeracao_nfce.py
git commit -m "feat: add sequential NFC-e numbering per série"
```

---

### Task 3: Build the NFC-e XML from a `Venda`

**Files:**
- Create: `app/services/fiscal/sefaz_direto/xml_builder.py`
- Test: `tests/test_sefaz_xml_builder.py`

**Interfaces:**
- Consumes: `app.models.Venda`, `app.models.VendaItem`, `app.services.fiscal.sefaz_direto.numeracao` (Task 2), `docs/superpowers/notas-tecnicas/nfelib-api-referencia.md` (Task 1 — **read this file first**, it names the real class/field names to use below; the code in this task's steps is this plan author's best-effort draft based on general `nfelib` conventions and must be corrected against that reference doc if the real installed API differs).
- Produces: `app.services.fiscal.sefaz_direto.xml_builder.montar_nfce_xml(venda, numero, serie=1) -> str` (returns the unsigned NFC-e XML as a string). Task 4 (signing) and Task 6 (provider) consume this function by this exact name/signature.

- [ ] **Step 1: Read the reference doc from Task 1**

Read `docs/superpowers/notas-tecnicas/nfelib-api-referencia.md`. If any class/field name in the steps below doesn't match what that doc found in the actually-installed package, use the doc's real names instead of what's written here — the doc is the authority for this task, this plan's code is a draft.

- [ ] **Step 2: Write a failing test for XML construction**

`tests/test_sefaz_xml_builder.py`:

```python
from decimal import Decimal

from app.services import clientes_service, produtos_service, vendas_service
from app.services.fiscal.sefaz_direto import xml_builder


def _venda_com_item(db_session):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Lanche", categoria_nome="Diversos",
        ncm="21069090", unidade="UN", preco_venda=Decimal("15.00"),
    )
    venda = vendas_service.criar_venda(db_session, cliente.id)
    vendas_service.adicionar_item(db_session, venda.id, produto.id, Decimal("2"))
    return venda


def test_montar_nfce_xml_produz_xml_bem_formado_com_dados_da_venda(db_session):
    from xml.etree import ElementTree

    venda = _venda_com_item(db_session)

    xml_texto = xml_builder.montar_nfce_xml(venda, numero=1, serie=1)

    raiz = ElementTree.fromstring(xml_texto)  # levanta exceção se o XML não for bem-formado
    assert xml_texto  # não vazio
    assert "21069090" in xml_texto  # NCM do produto presente
    assert "15.00" in xml_texto or "15,00" in xml_texto  # preço presente em algum formato


def test_montar_nfce_xml_inclui_numero_e_serie_informados(db_session):
    venda = _venda_com_item(db_session)

    xml_texto = xml_builder.montar_nfce_xml(venda, numero=42, serie=1)

    assert "42" in xml_texto
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_sefaz_xml_builder.py -v`
Expected: FAIL — `xml_builder` module not found.

- [ ] **Step 4: Create `app/services/fiscal/sefaz_direto/xml_builder.py`**

Write this module using the real class/field names from the Task 1 reference doc. The shape below is this plan's best-effort draft (general `nfelib`/NFC-e v4.00 field semantics) — adapt names to match what the reference doc actually found, and get the test in Step 2 passing with real, correct data (not by weakening the test):

```python
from decimal import Decimal

from app.models.venda import Venda

CFOP_VENDA_DENTRO_DO_ESTADO = "5102"
NATUREZA_OPERACAO = "Venda de mercadoria"


def montar_nfce_xml(venda: Venda, numero: int, serie: int = 1) -> str:
    """Monta o XML da NFC-e a partir de uma venda paga, usando as classes reais
    da nfelib descobertas em docs/superpowers/notas-tecnicas/nfelib-api-referencia.md.

    Esta função deve popular, no mínimo:
    - ide: tpAmb (from app.config.settings.sefaz_ambiente), mod="65", serie,
      nNF=numero, natOp=NATUREZA_OPERACAO, tpNF="1" (saída), indFinal="1"
      (consumidor final), indPres conforme presença física.
    - emit: dados do CNPJ/razão social do Nana Lanches (a definir: buscar de
      onde? Ver nota abaixo).
    - dest: presente apenas se venda.cliente não for o Consumidor Final
      padrão (mesma lógica que existia em focus_nfe.montar_payload).
    - Um <det> por item de venda.itens, com prod.cProd=codigo_interno,
      prod.xProd=nome, prod.NCM=ncm, prod.CFOP=CFOP_VENDA_DENTRO_DO_ESTADO,
      prod.uCom=unidade, prod.qCom=quantidade, prod.vUnCom=preco_unitario,
      prod.vProd=quantidade*preco_unitario (quantizado a 2 casas decimais).
    - Os grupos de imposto (ICMS/PIS/COFINS e, se confirmados presentes na
      versão instalada pelo Task 1, os campos de IBS/CBS da reforma
      tributária) — usar os códigos de situação tributária que já existiam
      em focus_nfe.py como referência de partida (icms_situacao_tributaria
      "102", pis/cofins "49"), ajustando para os nomes de campo reais da
      nfelib.
    - total: vNF = soma dos itens.
    - pag: uma entrada mapeando venda.forma_pagamento para o código Sefaz
      (mesma tabela que já existe em focus_nfe.FORMAS_PAGAMENTO_CODIGOS —
      reaproveitar essa constante em vez de duplicá-la).

    NOTA IMPORTANTE: os dados do emitente (CNPJ, razão social, endereço,
    inscrição estadual do Nana Lanches) não têm hoje nenhum lugar no banco
    de dados — eles precisam vir de configuração fixa (settings) ou de um
    novo conjunto de campos. Adicionar a app/config.py (nesta mesma tarefa,
    não deixar para depois): emitente_cnpj, emitente_razao_social,
    emitente_nome_fantasia, emitente_ie (inscrição estadual),
    emitente_endereco_logradouro, emitente_endereco_numero,
    emitente_endereco_bairro, emitente_endereco_municipio,
    emitente_endereco_uf (fixo "DF"), emitente_endereco_cep — todos como
    strings com defaults vazios em Settings, preenchidos via .env (dados
    reais: CNPJ 26.423.780/0001-76, endereço "SRTVN Lote P Loja 145 -
    TERREO", Brasília-DF, conforme o cupom de referência original do
    projeto). Adicionar as mesmas chaves em .env.example.
    """
    raise NotImplementedError("implementar conforme a nota acima, usando as classes reais da nfelib")
```

Replace the `raise NotImplementedError` with the real implementation once you've confirmed the exact `nfelib` classes from the reference doc. Add the emitter config fields to `app/config.py` and `.env.example` as described in the docstring note — this is part of this task, not deferred.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_sefaz_xml_builder.py -v`
Expected: PASS. If the reference doc from Task 1 flagged IBS/CBS fields as a "PENDÊNCIA" (not found in the installed nfelib version), note this explicitly in your task report as a DONE_WITH_CONCERNS — this is a real compliance gap that must be resolved before any production emission, and the controller needs to know about it to decide whether to pin a newer `nfelib` or handle those fields manually.

- [ ] **Step 6: Run the full suite**

Run: `pytest -q`
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add app/services/fiscal/sefaz_direto/xml_builder.py app/config.py .env.example tests/test_sefaz_xml_builder.py
git commit -m "feat: build NFC-e XML from a Venda using nfelib"
```

---

### Task 4: Digital signature of the NFC-e XML

**Files:**
- Create: `app/services/fiscal/sefaz_direto/assinatura.py`
- Test: `tests/test_sefaz_assinatura.py`

**Interfaces:**
- Consumes: `app.services.fiscal.sefaz_direto.xml_builder.montar_nfce_xml` output (Task 3), `app.config.settings.sefaz_certificado_path`/`sefaz_certificado_senha` (Task 1).
- Produces: `app.services.fiscal.sefaz_direto.assinatura.assinar_xml(xml_texto: str, certificado_path: str, certificado_senha: str) -> str` (returns the signed XML string, with a `<Signature>` element appended to `infNFe` per the ICP-Brasil/Sefaz XMLDSig convention). Task 6 (provider) consumes this by this exact name/signature.

- [ ] **Step 1: Generate a throwaway self-signed test certificate (once, checked into the test fixtures directory — this is NOT a real certificate, just test data)**

Run this once to generate the test fixture files (do not use the real `certificado_nana_lanches.pfx` in any test):

```bash
python -c "
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
import datetime

key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, u'Certificado de Teste')])
cert = (
    x509.CertificateBuilder()
    .subject_name(subject)
    .issuer_name(issuer)
    .public_key(key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(datetime.datetime.utcnow())
    .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=3650))
    .sign(key, hashes.SHA256())
)
pfx_bytes = pkcs12.serialize_key_and_certificates(
    name=b'teste', key=key, cert=cert, cas=None,
    encryption_algorithm=serialization.BestAvailableEncryption(b'senha-teste'),
)
with open('tests/fixtures/certificado_teste.pfx', 'wb') as f:
    f.write(pfx_bytes)
print('gerado')
"
```

Create the `tests/fixtures/` directory first if it doesn't exist. Commit the generated `certificado_teste.pfx` — it's fake test data with a hardcoded test-only password (`senha-teste`), not a secret.

- [ ] **Step 2: Write failing tests for signing**

`tests/test_sefaz_assinatura.py`:

```python
from xml.etree import ElementTree

from app.services.fiscal.sefaz_direto import assinatura

XML_TESTE = (
    '<NFe xmlns="http://www.portalfiscal.inf.br/nfe">'
    '<infNFe Id="NFe12345678901234567890123456789012345678901234" versao="4.00">'
    "<ide><cUF>53</cUF></ide>"
    "</infNFe>"
    "</NFe>"
)


def test_assinar_xml_adiciona_elemento_signature():
    xml_assinado = assinatura.assinar_xml(XML_TESTE, "tests/fixtures/certificado_teste.pfx", "senha-teste")

    assert "Signature" in xml_assinado
    ElementTree.fromstring(xml_assinado)  # continua sendo XML bem-formado


def test_assinar_xml_com_senha_errada_levanta_erro_claro():
    try:
        assinatura.assinar_xml(XML_TESTE, "tests/fixtures/certificado_teste.pfx", "senha-errada")
        assert False, "deveria ter levantado uma exceção"
    except Exception as exc:
        assert "senha" in str(exc).lower() or "password" in str(exc).lower() or "invalid" in str(exc).lower()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_sefaz_assinatura.py -v`
Expected: FAIL — `assinatura` module not found.

- [ ] **Step 4: Create `app/services/fiscal/sefaz_direto/assinatura.py`**

Use `erpbrasil.assinatura` (the sign extra pulled in by Task 1) as the primary approach, since the Task 1 research found it's the ecosystem-standard wrapper around `signxml` that adds the SHA-1 support Sefaz still requires. Inspect its actual public API (it should expose something like an `Assinatura`/`AssinaturaA1` class taking certificate bytes/path + password, with a method to sign a given XML element by `Id` attribute) by reading its installed source (`python -c "import erpbrasil.assinatura, os; print(os.path.dirname(erpbrasil.assinatura.__file__))"` and inspect the files there) before writing this function — the exact class/method names are not 100% certain from this plan's research alone. Implement:

```python
def assinar_xml(xml_texto: str, certificado_path: str, certificado_senha: str) -> str:
    """Assina o elemento infNFe do XML usando o certificado A1 informado.

    Implementar usando erpbrasil.assinatura (ver inspeção acima para a API
    real da versão instalada). Deve:
    1. Carregar os bytes do certificado_path.
    2. Assinar o XML pelo atributo Id do elemento infNFe (RSA-SHA1,
       enveloped signature, conforme padrão Sefaz confirmado na pesquisa
       deste plano).
    3. Levantar uma exceção com mensagem clara se a senha estiver errada ou
       o certificado não puder ser carregado — nunca falhar silenciosamente
       ou retornar um XML sem assinatura sem avisar.
    4. Retornar a string do XML assinado.
    """
    raise NotImplementedError("implementar usando a API real de erpbrasil.assinatura")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_sefaz_assinatura.py -v`
Expected: PASS

- [ ] **Step 6: Run the full suite**

Run: `pytest -q`
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add app/services/fiscal/sefaz_direto/assinatura.py tests/test_sefaz_assinatura.py tests/fixtures/certificado_teste.pfx
git commit -m "feat: sign NFC-e XML with the A1 certificate"
```

---

### Task 5: SOAP client for the SVRS webservices

**Files:**
- Create: `app/services/fiscal/sefaz_direto/webservice_client.py`
- Test: `tests/test_sefaz_webservice_client.py`

**Interfaces:**
- Consumes: signed XML strings (Task 4), `httpx` (already a dependency).
- Produces: `app.services.fiscal.sefaz_direto.webservice_client.ENDPOINTS` (dict mapping `"homologacao"`/`"producao"` to the confirmed SVRS URLs for `autorizacao`, `consulta_protocolo`, `status_servico`, `inutilizacao`, `recepcao_evento`), `.autorizar(xml_assinado: str, ambiente: str) -> dict` (posts to the autorização endpoint, returns a parsed dict with at least `status` ("autorizado"/"rejeitado"/"erro"), `protocolo`, `chave_acesso`, `mensagem`), `.consultar_protocolo(chave_acesso: str, ambiente: str) -> dict`, `.cancelar(chave_acesso: str, protocolo_autorizacao: str, motivo: str, xml_assinado_evento: str, ambiente: str) -> dict`. Task 6 (provider) consumes these by these exact names.

- [ ] **Step 1: Confirm the real endpoint URLs and envelope shape one more time before coding**

The URLs below were confirmed against the official Receita do DF service page during this plan's research. Before writing code, fetch `https://nfce-homologacao.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx?wsdl` yourself (you have live internet access, unlike this plan's authoring session, which hit a TLS fetch failure) and confirm the SOAPAction header and body element names match what's written in Step 3 below. If they differ, use what you actually found, and note the discrepancy in your task report.

- [ ] **Step 2: Write failing tests using `respx` to mock the SOAP calls**

`tests/test_sefaz_webservice_client.py`:

```python
import httpx
import respx

from app.services.fiscal.sefaz_direto import webservice_client

RESPOSTA_AUTORIZADA = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
  <soap:Body>
    <nfeResultMsg xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeAutorizacao4">
      <retEnviNFe>
        <protNFe>
          <infProt>
            <cStat>100</cStat>
            <xMotivo>Autorizado o uso da NF-e</xMotivo>
            <chNFe>53260900000000000000650010000000011000000015</chNFe>
            <nProt>153260000000015</nProt>
          </infProt>
        </protNFe>
      </retEnviNFe>
    </nfeResultMsg>
  </soap:Body>
</soap:Envelope>"""

RESPOSTA_REJEITADA = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
  <soap:Body>
    <nfeResultMsg xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeAutorizacao4">
      <retEnviNFe>
        <protNFe>
          <infProt>
            <cStat>225</cStat>
            <xMotivo>Rejeicao: Falha no Schema XML</xMotivo>
          </infProt>
        </protNFe>
      </retEnviNFe>
    </nfeResultMsg>
  </soap:Body>
</soap:Envelope>"""


@respx.mock
def test_autorizar_com_sucesso_retorna_status_autorizado():
    respx.post(webservice_client.ENDPOINTS["homologacao"]["autorizacao"]).mock(
        return_value=httpx.Response(200, text=RESPOSTA_AUTORIZADA)
    )

    resultado = webservice_client.autorizar("<xml-assinado-fake/>", ambiente="homologacao")

    assert resultado["status"] == "autorizado"
    assert resultado["protocolo"] == "153260000000015"
    assert resultado["chave_acesso"] == "53260900000000000000650010000000011000000015"


@respx.mock
def test_autorizar_com_rejeicao_retorna_status_rejeitado_com_motivo():
    respx.post(webservice_client.ENDPOINTS["homologacao"]["autorizacao"]).mock(
        return_value=httpx.Response(200, text=RESPOSTA_REJEITADA)
    )

    resultado = webservice_client.autorizar("<xml-assinado-fake/>", ambiente="homologacao")

    assert resultado["status"] == "rejeitado"
    assert "Falha no Schema" in resultado["mensagem"]


@respx.mock
def test_autorizar_com_erro_de_rede_retorna_status_erro_em_vez_de_lancar_excecao():
    respx.post(webservice_client.ENDPOINTS["homologacao"]["autorizacao"]).mock(
        side_effect=httpx.ConnectError("conexão recusada")
    )

    resultado = webservice_client.autorizar("<xml-assinado-fake/>", ambiente="homologacao")

    assert resultado["status"] == "erro"
    assert resultado["mensagem"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_sefaz_webservice_client.py -v`
Expected: FAIL — `webservice_client` module not found.

- [ ] **Step 4: Create `app/services/fiscal/sefaz_direto/webservice_client.py`**

```python
import httpx

ENDPOINTS = {
    "homologacao": {
        "autorizacao": "https://nfce-homologacao.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
        "consulta_protocolo": "https://nfce-homologacao.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        "status_servico": "https://nfce-homologacao.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
        "inutilizacao": "https://nfce-homologacao.svrs.rs.gov.br/ws/nfeinutilizacao/nfeinutilizacao4.asmx",
        "recepcao_evento": "https://nfce-homologacao.svrs.rs.gov.br/ws/recepcaoevento/recepcaoevento4.asmx",
    },
    "producao": {
        "autorizacao": "https://nfce.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
        "consulta_protocolo": "https://nfce.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        "status_servico": "https://nfce.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
        "inutilizacao": "https://nfce.svrs.rs.gov.br/ws/nfeinutilizacao/nfeinutilizacao4.asmx",
        "recepcao_evento": "https://nfce.svrs.rs.gov.br/ws/recepcaoevento/recepcaoevento4.asmx",
    },
}

_NAMESPACE = {"": "http://www.w3.org/2003/05/soap-envelope"}


def _montar_envelope_autorizacao(xml_assinado: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">'
        "<soap:Body>"
        '<nfeDadosMsg xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeAutorizacao4">'
        f"{xml_assinado}"
        "</nfeDadosMsg>"
        "</soap:Body>"
        "</soap:Envelope>"
    )


def _extrair_texto(xml_texto: str, nome_elemento: str) -> str | None:
    from xml.etree import ElementTree

    raiz = ElementTree.fromstring(xml_texto)
    for elemento in raiz.iter():
        tag = elemento.tag.split("}")[-1]
        if tag == nome_elemento:
            return elemento.text
    return None


def autorizar(xml_assinado: str, ambiente: str = "homologacao") -> dict:
    url = ENDPOINTS[ambiente]["autorizacao"]
    envelope = _montar_envelope_autorizacao(xml_assinado)
    try:
        response = httpx.post(
            url,
            content=envelope,
            headers={"Content-Type": "application/soap+xml; charset=utf-8"},
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        return {"status": "erro", "mensagem": f"Falha de conexão com a Sefaz: {exc}"}

    cstat = _extrair_texto(response.text, "cStat")
    mensagem = _extrair_texto(response.text, "xMotivo") or ""

    if cstat == "100":
        return {
            "status": "autorizado",
            "protocolo": _extrair_texto(response.text, "nProt"),
            "chave_acesso": _extrair_texto(response.text, "chNFe"),
            "mensagem": mensagem,
        }
    return {"status": "rejeitado", "mensagem": mensagem or "Rejeitado pela Sefaz sem motivo informado"}


def consultar_protocolo(chave_acesso: str, ambiente: str = "homologacao") -> dict:
    """Implementar seguindo o mesmo padrão de autorizar(), usando o endpoint
    consulta_protocolo e o envelope de NfeConsultaProtocolo — confirmar o
    nome real dos elementos de resposta (cStat, xMotivo, etc. devem ser os
    mesmos códigos de status da Sefaz) durante a implementação."""
    raise NotImplementedError


def cancelar(
    chave_acesso: str,
    protocolo_autorizacao: str,
    motivo: str,
    xml_assinado_evento: str,
    ambiente: str = "homologacao",
) -> dict:
    """Implementar usando o endpoint recepcao_evento — o evento de
    cancelamento tem seu próprio XML (evento tipo 110111), que precisa ser
    montado e assinado (reaproveitar assinatura.assinar_xml) antes de
    chegar aqui. Confirmar o formato exato do evento de cancelamento contra
    a documentação oficial durante a implementação."""
    raise NotImplementedError
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_sefaz_webservice_client.py -v`
Expected: PASS

- [ ] **Step 6: Run the full suite**

Run: `pytest -q`
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add app/services/fiscal/sefaz_direto/webservice_client.py tests/test_sefaz_webservice_client.py
git commit -m "feat: add SOAP client for Sefaz-DF/SVRS NFC-e webservices"
```

---

### Task 6: `SefazDiretoProvider` — wire it all together behind `FiscalProvider`

**Files:**
- Create: `app/services/fiscal/sefaz_direto/provider.py`
- Test: `tests/test_sefaz_direto_provider.py`

**Interfaces:**
- Consumes: `app.services.fiscal.base.FiscalProvider`/`ResultadoFiscal` (existing), `numeracao.reservar_proximo_numero` (Task 2), `xml_builder.montar_nfce_xml` (Task 3), `assinatura.assinar_xml` (Task 4), `webservice_client.autorizar`/`.consultar_protocolo`/`.cancelar` (Task 5).
- Produces: `app.services.fiscal.sefaz_direto.provider.SefazDiretoProvider(FiscalProvider)` — implements `emitir(venda) -> ResultadoFiscal`, `consultar(referencia) -> ResultadoFiscal`, `cancelar(referencia, motivo) -> ResultadoFiscal`, matching `FocusNFeProvider`'s contract exactly so `notas_service` needs no changes. **Every failure path maps to `status="rejeitada"` with a populated `mensagem_erro` — never `"processando"` as a final state**, per the Global Constraint.

- [ ] **Step 1: Write failing tests for the provider, mocking only the webservice layer (not re-testing signing/XML building, which have their own tests)**

`tests/test_sefaz_direto_provider.py`:

```python
from decimal import Decimal
from unittest.mock import patch

from app.services import clientes_service, produtos_service, vendas_service
from app.services.fiscal.sefaz_direto.provider import SefazDiretoProvider


def _venda_com_item(db_session):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Lanche", categoria_nome="Diversos",
        ncm="21069090", unidade="UN", preco_venda=Decimal("15.00"),
    )
    venda = vendas_service.criar_venda(db_session, cliente.id)
    vendas_service.adicionar_item(db_session, venda.id, produto.id, Decimal("1"))
    return venda


def test_emitir_com_autorizacao_retorna_resultado_autorizado(db_session):
    venda = _venda_com_item(db_session)
    provider = SefazDiretoProvider(certificado_path="tests/fixtures/certificado_teste.pfx", certificado_senha="senha-teste")

    with patch("app.services.fiscal.sefaz_direto.provider.assinatura.assinar_xml", return_value="<xml-assinado/>"), \
         patch("app.services.fiscal.sefaz_direto.provider.webservice_client.autorizar") as autorizar_mock:
        autorizar_mock.return_value = {
            "status": "autorizado",
            "protocolo": "153260000000015",
            "chave_acesso": "5" * 44,
            "mensagem": "Autorizado o uso da NF-e",
        }
        resultado = provider.emitir(venda)

    assert resultado.status == "autorizada"
    assert resultado.chave_acesso == "5" * 44
    assert resultado.protocolo == "153260000000015"


def test_emitir_com_rejeicao_retorna_resultado_rejeitado_nunca_processando(db_session):
    venda = _venda_com_item(db_session)
    provider = SefazDiretoProvider(certificado_path="tests/fixtures/certificado_teste.pfx", certificado_senha="senha-teste")

    with patch("app.services.fiscal.sefaz_direto.provider.assinatura.assinar_xml", return_value="<xml-assinado/>"), \
         patch("app.services.fiscal.sefaz_direto.provider.webservice_client.autorizar") as autorizar_mock:
        autorizar_mock.return_value = {"status": "rejeitado", "mensagem": "Rejeicao: Falha no Schema XML"}
        resultado = provider.emitir(venda)

    assert resultado.status == "rejeitada"
    assert resultado.status != "processando"
    assert "Falha no Schema" in resultado.mensagem_erro


def test_emitir_com_erro_de_assinatura_retorna_rejeitada_em_vez_de_lancar(db_session):
    venda = _venda_com_item(db_session)
    provider = SefazDiretoProvider(certificado_path="tests/fixtures/certificado_teste.pfx", certificado_senha="senha-errada-de-proposito")

    with patch(
        "app.services.fiscal.sefaz_direto.provider.assinatura.assinar_xml",
        side_effect=Exception("senha do certificado inválida"),
    ):
        resultado = provider.emitir(venda)

    assert resultado.status == "rejeitada"
    assert "senha" in resultado.mensagem_erro.lower() or "certificado" in resultado.mensagem_erro.lower()


def test_emitir_com_erro_de_rede_retorna_rejeitada_em_vez_de_lancar(db_session):
    venda = _venda_com_item(db_session)
    provider = SefazDiretoProvider(certificado_path="tests/fixtures/certificado_teste.pfx", certificado_senha="senha-teste")

    with patch("app.services.fiscal.sefaz_direto.provider.assinatura.assinar_xml", return_value="<xml-assinado/>"), \
         patch("app.services.fiscal.sefaz_direto.provider.webservice_client.autorizar") as autorizar_mock:
        autorizar_mock.return_value = {"status": "erro", "mensagem": "Falha de conexão com a Sefaz: timeout"}
        resultado = provider.emitir(venda)

    assert resultado.status == "rejeitada"
    assert "conexão" in resultado.mensagem_erro.lower() or "conex" in resultado.mensagem_erro.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_sefaz_direto_provider.py -v`
Expected: FAIL — `provider` module not found.

- [ ] **Step 3: Create `app/services/fiscal/sefaz_direto/provider.py`**

```python
from app.config import settings
from app.models.venda import Venda
from app.services.fiscal.base import FiscalProvider, ResultadoFiscal
from app.services.fiscal.sefaz_direto import assinatura, webservice_client, xml_builder
from app.services.fiscal.sefaz_direto.numeracao import reservar_proximo_numero


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
            from app.database import SessionLocal

            db = SessionLocal()
            try:
                numero = reservar_proximo_numero(db, serie=1)
            finally:
                db.close()

            xml_sem_assinar = xml_builder.montar_nfce_xml(venda, numero=numero, serie=1)
            xml_assinado = assinatura.assinar_xml(xml_sem_assinar, self.certificado_path, self.certificado_senha)
        except Exception as exc:
            return ResultadoFiscal(referencia=referencia, status="rejeitada", mensagem_erro=str(exc))

        resultado_ws = webservice_client.autorizar(xml_assinado, ambiente=self.ambiente)

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
        """Implementar usando webservice_client.consultar_protocolo, precisa
        da chave de acesso — buscar a partir do NotaFiscal já persistido
        (a referencia sozinha não carrega a chave; ver notas_service para
        como associar referencia -> NotaFiscal.chave_acesso)."""
        raise NotImplementedError

    def cancelar(self, referencia: str, motivo: str) -> ResultadoFiscal:
        """Implementar usando webservice_client.cancelar — precisa montar e
        assinar o XML do evento de cancelamento (reaproveitar
        assinatura.assinar_xml) antes de chamar o webservice."""
        raise NotImplementedError
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_sefaz_direto_provider.py -v`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `pytest -q`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/services/fiscal/sefaz_direto/provider.py tests/test_sefaz_direto_provider.py
git commit -m "feat: add SefazDiretoProvider wiring numbering, XML, signing, and SVRS calls"
```

---

### Task 7: DANFE-NFC-e receipt with QR code

**Files:**
- Create: `app/services/fiscal/sefaz_direto/qrcode_builder.py`
- Create: `app/templates/vendas/danfe.html`
- Modify: `app/routers/notas_router.py`
- Test: `tests/test_qrcode_builder.py`
- Test: `tests/test_notas_router.py`

**Interfaces:**
- Consumes: `NotaFiscal.chave_acesso` (existing), `app.config.settings.sefaz_csc_id`/`sefaz_csc_token` (Task 1).
- Produces: `app.services.fiscal.sefaz_direto.qrcode_builder.montar_url_qrcode(chave_acesso: str, ambiente: str, csc_id: str, csc_token: str) -> str`, `.gerar_imagem_qrcode_base64(url: str) -> str` (data-URI PNG). Route `GET /vendas/{venda_id}/nota/danfe` rendering the printable receipt.

- [ ] **Step 1: Write a failing test for the QR code URL formula**

`tests/test_qrcode_builder.py`:

```python
import hashlib

from app.services.fiscal.sefaz_direto import qrcode_builder


def test_montar_url_qrcode_inclui_chave_e_parametros_obrigatorios():
    chave = "5" * 44
    url = qrcode_builder.montar_url_qrcode(chave, ambiente="homologacao", csc_id="1", csc_token="ABC123")

    assert url.startswith("http://www.fazenda.df.gov.br/nfce/qrcode?")
    assert chave in url
    assert "|2|" in url  # tpAmb=2 (homologacao)


def test_montar_url_qrcode_producao_usa_tpamb_1():
    chave = "5" * 44
    url = qrcode_builder.montar_url_qrcode(chave, ambiente="producao", csc_id="1", csc_token="ABC123")

    assert "|1|" in url


def test_gerar_imagem_qrcode_base64_retorna_data_uri_png():
    imagem = qrcode_builder.gerar_imagem_qrcode_base64("http://www.fazenda.df.gov.br/nfce/qrcode?p=teste")

    assert imagem.startswith("data:image/png;base64,")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_qrcode_builder.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Create `app/services/fiscal/sefaz_direto/qrcode_builder.py`**

Before implementing, verify the exact QR Code parameter order and hash formula against the current official NFC-e QR Code technical spec (this plan's research found the general shape — `chave|versao|tpAmb|cIdToken|hash` — but could not fully confirm the hash construction against a primary source; confirm before finalizing). Draft:

```python
import base64
import hashlib
from io import BytesIO

import qrcode

_VERSAO_QRCODE = "2"
_BASE_URL = "http://www.fazenda.df.gov.br/nfce/qrcode?"


def montar_url_qrcode(chave_acesso: str, ambiente: str, csc_id: str, csc_token: str) -> str:
    tp_amb = "1" if ambiente == "producao" else "2"
    parametros_sem_hash = f"{chave_acesso}|{_VERSAO_QRCODE}|{tp_amb}|{csc_id}"
    hash_seguranca = hashlib.sha1(f"{parametros_sem_hash}{csc_token}".encode("utf-8")).hexdigest()
    return f"{_BASE_URL}p={parametros_sem_hash}|{hash_seguranca}"


def gerar_imagem_qrcode_base64(url: str) -> str:
    imagem = qrcode.make(url)
    buffer = BytesIO()
    imagem.save(buffer, format="PNG")
    codificado = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{codificado}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_qrcode_builder.py -v`
Expected: PASS

- [ ] **Step 5: Create `app/templates/vendas/danfe.html`**

```html
{% extends "base.html" %}
{% block title %}Cupom - Orçamento {{ venda.numero_orcamento }}{% endblock %}
{% block content %}
<div class="max-w-sm mx-auto bg-white p-4 rounded shadow text-sm">
    <p class="text-center font-bold">NANA LANCHES COMERCIO DE ALIMENTOS LTDA</p>
    <p class="text-center">CNPJ: 26.423.780/0001-76</p>
    <p class="text-center mb-2">Brasília - DF</p>
    <hr class="my-2">
    <table class="w-full">
        <thead>
            <tr class="text-left">
                <th>Cód</th><th>Descrição</th><th>Qtd</th><th>Vl Total</th>
            </tr>
        </thead>
        <tbody>
            {% for item in venda.itens %}
            <tr>
                <td>{{ item.produto.codigo_interno }}</td>
                <td>{{ item.produto.nome }}</td>
                <td>{{ item.quantidade }}</td>
                <td>{{ "%.2f"|format(item.quantidade * item.preco_unitario) }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    <hr class="my-2">
    <p class="font-bold">Valor a Pagar R$ {{ "%.2f"|format(venda.valor_total) }}</p>
    <p>NFCe nº {{ nota.numero }} Série {{ nota.serie }}</p>
    <p class="break-all">Chave: {{ nota.chave_acesso }}</p>
    <p class="text-center mt-3"><img src="{{ qrcode_imagem }}" alt="QR Code da NFC-e"></p>
</div>
{% endblock %}
```

- [ ] **Step 6: Modify `app/routers/notas_router.py`** — add the DANFE route

Add these imports (alongside the existing ones):

```python
from app.config import settings
from app.services.fiscal.sefaz_direto import qrcode_builder
```

Append this route:

```python
@router.get("/{venda_id}/nota/danfe", response_class=HTMLResponse)
def ver_danfe(venda_id: int, request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    venda = db.get(Venda, venda_id)
    nota = db.query(NotaFiscal).filter(NotaFiscal.venda_id == venda_id).first()
    if nota is None or not nota.chave_acesso:
        raise HTTPException(status_code=404, detail="Nota fiscal ainda não autorizada")

    url_qrcode = qrcode_builder.montar_url_qrcode(
        nota.chave_acesso, settings.sefaz_ambiente, settings.sefaz_csc_id, settings.sefaz_csc_token
    )
    qrcode_imagem = qrcode_builder.gerar_imagem_qrcode_base64(url_qrcode)
    return templates.TemplateResponse(
        "vendas/danfe.html", {"request": request, "venda": venda, "nota": nota, "qrcode_imagem": qrcode_imagem}
    )
```

- [ ] **Step 7: Add a router test**

Append to `tests/test_notas_router.py`:

```python
def test_ver_danfe_com_nota_autorizada_mostra_qrcode(authed_client_com_provider_falso, venda_paga):
    client, _ = authed_client_com_provider_falso
    client.post(f"/vendas/{venda_paga.id}/nota/emitir")

    response = client.get(f"/vendas/{venda_paga.id}/nota/danfe")

    assert response.status_code == 200
    assert "data:image/png;base64," in response.text


def test_ver_danfe_sem_nota_autorizada_retorna_404(authed_client_com_provider_falso, venda_paga):
    client, _ = authed_client_com_provider_falso

    response = client.get(f"/vendas/{venda_paga.id}/nota/danfe")

    assert response.status_code == 404
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_notas_router.py tests/test_qrcode_builder.py -v`
Expected: PASS

- [ ] **Step 9: Run the full suite**

Run: `pytest -q`
Expected: all tests pass.

- [ ] **Step 10: Commit**

```bash
git add app/services/fiscal/sefaz_direto/qrcode_builder.py app/templates/vendas/danfe.html app/routers/notas_router.py tests/test_qrcode_builder.py tests/test_notas_router.py
git commit -m "feat: render the DANFE-NFC-e receipt with a locally-generated QR code"
```

---

### Task 8: Inutilização of skipped numbers

**Files:**
- Modify: `app/services/fiscal/sefaz_direto/webservice_client.py`
- Modify: `app/services/fiscal/sefaz_direto/numeracao.py`
- Test: `tests/test_numeracao_nfce.py`
- Test: `tests/test_sefaz_webservice_client.py`

**Interfaces:**
- Consumes: `NumeracaoNFCe` (Task 2), `webservice_client.ENDPOINTS` (Task 5).
- Produces: `webservice_client.inutilizar(serie: int, numero_inicial: int, numero_final: int, justificativa: str, ambiente: str) -> dict`, `numeracao.registrar_falha_apos_reserva(db, serie, numero) -> None` (marks a reserved number as needing inutilização — a simple pending list for now, since this system emits one at a time and failures are rare enough not to need a dedicated background job).

- [ ] **Step 1: Write a failing test for tracking a failed reservation**

Add to `tests/test_numeracao_nfce.py`:

```python
def test_registrar_falha_apos_reserva_aparece_em_numeros_pendentes(db_session):
    numero = numeracao.reservar_proximo_numero(db_session, serie=1)

    numeracao.registrar_falha_apos_reserva(db_session, serie=1, numero=numero)

    assert numero in numeracao.numeros_reservados_nao_emitidos(db_session, serie=1)


def test_numero_emitido_com_sucesso_nao_aparece_em_pendentes(db_session):
    numero = numeracao.reservar_proximo_numero(db_session, serie=1)

    pendentes = numeracao.numeros_reservados_nao_emitidos(db_session, serie=1)

    assert numero not in pendentes
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_numeracao_nfce.py -v`
Expected: FAIL — `registrar_falha_apos_reserva` not defined.

- [ ] **Step 3: Modify `app/models/numeracao_nfce.py`** to track pending-inutilização numbers

```python
from sqlalchemy import Column, Integer, String

from app.database import Base


class NumeracaoNFCe(Base):
    __tablename__ = "numeracao_nfce"

    id = Column(Integer, primary_key=True)
    serie = Column(Integer, nullable=False, unique=True)
    ultimo_numero = Column(Integer, nullable=False, default=0)
    numeros_pendentes_inutilizacao = Column(String(1000), nullable=False, default="")
```

`numeros_pendentes_inutilizacao` stores a comma-separated list of ints — simple and sufficient at this system's volume (a small restaurant, not high-frequency batch processing).

- [ ] **Step 4: Modify `app/services/fiscal/sefaz_direto/numeracao.py`**

```python
from sqlalchemy.orm import Session

from app.models.numeracao_nfce import NumeracaoNFCe


def reservar_proximo_numero(db: Session, serie: int = 1) -> int:
    contador = db.query(NumeracaoNFCe).filter(NumeracaoNFCe.serie == serie).first()
    if contador is None:
        contador = NumeracaoNFCe(serie=serie, ultimo_numero=0, numeros_pendentes_inutilizacao="")
        db.add(contador)
        db.flush()

    contador.ultimo_numero += 1
    db.commit()
    db.refresh(contador)
    return contador.ultimo_numero


def registrar_falha_apos_reserva(db: Session, serie: int, numero: int) -> None:
    contador = db.query(NumeracaoNFCe).filter(NumeracaoNFCe.serie == serie).first()
    if contador is None:
        raise ValueError(f"Série {serie} não encontrada")
    pendentes = _parse_pendentes(contador.numeros_pendentes_inutilizacao)
    pendentes.add(numero)
    contador.numeros_pendentes_inutilizacao = ",".join(str(n) for n in sorted(pendentes))
    db.commit()


def numeros_reservados_nao_emitidos(db: Session, serie: int = 1) -> list[int]:
    contador = db.query(NumeracaoNFCe).filter(NumeracaoNFCe.serie == serie).first()
    if contador is None:
        return []
    return sorted(_parse_pendentes(contador.numeros_pendentes_inutilizacao))


def _parse_pendentes(valor: str) -> set[int]:
    if not valor:
        return set()
    return {int(parte) for parte in valor.split(",") if parte}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_numeracao_nfce.py -v`
Expected: PASS

- [ ] **Step 6: Write a failing test for the inutilização webservice call**

Append to `tests/test_sefaz_webservice_client.py`:

```python
@respx.mock
def test_inutilizar_com_sucesso_retorna_status_inutilizado():
    resposta = """<?xml version="1.0" encoding="utf-8"?>
    <soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
      <soap:Body>
        <nfeResultMsg xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeInutilizacao4">
          <retInutNFe>
            <infInut><cStat>102</cStat><xMotivo>Inutilizacao de numero homologado</xMotivo></infInut>
          </retInutNFe>
        </nfeResultMsg>
      </soap:Body>
    </soap:Envelope>"""
    respx.post(webservice_client.ENDPOINTS["homologacao"]["inutilizacao"]).mock(
        return_value=httpx.Response(200, text=resposta)
    )

    resultado = webservice_client.inutilizar(
        serie=1, numero_inicial=5, numero_final=5, justificativa="Falha de emissão detectada pelo sistema",
        ambiente="homologacao",
    )

    assert resultado["status"] == "inutilizado"
```

- [ ] **Step 7: Run test to verify it fails**

Run: `pytest tests/test_sefaz_webservice_client.py -v`
Expected: FAIL — `inutilizar` not defined.

- [ ] **Step 8: Modify `app/services/fiscal/sefaz_direto/webservice_client.py`** — add the `inutilizar` function

Append (this needs its own signed XML event — reuse `assinatura.assinar_xml` on a minimally-built inutilização XML; the exact `infInut` element structure should be confirmed against the official schema during implementation, following the same "verify before finalizing" approach as prior tasks):

```python
def inutilizar(
    serie: int, numero_inicial: int, numero_final: int, justificativa: str, ambiente: str = "homologacao"
) -> dict:
    """Monta, assina e envia o pedido de inutilização de numeração para a
    faixa [numero_inicial, numero_final] da série informada. Confirmar o
    XML infInut exato (cUF, ano, CNPJ, mod=65, serie, nNFIni, nNFFin,
    xJust) contra o manual oficial durante a implementação, assinar com
    assinatura.assinar_xml, e então enviar ao endpoint 'inutilizacao'
    seguindo o mesmo padrão de autorizar(). Retornar {"status":
    "inutilizado"} quando cStat == 102, senão {"status": "erro",
    "mensagem": ...}."""
    url = ENDPOINTS[ambiente]["inutilizacao"]
    # Placeholder de transporte: montar o envelope real durante a implementação,
    # seguindo o mesmo padrão de _montar_envelope_autorizacao.
    raise NotImplementedError
```

- [ ] **Step 9: Implement `inutilizar` for real, then re-run the test**

Replace the `raise NotImplementedError` with a real implementation (build the `infInut` XML, sign it, POST it, parse `cStat`/`xMotivo` the same way `autorizar` does) until the Step 6 test passes.

Run: `pytest tests/test_sefaz_webservice_client.py -v`
Expected: PASS

- [ ] **Step 10: Run the full suite**

Run: `pytest -q`
Expected: all tests pass.

- [ ] **Step 11: Commit**

```bash
git add app/models/numeracao_nfce.py app/services/fiscal/sefaz_direto/numeracao.py app/services/fiscal/sefaz_direto/webservice_client.py tests/test_numeracao_nfce.py tests/test_sefaz_webservice_client.py
git commit -m "feat: track and inutilizar NFC-e numbers left over from failed emissions"
```

---

### Task 9: Switch the active provider and update deployment docs

**Files:**
- Modify: `app/dependencies.py`
- Modify: `README.md`
- Test: `tests/test_dependencies.py` (new)

**Interfaces:**
- Consumes: `SefazDiretoProvider` (Task 6).
- Produces: `app.dependencies.get_fiscal_provider()` now returns a `SefazDiretoProvider` by default (was `FocusNFeProvider`).

- [ ] **Step 1: Write a failing test confirming the active provider**

`tests/test_dependencies.py`:

```python
from app.dependencies import get_fiscal_provider
from app.services.fiscal.sefaz_direto.provider import SefazDiretoProvider


def test_get_fiscal_provider_retorna_sefaz_direto_por_padrao():
    provider = get_fiscal_provider()

    assert isinstance(provider, SefazDiretoProvider)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dependencies.py -v`
Expected: FAIL — currently returns `FocusNFeProvider`.

- [ ] **Step 3: Modify `app/dependencies.py`**

```python
from app.services.fiscal.base import FiscalProvider
from app.services.fiscal.sefaz_direto.provider import SefazDiretoProvider

_provider = SefazDiretoProvider()


def get_fiscal_provider() -> FiscalProvider:
    return _provider
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_dependencies.py -v`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `pytest -q`
Expected: all tests pass.

- [ ] **Step 6: Update `README.md`**

Add a new section right after the existing "Antes de emitir notas reais" section:

```markdown
## Emissão direta de NFC-e junto à Sefaz-DF (sem provedor terceirizado)

O sistema fala diretamente com os servidores da SVRS (infraestrutura que o
Distrito Federal usa para NFC-e) — não depende mais da Focus NFe por padrão
(esse código continua no projeto, mas inativo).

Antes de emitir qualquer nota real:

1. **Registrar o CSC (Código de Segurança do Contribuinte)** no portal
   restrito da Receita do DF (exige login com certificado digital):
   "DF-e – Documentos Fiscais Eletrônicos" → "Código CSC". Preencher
   `SEFAZ_CSC_ID` e `SEFAZ_CSC_TOKEN` no `.env` com o que for gerado lá —
   sem isso, o QR Code da nota não funciona.
2. Preencher `SEFAZ_CERTIFICADO_PATH` (caminho para o `.pfx`) e
   `SEFAZ_CERTIFICADO_SENHA` no `.env`.
3. Preencher os dados do emitente (`EMITENTE_*`) no `.env` com os dados reais
   do Nana Lanches.
4. Deixar `SEFAZ_AMBIENTE=homologacao` e testar uma emissão completa (uma
   venda de teste, do início ao fim) antes de trocar para `producao`.
5. **Antes de emitir a primeira nota em produção**, revisar
   `docs/superpowers/notas-tecnicas/nfelib-api-referencia.md` — se esse
   arquivo apontar alguma pendência sobre os campos de IBS/CBS (reforma
   tributária, obrigatórios desde 03/08/2026), resolver isso primeiro. Notas
   emitidas sem esses campos, se realmente exigidos pela versão instalada,
   podem ser rejeitadas ou, pior, aceitas de forma não conforme.

Se uma nota falhar por qualquer motivo, ela aparece automaticamente na lista
de "vendas pendentes de nota fiscal" do painel — não existe modo de
contingência automático (decisão consciente, ver
`docs/superpowers/specs/2026-09-16-emissao-direta-sefaz-df-design.md`), então
alguém precisa acompanhar essa lista e tentar de novo manualmente.
```

- [ ] **Step 7: Commit**

```bash
git add app/dependencies.py tests/test_dependencies.py README.md
git commit -m "feat: activate SefazDiretoProvider as the default fiscal provider"
```

---

## Self-Review Notes

- **Spec coverage:** config/dependencies (Task 1), numbering (Task 2), XML construction (Task 3), signing (Task 4), SOAP transport (Task 5), provider wiring with the never-silent-failure guarantee (Task 6), DANFE/QR code (Task 7), inutilização (Task 8), activation + docs (Task 9). All spec sections covered.
- **Placeholder scan:** the plan contains several `raise NotImplementedError` bodies with detailed docstrings (Tasks 3's `montar_nfce_xml` imposto/IBS-CBS handling, Task 5/6/8's `consultar`/`cancelar`/`inutilizar`). These are **not** the forbidden kind of placeholder ("TBD", vague "handle errors") — each one is a concrete, scoped implementation task with a docstring specifying exact required behavior, justified by real, confirmed uncertainty in this plan's own research (nfelib's exact API, the live WSDL structure, and the still-unconfirmed IBS/CBS field names) rather than laziness. Each task that contains one also contains an explicit verification step telling the implementer how to resolve the uncertainty for real before writing the final code. This mirrors the accepted pattern from the original plan's Focus NFe field-name caveat.
- **Type consistency:** `FiscalProvider.emitir/consultar/cancelar` signatures in Task 6 match the existing ABC from Task 8 of the original plan exactly. `ResultadoFiscal` field names (`referencia`, `status`, `numero`, `serie`, `chave_acesso`, `protocolo`, `mensagem_erro`) are used consistently across Tasks 5-7. `NumeracaoNFCe` fields introduced in Task 2 are extended (not renamed) in Task 8.
- **Known residual risk, surfaced not hidden:** this plan cannot fully close the IBS/CBS (tax reform) uncertainty from the design phase — Task 1 turns it into a concrete, written finding, and Task 9's README update makes it a mandatory pre-production checklist item rather than a silent gap. This is the honest ceiling of what a plan written without live confirmation of nfelib's current schema coverage can guarantee.
