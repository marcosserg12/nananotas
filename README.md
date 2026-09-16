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
   - `FOCUS_NFE_TOKEN`: token da conta Focus NFe (comece pelo ambiente de
     homologação, que é gratuito).
   - `FOCUS_NFE_AMBIENTE`: `homologacao` para testes, `producao` para notas reais.
3. Aplique as migrações no banco:
   ```bash
   alembic upgrade head
   ```
4. Crie o usuário administrador e o cliente "Consumidor Final":
   ```bash
   python -m app.seed
   ```
5. Rode o servidor:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```
6. Acesse `http://localhost:8000` (ou `http://<ip-do-computador>:8000` de outro
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

## Rodando os testes

```bash
pytest
```

Os testes usam um banco SQLite em memória — não é necessário acesso ao MySQL
real nem à Focus NFe para rodá-los.
