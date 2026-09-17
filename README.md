# Nana Lanches — Sistema de Vendas e Nota Fiscal

## Requisitos
- Python 3.12+
- Acesso ao servidor MySQL (host `SEU_SERVIDOR_MYSQL`, porta `3306`)
- Conta na Focus NFe (ambiente de homologação para testes, produção para notas reais)

## Configuração inicial

1. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```
2. Copie `.env.example` para `.env` e preencha:
   - `DB_DATABASE`, `DB_USERNAME`, `DB_PASSWORD`: banco `nana_lanches` e usuário
     `nana_lanches_user` criados no servidor MySQL informado.
   - `SECRET_KEY`: qualquer texto aleatório longo (assina a sessão de login).
     **Obrigatório** — o servidor recusa iniciar (`RuntimeError`) se essa
     variável não for definida, para evitar assinar sessões com um valor
     padrão publicamente conhecido.
   - `FOCUS_NFE_TOKEN`: token da conta Focus NFe (comece pelo ambiente de
     homologação, que é gratuito).
   - `FOCUS_NFE_AMBIENTE`: `homologacao` para testes, `producao` para notas reais.
3. Crie o banco e o usuário no servidor MySQL (rode isto uma vez, conectado
   como um usuário com privilégio de administrador, por exemplo `mysql -h
   SEU_SERVIDOR_MYSQL -P 3306 -u root -p`), ajustando a senha para a mesma que foi
   colocada em `DB_PASSWORD` no `.env`:
   ```sql
   CREATE DATABASE IF NOT EXISTS nana_lanches CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   CREATE USER IF NOT EXISTS 'nana_lanches_user'@'%' IDENTIFIED BY 'SUBSTITUA_POR_UMA_SENHA_FORTE';
   GRANT ALL PRIVILEGES ON nana_lanches.* TO 'nana_lanches_user'@'%';
   FLUSH PRIVILEGES;
   ```
4. Gere o script de migração inicial e revise-o antes de aplicar:
   ```bash
   alembic revision --autogenerate -m "estrutura inicial"
   ```
   Abra o arquivo criado em `migrations/versions/` e confira se as tabelas e
   colunas geradas fazem sentido antes de seguir para o próximo passo.
5. Aplique as migrações no banco:
   ```bash
   alembic upgrade head
   ```
6. Crie o usuário administrador e o cliente "Consumidor Final":
   ```bash
   python -m app.seed
   ```
7. Rode o servidor:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```
8. Acesse `http://localhost:8000` (ou `http://<ip-do-computador>:8000` de outro
   dispositivo na mesma rede Wi-Fi, como um tablet no balcão).

## Antes de emitir notas reais

- Teste a emissão completa no ambiente de homologação da Focus NFe primeiro —
  isso não gera nota fiscal válida, só simula.
- Os nomes de campos usados na integração (`app/services/fiscal/focus_nfe.py`)
  foram montados a partir do conhecimento geral da API da Focus NFe, sem
  acesso à documentação ao vivo no momento em que este sistema foi escrito.
  Antes de ligar em produção, confira o payload de emissão contra a
  documentação atual em `https://docs.focusnfe.com.br/api/nfce/` e ajuste os
  nomes de campo em `montar_payload`/`_parse` caso tenham mudado.
- Confirme o NCM correto de cada categoria de produto com o contador do
  restaurante — os valores usados como sugestão no cadastro (ex.: água
  mineral `22011000`) vieram do sistema anterior e não substituem orientação
  contábil.

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

### Limitações conhecidas desta integração

- **Cancelamento de nota autorizada ainda não funciona.**
  `SefazDiretoProvider.cancelar` (`app/services/fiscal/sefaz_direto/provider.py`)
  lança `NotImplementedError` de propósito — construir o cancelamento exige
  um construtor de XML novo para o evento `infEvento`/`tpEvento=110111`, que
  ainda não existe neste projeto. A rota `/vendas/{id}/nota/cancelar`
  detecta isso e devolve um erro 400 com mensagem clara ("Cancelamento de
  nota ainda não está disponível na integração direta com a Sefaz —
  funcionalidade pendente.") em vez de quebrar. Enquanto isso não for
  implementado, a única alternativa é o recurso já existente de "marcar nota
  como emitida manualmente" (`/vendas/{id}/nota/marcar-manual`) — ele serve
  para *registrar* a situação no sistema, mas **não cancela a nota na
  Sefaz de fato**; qualquer cancelamento real precisa ser resolvido fora do
  sistema (ex.: diretamente no ambiente da Sefaz-DF ou com o contador) até
  essa funcionalidade ser implementada.
- **A página da DANFE-NFC-e (`/vendas/{id}/nota/danfe`) não tem link em
  nenhuma outra tela do sistema ainda.** Para visualizá-la ou imprimi-la é
  preciso digitar a URL diretamente no navegador, substituindo `{id}` pelo
  id da venda.

## Rodando os testes

```bash
pytest
```

Os testes usam um banco SQLite em memória — não é necessário acesso ao MySQL
real nem à Focus NFe para rodá-los.
