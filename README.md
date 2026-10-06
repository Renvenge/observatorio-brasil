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

## Fontes e cobertura

- PNCP: publicações dos últimos sete dias, fila rotativa de 20 contratos antigos por ciclo, aditivos, arquivos e histórico oficial.
- Obrasgov: cadastro nacional, varredura retomável de até 2.000 obras por ciclo; execução física, contratos e fases financeiras para até 10 obras por ciclo. A cobertura cresce gradualmente, não é integral.
- Portal da Transparência: conector para empenhos, liquidações, pagamentos e emendas. Depende do segredo `TRANSPARENCIA_API_KEY` nas configurações do repositório. Sem a chave, o painel mostra a indisponibilidade. Nunca inclua a chave em código ou relatórios.

Fontes oficiais: [PNCP](https://pncp.gov.br/manual/pt-br/latest/singlehtml/), [Obrasgov](https://www.gov.br/obrasgov/pt-br/ferramentas-de-gestao-e-transparencia/api-de-dados-obrasgov-br_novo), [Portal da Transparência](https://api.portaldatransparencia.gov.br/swagger-ui/index.html).

## Painel e atualização

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

Ainda dependem de fontes e validação: cobertura histórica completa, todas as bases estaduais e municipais, leitura e validação de PDFs/medições, comparação automática SINAPI/SICRO, vínculos societários e atribuição fundamentada a mandatos. Não inferimos responsabilidade pessoal pela data do contrato, nem vinculamos pagamentos a contratos apenas pelo nome do fornecedor. A API CGU pode publicar documentos com atraso; a fila implementada não garante capturar toda alteração retroativa.

Dados públicos podem conter informações pessoais. O painel não exporta CPF nem nome de fornecedor pessoa física. O checkpoint preserva registros originais das APIs; sua publicação deve permanecer restrita a fontes públicas autorizadas. Não adicionar dados privados.

## Contribuir

Cada indicador precisa de fonte, explicação, exemplos legítimos que possam dispará-lo, testes de dados ausentes e critérios de revisão. Não incluir credenciais ou acusações nos commits. Hipóteses devem ser chamadas de hipóteses; discussões partidárias não substituem evidências.
