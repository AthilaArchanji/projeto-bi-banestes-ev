# 3. Modelo dimensional

## 3.1 Visão geral

O projeto segue um modelo em estrela com quatro eixos principais de análise:

| Fato | Grão | Dimensões associadas | Métricas principais |
|---|---|---|---|
| `fato_operacoes_recarga_silver` / `gold_*` de operações | 1 recarga por operação | `dim_projetos_silver`, dimensão de tempo derivada, dimensão geográfica derivada | Energia, receita, custo, margem, tempo de utilização, origem local |
| `fato_movimentacao_fundo_silver` | 1 fundo por mês | `dim_fundo_silver`, dimensão de tempo derivada | Aporte líquido mensal |
| `gold_lucro_projetos_mensal` | 1 projeto por mês | `dim_projetos_silver`, dimensão de tempo derivada | Receita, custo de energia, margem bruta, custo de operação, lucro operacional |
| `gold_desempenho_fundo_selic` | 1 fundo por mês | `dim_fundo_silver`, `ext_selic_silver`, tempo derivado | Rentabilidade do fundo, Selic, retorno excedente, patrimônio, valor da cota |

## 3.2 Dimensões

### Dimensão Fundo

Fonte principal: `dim_fundo_silver.csv`

| Campo | Descrição |
|---|---|
| `id_fundo` | Chave do fundo |
| `nome_fundo` | Nome comercial do fundo |
| `taxa_administracao` | Taxa anual de administração |
| `benchmark` | Benchmark de referência |
| `data_inicio` | Data de início do fundo |

### Dimensão Projeto

Fonte principal: `dim_projetos_silver.csv`

| Campo | Descrição |
|---|---|
| `id_projeto` | Chave do projeto |
| `municipio`, `uf` | Localização do eletroposto |
| `tipo_local` | Tipo de instalação |
| `capex` | Investimento inicial |
| `opex_mensal` | Custo operacional mensal |
| `qtd_carregadores` | Quantidade de carregadores |
| `potencia_instalada_kw` | Potência instalada |
| `status` | Situação do projeto |
| `data_inicio_operacao` | Data de início da operação |
| métricas de frota e demanda | Apoiam a leitura de viabilidade e priorização |

### Dimensão Cotista

Fonte principal: `dim_cotistas_silver.csv`

| Campo | Descrição |
|---|---|
| `id_cotista` | Identificador do cotista |
| `perfil_risco` | Conservador, Moderado ou Arrojado |
| `municipio_origem` | Município de origem do investidor |
| `uf` | UF de origem |
| `data_entrada` | Data de entrada no fundo |
| `valor_investido` | Valor aportado |

### Dimensão Geográfica / SENATRAN

Fonte principal: `ext_senatran_es_silver.csv`

| Campo | Descrição |
|---|---|
| `uf` | UF padronizada |
| `municipio` | Município normalizado |
| `frota_eletrica` | Frota elétrica consolidada |
| `frota_hibrida_plugin` | Frota híbrida plug-in consolidada |
| `frota_recarregavel` | Soma da frota recarregável |
| `participacao_frota_es_pct` | Participação do município na frota recarregável do estado |
| `indice_demanda_senatran` | Índice sintético de demanda municipal |
| `classe_demanda_senatran` | Faixa de demanda: muito alta, alta, média, baixa ou sem frota |

### Dimensão Tempo

Não existe como tabela física única; é derivada nas tabelas Gold a partir de `data_referencia`, `ano_mes`, `hora_recarga` e similares.

| Campo derivado | Uso |
|---|---|
| `data_referencia` | Série mensal, diária ou timestamp base |
| `ano_mes` | Agrupamento mensal |
| `hora_recarga` | Análise horária |
| `dia_semana` | Análise comportamental das sessões |

## 3.3 Fatos

### Fato de Operações de Recarga

Grão: 1 linha por operação.

Chaves e atributos principais:

| Campo | Descrição |
|---|---|
| `id_operacao` | Identificador único da recarga |
| `id_projeto` | Chave para o projeto |
| `data_hora` | Data e hora da sessão |
| `municipio_origem_veiculo`, `uf_origem_veiculo` | Origem geográfica do veículo |
| `tipo_veiculo_recarregavel` | Elétrico ou híbrido plug-in |
| `energia_consumida_kwh` | Energia consumida |
| `tempo_utilizacao_min` | Duração da sessão |
| `preco_kwh_brl` | Preço por kWh |
| `receita_gerada_brl` | Receita da sessão |
| `custo_energia_brl` | Custo estimado de energia |
| `margem_bruta_brl` | Margem bruta da operação |
| `origem_local` | Indica se o veículo é do mesmo município do eletroposto |

### Fato de Movimentação do Fundo

Grão: 1 linha por fundo e mês.

| Campo | Descrição |
|---|---|
| `id_fundo` | Chave do fundo |
| `data_referencia` | Data de referência do mês |
| `aporte_liquido_mes` | Aporte líquido mensal |

### Fato Financeiro Mensal do Projeto

Grão: 1 linha por projeto e mês, criada em Gold.

| Campo | Descrição |
|---|---|
| `id_projeto` | Chave do projeto |
| `ano_mes` | Competência mensal |
| `quantidade_recargas` | Número de recargas no mês |
| `receita_projeto_brl` | Receita mensal |
| `custo_energia_projeto_brl` | Custo de energia no mês |
| `margem_bruta_projeto_brl` | Margem bruta mensal |
| `lucro_operacional_projeto_brl` | Lucro operacional após custo de operação |
| `retorno_operacional_mensal_sobre_capex_pct` | Retorno sobre o custo de projeto no mês |

### Fato Financeiro do Fundo x Selic

Grão: 1 linha por fundo e mês.

| Campo | Descrição |
|---|---|
| `id_fundo` | Chave do fundo |
| `ano_mes` | Competência mensal |
| `rentabilidade_fundo_pct` | Rentabilidade mensal do fundo |
| `taxa_selic_mes_pct` | Selic mensal |
| `retorno_excedente_pp` | Diferença em pontos percentuais |
| `fundo_superou_selic` | Indicador de superação |
| `valor_cota` | Valor da cota |
| `patrimonio_liquido` | Patrimônio líquido estimado |