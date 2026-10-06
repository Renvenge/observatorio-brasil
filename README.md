# Observatório Brasil

Projeto para ajudar a detectar possíveis casos de corrupção por meio de padrões suspeitos em contratos públicos brasileiros, com fontes verificáveis e hipóteses explicáveis. O propósito é permitir que qualquer pessoa examine o uso do dinheiro público e aprofunde a investigação com base em evidências.

**Versão inicial de pesquisa (0.1). Não comprova corrupção, não atribui culpa e não promete cobertura ou precisão de 100%.** Os critérios independem de partido, governo ou eleição. Órgão contratante não equivale a responsabilidade pessoal de um político.

## Recursos

- Coleta nacional de contratos publicados no PNCP por período, com paginação, retentativas e registro de falhas.
- Histórico local das versões observadas, identificador, data e hash SHA-256. O hash verifica a cópia, não a veracidade da fonte.
- Relatórios CSV/JSON com fontes e cobertura.
- Regra exploratória para valor global pelo menos 25% acima do inicial. Não é limite legal nem prova de superfaturamento.
- IA sem supervisão (Isolation Forest) para combinações atípicas, com nomes descritivos automáticos, evidências e explicações alternativas. Não exige chave paga de IA.
- Nove testes automatizados e monitor periódico no GitHub Actions.

## Executar

Python 3.11 ou superior. Dentro da pasta do projeto:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m observatorio collect --start 2026-10-01 --end 2026-10-01
.venv\Scripts\python -m observatorio report --ai
.venv\Scripts\python -m observatorio status
.venv\Scripts\python -m unittest discover -s tests -v
```

Em Linux, use `.venv/bin/python`. Coleta e relatório sem `--ai` funcionam sem dependências externas. Saídas: `data/observatorio.sqlite3`, `reports/contratos.csv` e `reports/analise.json`, ignoradas pelo Git. `--max-pages 1` permite teste limitado e marca coleta parcial quando houver mais páginas. `complete` significa conclusão da consulta daquele período, não cobertura de todo o gasto público. A API não fornece uma fotografia transacional: mudanças durante a paginação podem exigir nova coleta.

## Como a IA funciona

Agrupa por UF, esfera, categoria e tipo de contrato. Exige pelo menos 30 registros válidos e cinco vetores distintos por grupo. Analisa valor global, proporção global/inicial e duração contratual. Registra somente combinações atípicas com ao menos duas dimensões afastadas da mediana.

Exemplo de nome: **Combinação incomum: variação relativa de valor acima da mediana e duração contratual acima da mediana**.

O nome descreve um padrão, não uma fraude comprovada ou necessariamente inédita. O escore não é probabilidade de corrupção. Ausência de alerta não comprova regularidade. Cada hipótese apresenta fonte, campos, modelo, grupo, alternativas e próximos passos. Grupos podem reunir objetos diferentes: não são comparações de preços unitários. Precisão real de detecção ainda não foi medida com base revisada por especialistas; testes de software não substituem essa validação.

## Fonte e cobertura

Fonte implementada: [API oficial de consulta do PNCP](https://pncp.gov.br/api/consulta/swagger-ui/index.html). [Dados abertos](https://www.gov.br/pncp/pt-br/acesso-a-informacao/copy_of_dados-abertos).

A consulta é por **data de publicação**, não por todas as alterações. Reconsultar o mesmo período preserva as versões alteradas observadas. Ainda falta acompanhamento individual permanente de contratos antigos. Valor contratado não equivale a dinheiro pago.

Não há integração de pagamentos, medições, emendas, SINAPI/SICRO, execução física, PDFs ou atribuição a mandatos nesta versão. Não há painel público nem serviço com garantia de disponibilidade. Nenhuma acusação é publicada automaticamente. Conferir documentos, contexto, comparabilidade e dados pessoais antes de divulgar conclusões.

## Atualização automática

O workflow **Monitorar contratos**, em GitHub Actions, agenda coleta a cada seis horas e permite execução manual. Reconsulta os últimos sete dias e disponibiliza CSV/JSON nos artefatos de cada execução por 30 dias. Os resultados são hipóteses exploratórias não revisadas, não denúncias.

O GitHub pode atrasar ou desativar agendamentos. O histórico entre execuções usa cache, que pode ser eliminado: **não é backup nem arquivo permanente**. Produção exige banco persistente, backups e alertas operacionais. O cache pode conter registros públicos originais; não adicionar dados privados.

Alternativa local:

```powershell
.venv\Scripts\python monitor.py --interval-minutes 360 --lookback-days 7
```

Exige computador ligado e rede. Não instala serviço nem inicia após reiniciar. Parar com Ctrl+C. A data segue America/Fortaleza (UTC−3). Falhas ficam no banco e terminal; o próximo ciclo tenta novamente. Não executar dois monitores sobre o mesmo banco.

## Próximas etapas

1. Banco persistente, backups, alertas operacionais e recuperação de falhas.
2. Acompanhamento de contratos antigos, aditivos e justificativas.
3. Painel de busca, histórico e cobertura para o público.
4. Pagamentos e obras, distinguindo empenho, liquidação, pagamento e contrato.
5. Calibração da IA com revisão humana e métricas de falsos positivos.
6. Mais fontes estaduais e municipais, preços comparáveis e documentos.

## Contribuir

Cada regra precisa de fonte, explicação, exemplos legítimos que possam dispará-la, testes de dados ausentes e critérios de revisão. Não incluir credenciais, dados coletados ou acusações nos commits. Hipóteses devem ser chamadas de hipóteses; discussões partidárias não substituem evidências.
