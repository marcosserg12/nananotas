# Emissão direta de NFC-e junto à Sefaz-DF (sem provedor terceirizado)

**Data:** 2026-09-16
**Status:** Aprovado para planejamento de implementação

## Contexto e objetivo

O sistema Nana Lanches hoje emite NFC-e através da Focus NFe (um provedor de
emissão fiscal como serviço), implementado atrás da abstração
`app.services.fiscal.base.FiscalProvider`. Depois de avaliar o custo mensal
de provedores terceirizados (Focus NFe ~R$59,90/mês) e a alternativa gratuita
mas manual (Emissor Gratuito do SEBRAE, sem integração automática com o
sistema), o usuário decidiu que o sistema deve conversar **diretamente** com
a Sefaz-DF, sem nenhum intermediário pago, mesmo entendendo que isso é uma
tarefa de engenharia significativamente maior e que "zero erro possível" não
é uma meta realista para nenhum sistema de nota fiscal — a meta acordada é
que **todo erro seja detectado e visivelmente sinalizado**, nunca silencioso.

Este documento especifica um novo `FiscalProvider` — `SefazDiretoProvider` —
que substitui o uso ativo do `FocusNFeProvider` (mantido no código, inativo,
caso seja reativado no futuro) sem exigir nenhuma mudança no resto do
sistema (vendas, pagamento, tela de nota, checklist de pendências), graças à
abstração já existente.

## Decisões confirmadas com o usuário

1. **Sem modo de contingência formal.** Se a Sefaz-DF estiver indisponível no
   momento da emissão, o sistema não gera uma NFC-e provisória offline (o
   que a lei permite, mas exige um leiaute de DANFE especial e reenvio
   controlado). Em vez disso, a venda fica marcada como **pendente** no
   checklist já existente (`notas_service`/dashboard), com a mensagem de
   erro visível, e alguém tenta emitir de novo manualmente mais tarde.
2. **Todo erro deve ser detectável e visível — nunca silencioso.** Qualquer
   falha (rede, rejeição da Sefaz, resposta inesperada, certificado
   inválido) deve resultar em um registro de nota com status que apareça no
   checklist de pendências, com uma mensagem de erro legível em português.
   Nunca um status "processando"/"pendente" deve mascarar uma falha real —
   esse foi exatamente o Critical bug corrigido na integração com a Focus
   NFe, e a mesma disciplina se aplica aqui.
3. **Infraestrutura confirmada:** o Distrito Federal usa a infraestrutura
   compartilhada da **SVRS** (Sefaz Virtual do Rio Grande do Sul) para
   autorização de NFC-e. Endereços confirmados diretamente no site da
   Receita do DF:
   - Produção — Autorização: `https://nfce.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx`
   - Produção — Consulta Protocolo: `https://nfce.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx`
   - Produção — Status Serviço: `https://nfce.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx`
   - Produção — Inutilização: `https://nfce.svrs.rs.gov.br/ws/nfeinutilizacao/nfeinutilizacao4.asmx`
   - Produção — Recepção de Evento (cancelamento): `https://nfce.svrs.rs.gov.br/ws/recepcaoevento/recepcaoevento4.asmx`
   - Homologação: mesmos caminhos, trocando `nfce.svrs.rs.gov.br` por
     `nfce-homologacao.svrs.rs.gov.br`
   - QR Code (para o DANFE): base `http://www.fazenda.df.gov.br/nfce/qrcode?`
4. **Biblioteca de geração de XML:** `nfelib` (pacote `nfelib` no PyPI,
   mantido pela comunidade — Akretion/KMEE), que gera os bindings Python a
   partir dos XSD oficiais da NFC-e, evitando montar XML manualmente campo a
   campo.
5. **Certificado e senha:** o certificado (`.pfx`, já extraído do arquivo
   base64 fornecido pelo usuário) e sua senha ficam referenciados só via
   `.env` local (nunca no código, nunca commitados) — mesmo padrão já usado
   para `FOCUS_NFE_TOKEN`.
6. **Ambiente de testes primeiro.** Toda a implementação é validada contra o
   ambiente de homologação da SVRS antes de qualquer emissão em produção.

## Fora de escopo nesta versão (YAGNI)

- Modo de contingência offline formal (DANFE de contingência, reenvio
  automático) — explicitamente descartado pelo usuário.
- Carta de correção eletrônica (CC-e) — não solicitada.
- Emissão de NF-e modelo 55 (nota completa B2B) — o sistema já só lida com
  NFC-e modelo 65.
- Qualquer canal de alerta fora da própria tela do sistema (e-mail, SMS,
  WhatsApp) — o usuário confirmou que a tela/checklist já visível é
  suficiente, já que a emissão é feita em lote no fim do dia, com alguém
  ativamente na tela.

## Arquitetura

- **Novo módulo:** `app/services/fiscal/sefaz_direto.py`, contendo
  `SefazDiretoProvider(FiscalProvider)` — implementa `emitir`, `consultar`,
  `cancelar`, exatamente como `FocusNFeProvider` já faz, então
  `notas_service`, `notas_router` e a tela `vendas/nota.html` não mudam.
- **Geração de XML:** `nfelib` monta o objeto da NFC-e (emitente, destinatário
  opcional, itens, impostos, forma de pagamento) e serializa pro XML oficial.
  Os dados fiscais dos itens (NCM, CFOP, situação tributária) já existem no
  cadastro de produtos — a mesma lógica de mapeamento que existia em
  `focus_nfe.montar_payload` é adaptada para montar o objeto `nfelib` em vez
  de um payload JSON.
- **Assinatura digital:** uma biblioteca de assinatura XML (a confirmar
  durante a implementação — candidatos: `signxml` combinado com
  `cryptography` para carregar o `.pfx`) assina o XML com o certificado A1
  antes do envio, seguindo o padrão exigido pela Sefaz (assinatura sobre o
  elemento `infNFe`).
- **Comunicação com a Sefaz:** chamadas SOAP para os endereços da SVRS
  listados acima, usando `httpx` (já uma dependência do projeto) para o
  transporte HTTP e um envelope SOAP montado manualmente ou com apoio de uma
  biblioteca auxiliar — a decidir durante a implementação com base nos
  exemplos oficiais da `nfelib`.
- **Numeração sequencial:** nova tabela/contador (`app/models/numeracao_nfce.py`
  ou campo equivalente) rastreando o próximo número de NFC-e por série,
  garantindo que nunca haja número repetido. Números consumidos por
  tentativas que falharam antes de chegar à Sefaz precisam ser tratados via
  **inutilização** (serviço `NfeInutilizacao`) para não deixar buraco não
  justificado na numeração — implementado como uma rotina separada,
  executada quando uma falha é detectada e confirmada como "número não
  usado do lado da Sefaz".
- **Geração do DANFE:** um template HTML (baseado no leiaute do cupom de
  referência que o usuário enviou no início do projeto) mais uma imagem de
  QR Code gerada localmente (biblioteca `qrcode`, a adicionar às
  dependências), calculada a partir da chave de acesso e do hash exigido
  pela regra de QR Code da NFC-e. Substitui o `url_danfe` externo que a
  Focus NFe fornecia.
- **Config:** `.env` ganha `SEFAZ_CERTIFICADO_PATH`, `SEFAZ_CERTIFICADO_SENHA`,
  `SEFAZ_AMBIENTE` (homologacao/producao), seguindo o padrão de
  `FOCUS_NFE_*` já existente em `app/config.py`.
- **Provedor ativo:** `app/dependencies.get_fiscal_provider()` passa a
  retornar `SefazDiretoProvider` por padrão. `FocusNFeProvider` permanece no
  código, testado, mas inativo.

## Tratamento de erro e o checklist de pendências

Reaproveita a infraestrutura já construída:
- Qualquer falha (rede, rejeição, certificado, timeout) resulta em
  `NotaFiscal.status = REJEITADA` com `mensagem_erro` preenchida em
  português — nunca em `PROCESSANDO` como estado final silencioso.
- A venda continua aparecendo na função `vendas_pendentes_de_nota` (dashboard)
  até que uma nova tentativa seja bem-sucedida ou até ser marcada
  manualmente (`marcar_nota_emitida_manualmente`, já implementado, serve
  como via de escape caso a emissão direta falhe repetidamente e alguém
  precise usar o SEBRAE pra aquela nota específica pontualmente).

## Pendências a resolver durante a implementação (não bloqueiam o início)

- Confirmar a API exata da `nfelib` para montar o objeto NFC-e (nomes de
  classes/campos) direto na documentação/exemplos do pacote, já que o
  pacote pode ter mudado desde o conhecimento geral usado para escrever este
  documento.
- Confirmar se a autorização da NFC-e é síncrona (resposta imediata,
  `indSinc=1`) ou se exige consulta posterior via `NfeRetAutorizacao` — isso
  muda o fluxo de `emitir`/`consultar`.
- Confirmar a biblioteca de assinatura XML mais adequada e testada dentro do
  ecossistema `nfelib` (pode já vir com suporte embutido).
- Confirmar a fórmula exata do QR Code da NFC-e (parâmetros da URL,
  necessidade de hash adicional) contra o manual técnico vigente.
- Confirmar formato de erro retornado pela SVRS para garantir que a lógica
  de "nunca silencioso" cubra todos os casos de rejeição conhecidos.

Essas pendências não impedem o início do trabalho — cada uma delas vira uma
etapa explícita de pesquisa dentro da tarefa correspondente do plano de
implementação, com evidência (teste ou verificação) antes de prosseguir.

## Testes e validação

- Testes automatizados (pytest) cobrindo: montagem do objeto/XML da nota a
  partir de uma `Venda` (sem rede), assinatura de um XML de teste com um
  certificado de teste gerado na hora (não o certificado real do
  restaurante), e o parsing de respostas simuladas da Sefaz via `respx`
  (mesma técnica já usada para a Focus NFe — intercepta na camada de
  transporte, nenhum acesso de rede real).
- Antes de qualquer emissão em produção: pelo menos uma rodada completa de
  testes manuais no ambiente de homologação da SVRS (gratuito, não gera nota
  real), verificando autorização, consulta e cancelamento de uma nota de
  teste.
