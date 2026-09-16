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

## Rodando os testes

```bash
pytest
```

Os testes usam um banco SQLite em memória — não é necessário acesso ao MySQL
real nem à Focus NFe para rodá-los.
