# Projeto BI Banestes EV — Bronze e Silver

## Ordem de execução

```bash
pip install -r requirements.txt
python 01_ingestao_bronze.py
python 02_tratamento_silver.py
```

## Camada Bronze

O script `01_ingestao_bronze.py`:

- gera dados internos fictícios de fundo, projetos, cotistas, rentabilidade e recargas;
- usa municípios reais do Espírito Santo;
- grava a UF como `ESPIRITO SANTO`;
- ingere a Selic bruta da API do Banco Central;
- mantém o arquivo bruto da SENATRAN na pasta Bronze;
- usa semente fixa para gerar sempre o mesmo conjunto de dados.

## Camada Silver

O script `02_tratamento_silver.py`:

- remove duplicidades por chave;
- converte datas e campos numéricos;
- padroniza municípios em maiúsculas e sem acentos para facilitar os relacionamentos;
- padroniza `ES`, `ESPÍRITO SANTO` e `ESPIRITO SANTO` como `ESPIRITO SANTO`;
- valida operações contra os projetos existentes;
- cria ano/mês, hora, custo de energia e margem bruta das recargas;
- trata fundo e rentabilidade, que antes não possuíam saída Silver;
- trata a Selic somente a partir do arquivo bruto da Bronze;
- filtra corretamente a SENATRAN por `ESPIRITO SANTO`;
- considera somente veículos recarregáveis em eletropostos: `ELETRICO`, `ELETRICO/FONTE EXTERNA` e `HIBRIDO PLUG-IN`;
- separa `frota_eletrica`, `frota_hibrida_plugin` e `frota_recarregavel`;
- gera `controle_qualidade_silver.csv` para documentar os tratamentos.

## Arquivos prontos para a futura Gold

- `dim_fundo_silver.csv`
- `dim_projetos_silver.csv`
- `dim_cotistas_silver.csv`
- `fato_rentabilidade_silver.csv`
- `fato_operacoes_recarga_silver.csv`
- `ext_selic_silver.csv`
- `ext_senatran_es_silver.csv`

A chave de relacionamento geográfico é o campo `municipio`, padronizado da mesma forma em projetos e SENATRAN.
