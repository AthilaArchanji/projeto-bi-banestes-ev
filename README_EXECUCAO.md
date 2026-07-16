# Projeto BI Banestes EV — Bronze, Silver e Gold

## Ordem de execução

O arquivo `frota_senatran_bruta.xlsx` deve estar dentro de `camada_bronze` antes da execução.

```bash
pip install -r requirements.txt
python3 01_ingestao_bronze.py
python3 02_tratamento_silver.py
python3 03_geracao_gold.py
```

No Windows, também pode ser usado `python` ou `py` no lugar de `python3`.

## Camada Bronze

O script `01_ingestao_bronze.py`:

- preserva a planilha bruta da SENATRAN;
- considera somente `ELETRICO`, `ELETRICO/FONTE EXTERNA` e `HIBRIDO PLUG-IN` para orientar a simulação;
- distribui os projetos conforme a frota real recarregável de cada município;
- garante projetos para os municípios de maior frota e distribui os restantes por peso de demanda;
- aumenta carregadores, potência, CAPEX e demanda estimada em cidades com maior frota;
- gera operações de recarga em maior quantidade nos projetos associados a cidades com maior frota;
- registra a cidade de origem do veículo em cada operação;
- simula aproximadamente 82% das recargas como demanda local e o restante como deslocamento intermunicipal;
- diferencia veículos elétricos e híbridos plug-in na energia e duração das sessões;
- gera cotistas com municípios de origem reais do Espírito Santo;
- gera `aporte_liquido_mes` na rentabilidade do fundo;
- tenta atualizar a Selic e mantém o arquivo existente se a API estiver indisponível.

## Camada Silver

O script `02_tratamento_silver.py`:

- remove duplicidades e converte tipos;
- padroniza nomes de municípios e a UF como `ESPIRITO SANTO`;
- trata a SENATRAN antes das tabelas internas para validar municípios;
- calcula participação da frota, índice de demanda e classe de demanda municipal;
- valida projetos, cotistas e origens das operações contra os municípios da SENATRAN;
- relaciona cada recarga ao município do eletroposto e ao município de origem do veículo;
- cria `origem_local`, ano/mês, hora, dia da semana, custo de energia e margem bruta;
- valida `aporte_liquido_mes` na rentabilidade;
- trata a Selic a partir do arquivo bruto da Bronze;
- gera `controle_qualidade_silver.csv`.

## Camada Gold

O script `03_geracao_gold.py` cria tabelas agregadas prontas para o Power BI:

- `gold_oportunidade_municipios.csv`: frota, projetos, carregadores, recargas, déficit de infraestrutura e índice de oportunidade de investimento;
- `gold_desempenho_projetos.csv`: receita, margem, energia, atingimento da demanda e retorno operacional sobre o CAPEX;
- `gold_operacoes_mensais.csv`: evolução mensal das operações;
- `gold_demanda_horaria.csv`: horários de maior demanda;
- `gold_origem_recargas_municipios.csv`: municípios de origem dos veículos que utilizam os eletropostos;
- `gold_cotistas_municipio_perfil.csv`: distribuição de investidores;
- `gold_desempenho_fundo_selic.csv`: comparação mensal entre o fundo e a Selic;
- `gold_resumo_fundo_selic.csv`: resumo executivo da comparação com a Selic;
- `gold_resumo_executivo.csv`: principais indicadores do fundo e da operação.

## Relação entre SENATRAN e recargas simuladas

A quantidade de operações não é sorteada uniformemente. O peso de cada projeto considera:

- frota recarregável do município;
- quantidade de carregadores;
- quantidade de projetos existentes na mesma cidade;
- pequena variação aleatória para evitar valores perfeitamente lineares.

Com a semente atual, a correlação entre frota municipal e quantidade de recargas fica próxima de 1, demonstrando que a operação simulada segue a demanda indicada pela fonte externa, sem ser uma cópia exata.
