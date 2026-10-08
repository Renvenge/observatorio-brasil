# Observatório Brasil

Projeto para ajudar a detectar possíveis casos de corrupção por meio de padrões suspeitos em contratos públicos brasileiros, com fontes verificáveis e hipóteses explicáveis. O propósito é permitir que qualquer pessoa examine o uso do dinheiro público e aprofunde a investigação com base em evidências.

**Versão inicial de pesquisa (0.2). Não comprova corrupção, não atribui culpa e não promete cobertura ou precisão de 100%.** Os critérios independem de partido, governo ou eleição. Órgão contratante não equivale a responsabilidade pessoal de um político.

## Recursos

- Coleta nacional de contratos publicados no PNCP por período, com paginação, retentativas e registro de falhas.
- Histórico local das versões observadas, identificador, data e hash SHA-256. O hash verifica a cópia, não a veracidade da fonte.
- Relatórios CSV/JSON com fontes e cobertura.
- Regra exploratória para valor global pelo menos 25% acima do inicial. Não é limite legal nem prova de superfaturamento.
- IA sem supervisão (Isolation Forest) para combinações atípicas, com nomes descritivos automáticos, evidências e explicações alternativas. Não exige chave paga de IA.
- Testes automatizados e monitor periódico no GitHub Actions.

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

## Fontes e cobertura

- PNCP: publicações dos últimos sete dias, fila rotativa de 20 contratos antigos por ciclo, aditivos, arquivos e histórico oficial.
- Obrasgov: cadastro nacional, varredura retomável de até 2.000 obras por ciclo; execução física, contratos e fases financeiras para até 10 obras por ciclo. A cobertura cresce gradualmente, não é integral.
- Portal da Transparência: conector para empenhos, liquidações, pagamentos e emendas. Depende do segredo `TRANSPARENCIA_API_KEY` nas configurações do repositório. Sem a chave, o painel mostra a indisponibilidade. Nunca inclua a chave em código ou relatórios.

Fontes oficiais: [PNCP](https://pncp.gov.br/manual/pt-br/latest/singlehtml/), [Obrasgov](https://www.gov.br/obrasgov/pt-br/ferramentas-de-gestao-e-transparencia/api-de-dados-obrasgov-br_novo), [Portal da Transparência](https://api.portaldatransparencia.gov.br/swagger-ui/index.html).

## Painel e atualização

[Abrir o painel público](https://observatorio-brasil-renvenge.jose-breno1.chatgpt.site).

A pasta `web` contém o painel público, sem dependências de compilação. Busca por cidade, órgão, fornecedor e objeto; filtro de UF; alertas, fontes, histórico e exportação da seleção. Lê `current.json` no ramo `data` deste repositório. Atualiza a leitura a cada cinco minutos; a coleta ocorre a cada seis horas, conforme disponibilidade das fontes e do GitHub. Não é transmissão instantânea.

O workflow **Monitorar contratos** coleta, enriquece e exporta. Preserva versões originais no SQLite e publica um checkpoint comprimido, com SHA-256, no ramo `data`. Cada commit mantém o histórico anterior. Restauração valida checksum e integridade. Falha de restauração impede publicação substituta. Cache serve apenas à migração inicial; artefatos duram 30 dias.

O arquivo comprimido tem limite operacional de 80 MB e cada relatório 90 MB. Ao atingir o limite, a publicação falha preservando o último checkpoint remoto. Para expansão nacional sustentada será necessário migrar para banco/armazenamento dedicado; Git não é arquivo ilimitado. Agendamentos podem atrasar ou ser desativados pelo GitHub. Acompanhe **Actions** e a idade da última atualização no painel. Notificações externas dependem das preferências do proprietário no GitHub.

```powershell
python manage.py enrich --contracts 20 --work-pages 10 --work-details 10
python manage.py export
python manage.py backup data/backup.sqlite3.gz
python manage.py restore data/backup.sqlite3.gz
python -m http.server 8080 --directory web
```

Feche outras conexões ao banco antes de restaurar. O monitor local requer computador ligado; o GitHub Actions funciona independentemente dele.

## Revisão e comparação de preços

Revisão administrativa local, sem formulário público que permita adulterar resultados:

```powershell
python manage.py review ID_DO_ALERTA SHA256 supported --note "Evidências e justificativa da revisão"
```

Rótulos: `supported`, `false_positive`, `inconclusive`. A revisão fica vinculada ao alerta e à versão dos dados; mudanças tornam revisões antigas obsoletas. O painel mostra contagens e proporção entre hipóteses revisadas. Isso não mede precisão de detecção de corrupção nem elimina viés de seleção.

`python manage.py compare-prices arquivo.json` compara `item` e `reference`. Ambos exigem `item_code`, `specification`, `unit`, `uf`, `month`, `tax_regime`, `price_basis`, `source` e `unit_price`. Os sete primeiros campos precisam coincidir. Não existe comparação automática confiável apenas pelo valor total de um contrato. SINAPI/SICRO e planilhas de quantidades ainda precisam de aquisição, normalização e validação técnica antes de alimentar este comparador.

## Limites e trabalho dependente de dados/acessos

Não prometemos detectar toda corrupção. A IA propõe nomes descritivos para combinações atípicas, sem afirmar que descobriu um novo crime. Contratos com campos coincidentes geram hipótese de duplicidade, não prova de pagamento duplicado.

Ainda dependem de fontes e validação: cobertura histórica completa, todas as bases estaduais e municipais, leitura e validação de PDFs/medições, comparação automática SINAPI/SICRO, verificação histórica de vínculos societários e atribuição fundamentada a mandatos. Não inferimos responsabilidade pessoal pela data do contrato, nem vinculamos pagamentos a contratos apenas pelo nome do fornecedor. A API CGU pode publicar documentos com atraso; a fila implementada não garante capturar toda alteração retroativa.

Dados públicos podem conter informações pessoais. O painel não exporta CPF completo nem nome de fornecedor pessoa física; a seção de correspondências utiliza apenas CPF mascarado. O checkpoint preserva registros originais das APIs; sua publicação deve permanecer restrita a fontes públicas autorizadas. Não adicionar dados privados.

## Contribuir

Cada indicador precisa de fonte, explicação, exemplos legítimos que possam dispará-lo, testes de dados ausentes e critérios de revisão. Não incluir credenciais ou acusações nos commits. Hipóteses devem ser chamadas de hipóteses; discussões partidárias não substituem evidências.


## Candidaturas, sociedades e fornecedores

O monitor `political_monitor.py` cruza fornecedores PJ do PNCP com o quadro público de sócios e administradores da Receita e candidaturas do TSE. A rotina independente `Cruzar candidaturas e fornecedores` atualiza diariamente os anos 2022, 2024 e 2026 e as dez partes do mês mais recente da Receita. Compartilha a fila de publicação com o monitor principal para não sobrescrever coletas concorrentes.

Para anos anteriores ao ano corrente, são retidas candidaturas cujo resultado na fonte começa por ELEITO; para 2026, no ano de 2026, entram todas as candidaturas. Isso não verifica mandato atual. Os dados de 2024 consultados não contêm CPF utilizável e não geram correspondências automáticas.

Uma correspondência exige nome completo normalizado igual e as mesmas seis posições centrais visíveis do CPF. Os outros dígitos não são armazenados nos registros eleitorais nem reconstruídos. Homônimos e colisões continuam possíveis: o resultado é sempre **correspondência a conferir**, nunca identidade confirmada ou um sinal financeiro. A relação societária não estabelece favorecimento ou corrupção.

O CNPJ do fornecedor é associado pela raiz de oito caracteres, comum à matriz e filiais. O painel informa eleição, partido naquela eleição, situação eleitoral, mês da Receita, data de entrada societária, datas de consulta e fontes. Uma entrada posterior ao início do contrato recebe ressalva expressa. O QSA atual não comprova participação na época do contrato.

A cobertura mostra candidaturas com identificador utilizável, mês e partes societárias consultadas. Falhas preservam a última consulta válida; não significam ausência de relações. A rotina reconsulta as partes para incluir novos fornecedores. O download bruto fica apenas no diretório local ignorado e é removido após processamento; o checkpoint guarda somente as correspondências de fornecedores da base e os registros eleitorais minimizados.

Execução: `python political_monitor.py --parts 10`, seguida por `python manage.py export`. Não exige a chave da CGU.

## Coleta histórica e leitura local de PDFs

`python manage.py history --pages 5 --earliest 2021-01-01` consulta o PNCP por dia de publicação, começando sete dias antes da primeira execução e retrocedendo. O cursor permanece no banco e no checkpoint. Falhas de rede mantêm a página pendente; paginação inconsistente reinicia somente a janela afetada. Registros antigos não substituem detalhes já conhecidos. O monitor foi preparado para consultar cinco páginas adicionais por ciclo. A ampliação é gradual e não equivale à cobertura nacional completa; o checkpoint continua limitado a 80 MB comprimidos.

`python manage.py document URL_OFICIAL_PNCP --output data/documents/resultado.json` baixa e extrai texto de um PDF oficial do PNCP. O relatório local registra fonte, SHA-256, páginas, texto extraído e páginas pendentes. Limites: arquivo de 20 MB, 150 páginas, 500 mil caracteres e 60 segundos para processamento. Páginas sem texto exigem conferência ou OCR. O texto não é automaticamente publicado, interpretado como pagamento ou usado para afirmar irregularidades. A extração não executa OCR nem interpreta tabelas de preços. A integração em lote e o armazenamento durável dos documentos ainda estão pendentes.
