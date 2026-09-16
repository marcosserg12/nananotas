# Sistema de Emissão de Notas Fiscais — Nana Lanches

**Data:** 2026-09-16
**Status:** Aprovado para planejamento de implementação

## Contexto e objetivo

O Nana Lanches (restaurante do pai do usuário, CNPJ 26.423.780/0001-76, Brasília-DF)
usa hoje um sistema desktop/web genérico (com módulos de venda e até locação) só
para emitir notas fiscais de consumidor (NFC-e). O objetivo é substituir isso por
um sistema próprio, em Python, mais rápido e responsivo, cobrindo apenas o que o
restaurante realmente usa: cadastro de produtos, cadastro de clientes (PF/PJ),
criação de vendas/orçamentos, pagamento (à vista ou parcelado) e emissão da NFC-e
dentro das normas fiscais vigentes.

O pai do usuário já possui certificado digital e conta em algum provedor de
emissão fiscal (ainda não identificado qual). Este projeto não vai reimplementar a
comunicação com a SEFAZ — isso é delegado a um provedor de emissão fiscal como
serviço (API), abstraído atrás de uma interface própria para facilitar a troca de
provedor quando o provedor real do pai for identificado.

## Decisões confirmadas com o usuário

1. **Emissão fiscal via provedor/API** (não integração direta com SEFAZ, não
   apenas controle interno). Provedor de desenvolvimento/testes: **Focus NFe**
   (ambiente de homologação gratuito), atrás de uma camada de abstração
   (`FiscalProvider`) para trocar de provedor depois.
2. **Aplicação web local**, em Python (FastAPI), acessível de outros
   dispositivos na rede do restaurante (ex.: tablet no balcão).
3. **Um único usuário/login** (o pai como administrador) — sem múltiplos
   funcionários/permissões por enquanto.
4. **Banco de dados MySQL**, no servidor remoto já em uso
   (`DB_CONNECTION=mysql`, `DB_HOST=SEU_SERVIDOR_MYSQL`, `DB_PORT=3306`). Banco e
   usuário novos, a criar: sugestão `nana_lanches` / `nana_lanches_user`. A
   senha fica só no `.env` local, nunca no código ou no chat.
5. O leiaute do cupom fiscal (DANFE da NFC-e, com QR Code e protocolo de
   autorização) é sempre o retornado pelo provedor de emissão — o sistema não
   redesenha esse leiaute, para não correr risco de não conformidade.

## Fora de escopo nesta versão (YAGNI)

- Múltiplos usuários/permissões de acesso.
- Módulo de "locação" de produtos (presente no sistema antigo, mas não parece
  se aplicar a um restaurante — os campos "Disponível para Locação" e "Estoque
  Atual Locação" vistos nas imagens de referência não serão replicados).
- Nota fiscal modelo 55 (NF-e completa B2B) — apenas NFC-e modelo 65, com opção
  de identificar ou não o consumidor.
- Integração direta com SEFAZ (assinatura de XML, webservices por estado).
- Contingência offline manual — delegada ao provedor de emissão.
- Relatórios financeiros avançados — apenas um painel simples de vendas do dia.

## Arquitetura

- **Backend:** Python 3.12+, FastAPI.
- **ORM/migrações:** SQLAlchemy + Alembic.
- **Banco de dados:** MySQL (servidor remoto do usuário).
- **Frontend:** Jinja2 (server-side rendering) + HTMX (interações dinâmicas
  sem recarregar a página) + Tailwind CSS (responsivo, mobile/tablet-friendly).
- **Autenticação:** login único, sessão via cookie assinado, senha com hash
  (bcrypt/passlib).
- **Integração fiscal:** interface `FiscalProvider` com métodos
  `emitir(venda) -> NotaFiscal`, `consultar(referencia) -> status`,
  `cancelar(referencia, motivo)`. Implementação inicial: `FocusNFeProvider`.
- **Configuração:** arquivo `.env` (não versionado) com credenciais de banco,
  token da Focus NFe e ambiente (`homologacao`/`producao`).
- **Execução:** `uvicorn` local, acessível na rede Wi-Fi do restaurante.

## Modelo de dados (principal)

- `usuarios`: login do administrador.
- `categorias`: grupo do produto (ex.: Água Mineral, Sucos, Diversos).
- `produtos`: código interno, nome, código do fabricante, categoria, NCM,
  unidade, preço de custo, preço de venda, preço atacado, estoque atual,
  ativo/inativo.
- `clientes`: tipo (PF/PJ), nome/razão social, CPF/CNPJ, IE, endereço,
  telefone, e-mail. Registro padrão pré-cadastrado "Consumidor Final".
- `vendas`: número do orçamento, cliente (opcional — padrão Consumidor Final),
  data, status (orçamento/pago/cancelado), forma de pagamento, valor total,
  valor pago, troco.
- `venda_itens`: venda, produto, quantidade, preço unitário, preço total.
- `parcelas`: venda, número da parcela, valor, vencimento, status (pago/em
  aberto).
- `notas_fiscais`: venda, provedor, status (processando/autorizada/
  rejeitada/cancelada), número, série, chave de acesso, protocolo, URL do
  DANFE, URL do XML, mensagem de erro (se houver).

## Fluxos principais

1. **Login** → painel com vendas do dia e atalho "Nova Venda".
2. **Produtos**: listar agrupados por categoria (como na tela de referência),
   criar/editar, ativar/desativar.
3. **Clientes**: listar, criar/editar PF ou PJ, buscar por CPF/CNPJ/nome.
4. **Nova Venda**:
   a. Escolher cliente (padrão "Consumidor Final", ou buscar por CPF/CNPJ
      para identificar o consumidor na nota).
   b. Adicionar produtos (busca rápida, quantidade, preço vindo do cadastro,
      ajustável).
   c. Resumo do orçamento com total.
   d. Forma de pagamento + parcelas (se a prazo), com resumo das parcelas
      geradas.
   e. Confirmar venda → baixa o estoque, grava a venda como paga.
5. **Emitir NFC-e**: botão "Gerar Cupom Fiscal" → monta o payload a partir dos
   dados da venda → envia para a Focus NFe → aguarda autorização → grava chave
   de acesso, protocolo e link do DANFE.
6. **Imprimir**: abre o DANFE (gerado pelo provedor) para impressão na
   impressora térmica.
7. **Cancelar nota**: dentro do prazo legal (tipicamente 24h), botão de
   cancelamento que aciona `FiscalProvider.cancelar`.

## Testes e validação

- Testes automatizados (pytest) para regras de negócio: cálculo de total,
  geração de parcelas, baixa de estoque.
- Emissão de ponta a ponta testada no ambiente de homologação da Focus NFe
  (gratuito, não gera nota real) antes de qualquer uso em produção.
- Roteiro de teste manual guiado com o usuário antes de considerar o sistema
  pronto para uso real pelo pai.

## Pendências a resolver antes de ir para produção

- Identificar qual provedor/certificado digital o pai já usa hoje, para
  decidir se mantemos Focus NFe ou trocamos a implementação de
  `FiscalProvider`.
- Confirmar NCM/CFOP corretos por categoria de produto junto ao contador do
  restaurante (os valores vistos nas imagens de referência serão usados como
  sugestão inicial, não como verdade fiscal).
- Criar banco e usuário MySQL (`nana_lanches` / `nana_lanches_user`) no
  servidor informado e preencher a senha no `.env` local.
