# Dicionário de Dados, Modelo Dimensional e Questões de Análise

## 1. Fontes externas

### 1.1 SENATRAN

Fonte bruta externa usada como referência de frota recarregável por município no Espírito Santo.

| Fonte | Arquivo | Descrição | Uso no pipeline |
|---|---|---|---|
| Externa | `camada_bronze/frota_senatran_bruta.xlsx` | Base bruta com frota veicular por UF, município e combustível | Orienta a simulação da Bronze e é tratada na Silver para gerar a visão consolidada de frota recarregável |

Campos esperados após normalização no tratamento:

| Campo | Tipo lógico | Descrição |
|---|---|---|
| `uf` | texto | UF do registro, padronizada para `ESPIRITO SANTO` quando aplicável |
| `municipio` | texto | Município normalizado em maiúsculas, sem acento |
| `combustivel` | texto | Tipo de combustível do veículo |
| `quantidade_veiculos` | numérico | Quantidade de veículos na combinação UF, município e combustível |

### 1.2 Selic do Banco Central

Fonte externa consumida via API e mantida em forma bruta na Bronze.

| Fonte | Arquivo | Descrição | Uso no pipeline |
|---|---|---|---|
| Externa | `camada_bronze/selic_bcb_bruta.csv` | Série histórica da Selic obtida da API do Banco Central | É tratada na Silver e comparada com a rentabilidade do fundo na Gold |

Campos brutos recebidos da API:

| Campo | Tipo lógico | Descrição |
|---|---|---|
| `data` | texto/data | Data da observação na API |
| `valor` | texto numérico | Taxa Selic do período |

## 2. Fontes criadas pelo código

### 2.1 Camada Bronze

| Arquivo | Tipo | Granularidade | Descrição | Principais campos |
|---|---|---|---|---|
| `camada_bronze/dim_fundo.csv` | Dimensão | 1 linha por fundo | Cadastro base do fundo Banestes Infra EV ESG FII | `id_fundo`, `nome_fundo`, `taxa_administracao`, `benchmark`, `data_inicio` |
| `camada_bronze/dim_projetos.csv` | Dimensão | 1 linha por projeto | Projetos simulados de eletropostos, distribuídos por município e demanda da frota | `id_projeto`, `municipio`, `uf`, `tipo_local`, `capex`, `opex_mensal`, `qtd_carregadores`, `potencia_instalada_kw`, `status`, `data_inicio_operacao`, métricas de frota e demanda |
| `camada_bronze/dim_cotistas.csv` | Dimensão | 1 linha por cotista | Cotistas simulados com município de origem, perfil de risco e valor investido | `id_cotista`, `perfil_risco`, `municipio_origem`, `uf`, `data_entrada`, `valor_investido` |
| `camada_bronze/fato_movimentacao_fundo.csv` | Fato | 1 linha por fundo e mês | Movimentação bruta mensal de aporte líquido | `id_fundo`, `data_referencia`, `aporte_liquido_mes` |
| `camada_bronze/fato_operacoes_recarga.csv` | Fato | 1 linha por operação | Operações brutas de recarga simuladas por projeto | `id_operacao`, `id_projeto`, `data_hora`, `municipio_origem_veiculo`, `uf_origem_veiculo`, `tipo_veiculo_recarregavel`, `veiculo_modelo`, `energia_consumida_kwh`, `tempo_utilizacao_min`, `preco_kwh_brl`, `receita_gerada_brl` |

### 2.2 Camada Silver

| Arquivo | Tipo | Granularidade | Descrição | Principais campos |
|---|---|---|---|---|
| `camada_silver/ext_senatran_es_silver.csv` | Dimensão externa tratada | 1 linha por UF, município e combustível agregado | Consolida a frota recarregável da SENATRAN para o Espírito Santo | `uf`, `municipio`, `frota_eletrica`, `frota_hibrida_plugin`, `frota_recarregavel`, `participacao_frota_es_pct`, `indice_demanda_senatran`, `classe_demanda_senatran` |
| `camada_silver/dim_fundo_silver.csv` | Dimensão | 1 linha por fundo | Fundo limpo, com tipos convertidos e duplicidades removidas | `id_fundo`, `nome_fundo`, `taxa_administracao`, `benchmark`, `data_inicio` |
| `camada_silver/dim_projetos_silver.csv` | Dimensão | 1 linha por projeto | Projetos validados contra a SENATRAN | campos da Bronze + `frota_recarregavel_senatran_atual`, `diferenca_frota_referencia` |
| `camada_silver/dim_cotistas_silver.csv` | Dimensão | 1 linha por cotista | Cotistas válidos com município e UF padronizados | `id_cotista`, `perfil_risco`, `municipio_origem`, `uf`, `data_entrada`, `valor_investido` |
| `camada_silver/fato_movimentacao_fundo_silver.csv` | Fato | 1 linha por fundo e mês | Aportes líquidos tratados | `id_fundo`, `data_referencia`, `aporte_liquido_mes` |
| `camada_silver/fato_operacoes_recarga_silver.csv` | Fato | 1 linha por operação | Operações tratadas com dimensões derivadas de tempo, custo e margem | campos da Bronze + `municipio_eletroposto`, `uf_eletroposto`, `data_referencia`, `ano_mes`, `hora_recarga`, `dia_semana`, `origem_local`, `custo_energia_brl`, `margem_bruta_brl` |
| `camada_silver/ext_selic_silver.csv` | Fato externo tratado | 1 linha por data | Série Selic filtrada e convertida para análise | `data_referencia`, `taxa_selic_mes` |
| `camada_silver/controle_qualidade_silver.csv` | Controle | 1 linha por tabela tratada | Log de qualidade com entradas, saídas e observações | `tabela`, `registros_bronze`, `registros_silver`, `registros_removidos`, `observacao` |

### 2.3 Camada Gold

| Arquivo | Tipo analítico | Granularidade | Finalidade |
|---|---|---|---|
| `camada_gold/gold_oportunidade_municipios.csv` | Tabela analítica municipal | 1 linha por município | Priorizar expansão e investimento com base em frota, déficit de infraestrutura e demanda observada |
| `camada_gold/gold_desempenho_projetos.csv` | Tabela analítica por projeto | 1 linha por projeto | Comparar receita, margem, energia, retorno e aderência à demanda estimada |
| `camada_gold/gold_operacoes_mensais.csv` | Série temporal | 1 linha por mês | Acompanhar evolução do volume e da receita das recargas ao longo do tempo |
| `camada_gold/gold_demanda_horaria.csv` | Série intradiária | 1 linha por hora | Identificar picos de demanda ao longo do dia |
| `camada_gold/gold_origem_recargas_municipios.csv` | Tabela geográfica | 1 linha por município de origem | Entender de onde vêm os veículos que carregam nos eletropostos |
| `camada_gold/gold_cotistas_municipio_perfil.csv` | Tabela de distribuição de investidores | 1 linha por município e perfil | Analisar distribuição do capital por origem geográfica e perfil de risco |
| `camada_gold/gold_lucro_projetos_mensal.csv` | Fato analítico mensal | 1 linha por projeto e mês | Medir lucro operacional mensal dos projetos ativos |
| `camada_gold/gold_desempenho_fundo_selic.csv` | Série financeira comparativa | 1 linha por mês | Comparar o fundo com a Selic e medir retorno excedente |
| `camada_gold/gold_resumo_fundo_selic.csv` | Resumo financeiro | 1 linha | Consolidar o resultado da comparação fundo x Selic |
| `camada_gold/gold_resumo_executivo.csv` | Resumo executivo | 1 linha | Reunir os principais KPIs do projeto em um único registro |