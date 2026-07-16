from pathlib import Path

import numpy as np
import pandas as pd

# A camada Gold contém tabelas de consumo prontas para análise e dashboard.
# Ela lê somente dados tratados da Silver, relaciona as fontes e gera métricas
# de negócio voltadas às decisões do banco e do fundo de investimento.
BASE_DIR = Path(__file__).resolve().parent
SILVER_DIR = BASE_DIR / "camada_silver"
GOLD_DIR = BASE_DIR / "camada_gold"
GOLD_DIR.mkdir(exist_ok=True)


def ler_silver(nome_arquivo, colunas_obrigatorias=None):
    """Lê uma tabela Silver e valida as colunas necessárias."""
    caminho = SILVER_DIR / nome_arquivo
    if not caminho.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {caminho}. Execute primeiro os scripts "
            "01_ingestao_bronze.py e 02_tratamento_silver.py."
        )

    df = pd.read_csv(caminho)
    colunas_obrigatorias = colunas_obrigatorias or []
    faltantes = [
        coluna for coluna in colunas_obrigatorias if coluna not in df.columns
    ]
    if faltantes:
        raise ValueError(
            f"O arquivo {nome_arquivo} não possui as colunas: {faltantes}"
        )
    return df


def padronizar_municipios_gold(df):
    """Padroniza os campos de município para uso geográfico no BI."""
    df_saida = df.copy()
    colunas_municipio = [
        "municipio",
        "municipio_origem",
        "municipio_eletroposto",
        "municipio_origem_veiculo",
        "municipio_maior_oportunidade"
    ]

    for coluna in colunas_municipio:
        if coluna in df_saida.columns:
            df_saida[coluna] = df_saida[coluna].apply(
                lambda valor: (
                    f"{str(valor).split(',')[0].strip().upper()} "
                    ", ESPIRITO SANTO, BRASIL"
                    if pd.notna(valor)
                    else valor
                )
            )

    return df_saida


def salvar_gold(df, nome_arquivo):
    caminho = GOLD_DIR / nome_arquivo
    df_saida = padronizar_municipios_gold(df)
    df_saida.to_csv(caminho, index=False)
    print(f"- {nome_arquivo}: {len(df_saida)} registros")


def divisao_segura(numerador, denominador):
    """Evita divisão por zero nos indicadores."""
    return np.where(denominador > 0, numerador / denominador, np.nan)


def score_percentil(serie):
    """Transforma uma medida positiva em um score de 0 a 100."""
    serie = pd.to_numeric(serie, errors="coerce").fillna(0)
    score = serie.rank(method="average", pct=True) * 100
    return np.where(serie > 0, score, 0)


print("Iniciando a geração da Camada Gold...")

# Fontes Silver compartilhadas por várias análises.
frota = ler_silver(
    "ext_senatran_es_silver.csv",
    [
        "uf", "municipio", "frota_eletrica", "frota_hibrida_plugin",
        "frota_recarregavel", "participacao_frota_es_pct",
        "indice_demanda_senatran", "classe_demanda_senatran"
    ]
)
projetos = ler_silver(
    "dim_projetos_silver.csv",
    [
        "id_projeto", "municipio", "uf", "tipo_local", "capex",
        "opex_mensal", "qtd_carregadores", "potencia_instalada_kw",
        "status", "data_inicio_operacao",
        "frota_recarregavel_municipio_ref", "indice_demanda_senatran",
        "classe_demanda_senatran", "demanda_mensal_estimada_recargas"
    ]
)
operacoes = ler_silver(
    "fato_operacoes_recarga_silver.csv",
    [
        "id_operacao", "id_projeto", "data_hora", "ano_mes",
        "hora_recarga", "municipio_eletroposto", "uf_eletroposto",
        "municipio_origem_veiculo", "uf_origem_veiculo", "origem_local",
        "tipo_veiculo_recarregavel", "energia_consumida_kwh",
        "tempo_utilizacao_min", "receita_gerada_brl",
        "custo_energia_brl", "margem_bruta_brl"
    ]
)

# -----------------------------------------------------------------------------
# 1. OPORTUNIDADE E VIABILIDADE POR MUNICÍPIO
# Responde:
# 1) Quais municípios possuem maior frota recarregável?
# 2) Quais municípios possuem mais projetos?
# 3) Quais possuem mais veículos por projeto/carregador?
# Também cria um índice para orientar expansão e investimento do fundo.
# -----------------------------------------------------------------------------
projetos_municipio = (
    projetos.groupby(["uf", "municipio"], as_index=False)
    .agg(
        quantidade_projetos=("id_projeto", "nunique"),
        projetos_em_operacao=(
            "status", lambda serie: (serie.str.upper() == "EM OPERAÇÃO").sum()
        ),
        projetos_em_construcao=(
            "status", lambda serie: (serie.str.upper() == "EM CONSTRUÇÃO").sum()
        ),
        capex_total_brl=("capex", "sum"),
        opex_mensal_total_brl=("opex_mensal", "sum"),
        quantidade_carregadores=("qtd_carregadores", "sum"),
        potencia_instalada_total_kw=("potencia_instalada_kw", "sum"),
        demanda_mensal_estimada_recargas=(
            "demanda_mensal_estimada_recargas", "sum"
        )
    )
)

operacoes_municipio = (
    operacoes.groupby(
        ["uf_eletroposto", "municipio_eletroposto"], as_index=False
    )
    .agg(
        quantidade_recargas=("id_operacao", "nunique"),
        meses_com_operacao=("ano_mes", "nunique"),
        energia_total_kwh=("energia_consumida_kwh", "sum"),
        receita_total_brl=("receita_gerada_brl", "sum"),
        margem_bruta_total_brl=("margem_bruta_brl", "sum"),
        recargas_origem_local=(
            "origem_local", lambda serie: (serie == "SIM").sum()
        )
    )
    .rename(columns={
        "uf_eletroposto": "uf",
        "municipio_eletroposto": "municipio"
    })
)

gold_municipios = (
    frota
    .merge(projetos_municipio, on=["uf", "municipio"], how="left")
    .merge(operacoes_municipio, on=["uf", "municipio"], how="left")
)

colunas_zerar = [
    "quantidade_projetos", "projetos_em_operacao",
    "projetos_em_construcao", "capex_total_brl",
    "opex_mensal_total_brl", "quantidade_carregadores",
    "potencia_instalada_total_kw", "demanda_mensal_estimada_recargas",
    "quantidade_recargas", "meses_com_operacao", "energia_total_kwh",
    "receita_total_brl", "margem_bruta_total_brl",
    "recargas_origem_local"
]
gold_municipios[colunas_zerar] = gold_municipios[colunas_zerar].fillna(0)

colunas_inteiras = [
    "quantidade_projetos", "projetos_em_operacao",
    "projetos_em_construcao", "quantidade_carregadores",
    "potencia_instalada_total_kw", "demanda_mensal_estimada_recargas",
    "quantidade_recargas", "meses_com_operacao", "recargas_origem_local"
]
gold_municipios[colunas_inteiras] = gold_municipios[
    colunas_inteiras
].astype(int)

gold_municipios["veiculos_por_projeto"] = np.round(
    divisao_segura(
        gold_municipios["frota_recarregavel"],
        gold_municipios["quantidade_projetos"]
    ),
    2
)
gold_municipios["veiculos_por_carregador"] = np.round(
    divisao_segura(
        gold_municipios["frota_recarregavel"],
        gold_municipios["quantidade_carregadores"]
    ),
    2
)
gold_municipios["media_mensal_recargas"] = np.round(
    divisao_segura(
        gold_municipios["quantidade_recargas"],
        gold_municipios["meses_com_operacao"]
    ),
    2
)
gold_municipios["recargas_por_100_veiculos"] = np.round(
    divisao_segura(
        gold_municipios["quantidade_recargas"] * 100,
        gold_municipios["frota_recarregavel"]
    ),
    2
)
gold_municipios["receita_por_veiculo_brl"] = np.round(
    divisao_segura(
        gold_municipios["receita_total_brl"],
        gold_municipios["frota_recarregavel"]
    ),
    2
)
gold_municipios["percentual_recargas_origem_local"] = np.round(
    divisao_segura(
        gold_municipios["recargas_origem_local"] * 100,
        gold_municipios["quantidade_recargas"]
    ),
    2
)
gold_municipios["atingimento_demanda_estimada_pct"] = np.round(
    divisao_segura(
        gold_municipios["media_mensal_recargas"] * 100,
        gold_municipios["demanda_mensal_estimada_recargas"]
    ),
    2
)

# O déficit atribui maior valor a cidades com muita frota e poucos pontos.
gold_municipios["indicador_deficit_infraestrutura"] = np.round(
    gold_municipios["frota_recarregavel"]
    / np.where(
        gold_municipios["quantidade_carregadores"] > 0,
        gold_municipios["quantidade_carregadores"],
        0.5
    ),
    2
)
gold_municipios["score_frota"] = np.round(
    score_percentil(gold_municipios["frota_recarregavel"]), 2
)
gold_municipios["score_deficit_infraestrutura"] = np.round(
    score_percentil(gold_municipios["indicador_deficit_infraestrutura"]), 2
)
gold_municipios["score_demanda_observada"] = np.round(
    score_percentil(gold_municipios["quantidade_recargas"]), 2
)
gold_municipios["indice_oportunidade_investimento"] = np.round(
    gold_municipios["score_frota"] * 0.45
    + gold_municipios["score_deficit_infraestrutura"] * 0.35
    + gold_municipios["score_demanda_observada"] * 0.20,
    2
)
gold_municipios["possui_projeto"] = np.where(
    gold_municipios["quantidade_projetos"] > 0, "SIM", "NAO"
)
gold_municipios["prioridade_expansao"] = np.select(
    [
        (gold_municipios["quantidade_projetos"] == 0)
        & (gold_municipios["frota_recarregavel"] >= 50),
        gold_municipios["veiculos_por_carregador"] >= 150,
        gold_municipios["veiculos_por_carregador"] >= 60
    ],
    ["ALTA - SEM PROJETO", "ALTA", "MEDIA"],
    default="BAIXA"
)
gold_municipios["recomendacao_investimento"] = np.select(
    [
        gold_municipios["indice_oportunidade_investimento"] >= 75,
        gold_municipios["indice_oportunidade_investimento"] >= 55,
        gold_municipios["indice_oportunidade_investimento"] >= 35
    ],
    ["PRIORIDADE ALTA", "AVALIAR EXPANSAO", "MONITORAR"],
    default="BAIXA PRIORIDADE"
)
gold_municipios = gold_municipios.round(2).sort_values(
    ["indice_oportunidade_investimento", "frota_recarregavel"],
    ascending=[False, False]
)
salvar_gold(gold_municipios, "gold_oportunidade_municipios.csv")

# -----------------------------------------------------------------------------
# 2. DESEMPENHO CONSOLIDADO DOS PROJETOS
# Responde:
# 4) Quais projetos geraram maior receita?
# 5) Quais projetos apresentaram maior margem bruta?
# 8) Quais projetos forneceram mais energia?
# -----------------------------------------------------------------------------
medidas_projeto = (
    operacoes.groupby("id_projeto", as_index=False)
    .agg(
        quantidade_recargas=("id_operacao", "nunique"),
        energia_total_kwh=("energia_consumida_kwh", "sum"),
        tempo_total_utilizacao_min=("tempo_utilizacao_min", "sum"),
        receita_total_brl=("receita_gerada_brl", "sum"),
        custo_energia_total_brl=("custo_energia_brl", "sum"),
        margem_bruta_total_brl=("margem_bruta_brl", "sum"),
        ticket_medio_brl=("receita_gerada_brl", "mean"),
        energia_media_por_recarga_kwh=("energia_consumida_kwh", "mean"),
        tempo_medio_recarga_min=("tempo_utilizacao_min", "mean"),
        meses_com_operacao=("ano_mes", "nunique"),
        recargas_origem_local=(
            "origem_local", lambda serie: (serie == "SIM").sum()
        )
    )
)

gold_projetos = projetos.merge(
    medidas_projeto, on="id_projeto", how="left"
)
colunas_medidas = [
    "quantidade_recargas", "energia_total_kwh",
    "tempo_total_utilizacao_min", "receita_total_brl",
    "custo_energia_total_brl", "margem_bruta_total_brl",
    "ticket_medio_brl", "energia_media_por_recarga_kwh",
    "tempo_medio_recarga_min", "meses_com_operacao",
    "recargas_origem_local"
]
gold_projetos[colunas_medidas] = gold_projetos[colunas_medidas].fillna(0)
gold_projetos[[
    "quantidade_recargas", "meses_com_operacao", "recargas_origem_local"
]] = gold_projetos[[
    "quantidade_recargas", "meses_com_operacao", "recargas_origem_local"
]].astype(int)

gold_projetos["margem_bruta_pct"] = np.round(
    divisao_segura(
        gold_projetos["margem_bruta_total_brl"] * 100,
        gold_projetos["receita_total_brl"]
    ),
    2
)
gold_projetos["receita_por_carregador_brl"] = np.round(
    divisao_segura(
        gold_projetos["receita_total_brl"],
        gold_projetos["qtd_carregadores"]
    ),
    2
)
gold_projetos["media_mensal_recargas"] = np.round(
    divisao_segura(
        gold_projetos["quantidade_recargas"],
        gold_projetos["meses_com_operacao"]
    ),
    2
)
gold_projetos["atingimento_demanda_estimada_pct"] = np.round(
    divisao_segura(
        gold_projetos["media_mensal_recargas"] * 100,
        gold_projetos["demanda_mensal_estimada_recargas"]
    ),
    2
)
gold_projetos["percentual_recargas_origem_local"] = np.round(
    divisao_segura(
        gold_projetos["recargas_origem_local"] * 100,
        gold_projetos["quantidade_recargas"]
    ),
    2
)
gold_projetos["opex_periodo_brl"] = (
    gold_projetos["opex_mensal"] * gold_projetos["meses_com_operacao"]
).round(2)
gold_projetos["margem_apos_opex_brl"] = (
    gold_projetos["margem_bruta_total_brl"]
    - gold_projetos["opex_periodo_brl"]
).round(2)
gold_projetos["retorno_operacional_sobre_capex_pct"] = np.round(
    divisao_segura(
        gold_projetos["margem_apos_opex_brl"] * 100,
        gold_projetos["capex"]
    ),
    2
)
gold_projetos["projeto"] = (
    "Projeto " + gold_projetos["id_projeto"].astype(str).str.zfill(2)
    + " - " + gold_projetos["municipio"]
)
gold_projetos = gold_projetos.round(2).sort_values(
    "receita_total_brl", ascending=False
)
salvar_gold(gold_projetos, "gold_desempenho_projetos.csv")

# -----------------------------------------------------------------------------
# 3. EVOLUÇÃO MENSAL DAS RECARGAS
# Responde:
# 6) Como a quantidade de recargas evoluiu ao longo do tempo?
# -----------------------------------------------------------------------------
gold_operacoes_mensais = (
    operacoes.groupby("ano_mes", as_index=False)
    .agg(
        quantidade_recargas=("id_operacao", "nunique"),
        projetos_com_movimento=("id_projeto", "nunique"),
        municipios_com_movimento=("municipio_eletroposto", "nunique"),
        energia_total_kwh=("energia_consumida_kwh", "sum"),
        receita_total_brl=("receita_gerada_brl", "sum"),
        custo_energia_total_brl=("custo_energia_brl", "sum"),
        margem_bruta_total_brl=("margem_bruta_brl", "sum"),
        ticket_medio_brl=("receita_gerada_brl", "mean")
    )
    .sort_values("ano_mes")
)
gold_operacoes_mensais["data_mes"] = pd.to_datetime(
    gold_operacoes_mensais["ano_mes"] + "-01"
)
gold_operacoes_mensais["margem_bruta_pct"] = np.round(
    divisao_segura(
        gold_operacoes_mensais["margem_bruta_total_brl"] * 100,
        gold_operacoes_mensais["receita_total_brl"]
    ),
    2
)
gold_operacoes_mensais = gold_operacoes_mensais.round(2)
salvar_gold(gold_operacoes_mensais, "gold_operacoes_mensais.csv")

# -----------------------------------------------------------------------------
# 4. DEMANDA POR HORÁRIO
# Responde:
# 7) Em quais horários ocorre a maior demanda por recargas?
# -----------------------------------------------------------------------------
gold_demanda_horaria = (
    operacoes.groupby("hora_recarga", as_index=False)
    .agg(
        quantidade_recargas=("id_operacao", "nunique"),
        energia_total_kwh=("energia_consumida_kwh", "sum"),
        receita_total_brl=("receita_gerada_brl", "sum"),
        tempo_medio_recarga_min=("tempo_utilizacao_min", "mean")
    )
    .sort_values("hora_recarga")
)
gold_demanda_horaria["faixa_horaria"] = (
    gold_demanda_horaria["hora_recarga"].astype(str).str.zfill(2) + ":00"
)
gold_demanda_horaria = gold_demanda_horaria.round(2)
salvar_gold(gold_demanda_horaria, "gold_demanda_horaria.csv")

# -----------------------------------------------------------------------------
# 5. ORIGEM MUNICIPAL DA DEMANDA
# Tabela adicional para o banco analisar de quais municípios partem os
# veículos que utilizam os eletropostos.
# -----------------------------------------------------------------------------
gold_origem_recargas = (
    operacoes.groupby(
        ["uf_origem_veiculo", "municipio_origem_veiculo"], as_index=False
    )
    .agg(
        quantidade_recargas_originadas=("id_operacao", "nunique"),
        energia_total_kwh=("energia_consumida_kwh", "sum"),
        receita_associada_brl=("receita_gerada_brl", "sum")
    )
    .rename(columns={
        "uf_origem_veiculo": "uf",
        "municipio_origem_veiculo": "municipio"
    })
)
gold_origem_recargas = gold_origem_recargas.merge(
    frota[["uf", "municipio", "frota_recarregavel"]],
    on=["uf", "municipio"],
    how="left"
)
total_recargas = max(
    int(gold_origem_recargas["quantidade_recargas_originadas"].sum()), 1
)
gold_origem_recargas["participacao_recargas_pct"] = (
    gold_origem_recargas["quantidade_recargas_originadas"]
    / total_recargas * 100
).round(2)
gold_origem_recargas["recargas_por_100_veiculos"] = np.round(
    divisao_segura(
        gold_origem_recargas["quantidade_recargas_originadas"] * 100,
        gold_origem_recargas["frota_recarregavel"]
    ),
    2
)
gold_origem_recargas = gold_origem_recargas.round(2).sort_values(
    "quantidade_recargas_originadas", ascending=False
)
salvar_gold(
    gold_origem_recargas, "gold_origem_recargas_municipios.csv"
)

# -----------------------------------------------------------------------------
# 6. DISTRIBUIÇÃO DOS COTISTAS
# Responde:
# 10) Como os cotistas estão distribuídos por município e perfil de risco?
# -----------------------------------------------------------------------------
cotistas = ler_silver(
    "dim_cotistas_silver.csv",
    [
        "id_cotista", "perfil_risco", "municipio_origem",
        "uf", "data_entrada", "valor_investido"
    ]
)
gold_cotistas = (
    cotistas.groupby(
        ["uf", "municipio_origem", "perfil_risco"], as_index=False
    )
    .agg(
        quantidade_cotistas=("id_cotista", "nunique"),
        valor_total_investido_brl=("valor_investido", "sum"),
        investimento_medio_brl=("valor_investido", "mean")
    )
)
total_cotistas = cotistas["id_cotista"].nunique()
total_investido = cotistas["valor_investido"].sum()
gold_cotistas["participacao_cotistas_pct"] = (
    gold_cotistas["quantidade_cotistas"] / total_cotistas * 100
).round(2)
gold_cotistas["participacao_investimento_pct"] = (
    gold_cotistas["valor_total_investido_brl"] / total_investido * 100
).round(2)
gold_cotistas = gold_cotistas.round(2).sort_values(
    "valor_total_investido_brl", ascending=False
)
salvar_gold(gold_cotistas, "gold_cotistas_municipio_perfil.csv")

# -----------------------------------------------------------------------------
# 7. RENTABILIDADE CONSOLIDADA DO FUNDO E COMPARAÇÃO COM A SELIC
# Responde principalmente:
# 9) Como a rentabilidade do fundo evoluiu em comparação com a Selic?
# 11) Em quais períodos o fundo superou a Selic e qual foi o retorno excedente?
#
# A rentabilidade nasce somente na Gold. Ela é calculada a partir do lucro
# mensal dos projetos, e não sorteada ou transportada das camadas anteriores.
# -----------------------------------------------------------------------------
movimentacao_fundo = ler_silver(
    "fato_movimentacao_fundo_silver.csv",
    ["id_fundo", "data_referencia", "aporte_liquido_mes"]
)
selic = ler_silver(
    "ext_selic_silver.csv",
    ["data_referencia", "taxa_selic_mes"]
)
fundo = ler_silver(
    "dim_fundo_silver.csv",
    ["id_fundo", "nome_fundo", "taxa_administracao"]
)

movimentacao_fundo["data_referencia"] = pd.to_datetime(
    movimentacao_fundo["data_referencia"], errors="coerce"
)
movimentacao_fundo["ano_mes"] = (
    movimentacao_fundo["data_referencia"].dt.to_period("M").astype(str)
)
movimentacao_mensal = (
    movimentacao_fundo.groupby(["id_fundo", "ano_mes"], as_index=False)
    .agg(aporte_liquido_mes=("aporte_liquido_mes", "sum"))
)

# A série financeira utiliza apenas meses fechados existentes na movimentação
# do fundo. Isso evita transformar um mês corrente parcial em rentabilidade.
periodo_inicial = movimentacao_fundo["data_referencia"].min().to_period("M")
periodo_final = movimentacao_fundo["data_referencia"].max().to_period("M")
periodos_fundo = pd.period_range(periodo_inicial, periodo_final, freq="M")
calendario_fundo = pd.DataFrame({
    "periodo": periodos_fundo,
    "ano_mes": periodos_fundo.astype(str),
    "data_referencia": periodos_fundo.to_timestamp(how="end").normalize()
})

# Consolida receita, custo de energia e margem por projeto e mês.
operacoes_projeto_mes = (
    operacoes[operacoes["ano_mes"].isin(calendario_fundo["ano_mes"])]
    .groupby(["ano_mes", "id_projeto"], as_index=False)
    .agg(
        quantidade_recargas=("id_operacao", "nunique"),
        receita_projeto_brl=("receita_gerada_brl", "sum"),
        custo_energia_projeto_brl=("custo_energia_brl", "sum"),
        margem_bruta_projeto_brl=("margem_bruta_brl", "sum")
    )
)

# Cada projeto em operação incorre em OPEX a partir do mês de início, mesmo
# quando não registra recargas. Assim, o lucro não é superestimado.
projetos_rentabilidade = projetos.copy()
projetos_rentabilidade["data_inicio_operacao"] = pd.to_datetime(
    projetos_rentabilidade["data_inicio_operacao"], errors="coerce"
)
projetos_rentabilidade = projetos_rentabilidade[
    projetos_rentabilidade["status"].str.upper().eq("EM OPERAÇÃO")
    & projetos_rentabilidade["data_inicio_operacao"].notna()
].copy()

linhas_projetos_mensais = []
for periodo in periodos_fundo:
    fim_mes = periodo.to_timestamp(how="end").normalize()
    projetos_ativos_mes = projetos_rentabilidade[
        projetos_rentabilidade["data_inicio_operacao"] <= fim_mes
    ][[
        "id_projeto", "municipio", "capex", "opex_mensal"
    ]].copy()

    if projetos_ativos_mes.empty:
        continue

    projetos_ativos_mes["ano_mes"] = str(periodo)
    projetos_ativos_mes = projetos_ativos_mes.merge(
        operacoes_projeto_mes,
        on=["ano_mes", "id_projeto"],
        how="left"
    )
    colunas_operacionais = [
        "quantidade_recargas", "receita_projeto_brl",
        "custo_energia_projeto_brl", "margem_bruta_projeto_brl"
    ]
    projetos_ativos_mes[colunas_operacionais] = (
        projetos_ativos_mes[colunas_operacionais].fillna(0)
    )
    projetos_ativos_mes["quantidade_recargas"] = (
        projetos_ativos_mes["quantidade_recargas"].astype(int)
    )
    projetos_ativos_mes["lucro_operacional_projeto_brl"] = (
        projetos_ativos_mes["margem_bruta_projeto_brl"]
        - projetos_ativos_mes["opex_mensal"]
    ).round(2)
    projetos_ativos_mes["retorno_operacional_mensal_sobre_capex_pct"] = (
        divisao_segura(
            projetos_ativos_mes["lucro_operacional_projeto_brl"] * 100,
            projetos_ativos_mes["capex"]
        )
    ).round(4)
    linhas_projetos_mensais.append(projetos_ativos_mes)

if linhas_projetos_mensais:
    gold_lucro_projetos_mensal = pd.concat(
        linhas_projetos_mensais, ignore_index=True
    )
else:
    gold_lucro_projetos_mensal = pd.DataFrame(columns=[
        "id_projeto", "municipio", "capex", "opex_mensal", "ano_mes",
        "quantidade_recargas", "receita_projeto_brl",
        "custo_energia_projeto_brl", "margem_bruta_projeto_brl",
        "lucro_operacional_projeto_brl",
        "retorno_operacional_mensal_sobre_capex_pct"
    ])

salvar_gold(
    gold_lucro_projetos_mensal.round(2),
    "gold_lucro_projetos_mensal.csv"
)

resultado_projetos_mensal = (
    gold_lucro_projetos_mensal.groupby("ano_mes", as_index=False)
    .agg(
        projetos_em_operacao=("id_projeto", "nunique"),
        projetos_com_recarga=(
            "quantidade_recargas", lambda serie: int((serie > 0).sum())
        ),
        quantidade_recargas=("quantidade_recargas", "sum"),
        receita_total_projetos_brl=("receita_projeto_brl", "sum"),
        custo_energia_total_projetos_brl=(
            "custo_energia_projeto_brl", "sum"
        ),
        margem_bruta_total_projetos_brl=(
            "margem_bruta_projeto_brl", "sum"
        ),
        opex_total_projetos_brl=("opex_mensal", "sum"),
        lucro_operacional_projetos_brl=(
            "lucro_operacional_projeto_brl", "sum"
        )
    )
)

base_rentabilidade = (
    calendario_fundo
    .merge(resultado_projetos_mensal, on="ano_mes", how="left")
    .merge(movimentacao_mensal, on="ano_mes", how="left")
)
colunas_financeiras_zerar = [
    "projetos_em_operacao", "projetos_com_recarga", "quantidade_recargas",
    "receita_total_projetos_brl", "custo_energia_total_projetos_brl",
    "margem_bruta_total_projetos_brl", "opex_total_projetos_brl",
    "lucro_operacional_projetos_brl", "aporte_liquido_mes"
]
base_rentabilidade[colunas_financeiras_zerar] = (
    base_rentabilidade[colunas_financeiras_zerar].fillna(0)
)
base_rentabilidade[[
    "projetos_em_operacao", "projetos_com_recarga", "quantidade_recargas"
]] = base_rentabilidade[[
    "projetos_em_operacao", "projetos_com_recarga", "quantidade_recargas"
]].astype(int)

# A taxa administrativa cadastrada é anual. A taxa mensal equivalente é
# descontada do lucro operacional dos projetos antes da rentabilidade.
taxa_administracao_anual = float(fundo.iloc[0]["taxa_administracao"])
taxa_administracao_mensal = (
    (1 + taxa_administracao_anual) ** (1 / 12) - 1
)

PATRIMONIO_INICIAL_FUNDO_BRL = 15_000_000.0
VALOR_COTA_INICIAL = 100.0
patrimonio_atual = PATRIMONIO_INICIAL_FUNDO_BRL
valor_cota_atual = VALOR_COTA_INICIAL
linhas_rentabilidade = []

for linha in base_rentabilidade.sort_values("data_referencia").itertuples():
    capital_base = patrimonio_atual
    taxa_administracao_brl = capital_base * taxa_administracao_mensal
    lucro_liquido_fundo = (
        linha.lucro_operacional_projetos_brl - taxa_administracao_brl
    )
    rentabilidade_mes = (
        lucro_liquido_fundo / capital_base if capital_base > 0 else 0
    )

    valor_cota_atual *= 1 + rentabilidade_mes
    patrimonio_atual = (
        capital_base + lucro_liquido_fundo + linha.aporte_liquido_mes
    )

    linhas_rentabilidade.append({
        "id_fundo": int(fundo.iloc[0]["id_fundo"]),
        "nome_fundo": fundo.iloc[0]["nome_fundo"],
        "data_referencia": linha.data_referencia,
        "ano_mes": linha.ano_mes,
        "projetos_em_operacao": linha.projetos_em_operacao,
        "projetos_com_recarga": linha.projetos_com_recarga,
        "quantidade_recargas": linha.quantidade_recargas,
        "receita_total_projetos_brl": linha.receita_total_projetos_brl,
        "custo_energia_total_projetos_brl": (
            linha.custo_energia_total_projetos_brl
        ),
        "margem_bruta_total_projetos_brl": (
            linha.margem_bruta_total_projetos_brl
        ),
        "opex_total_projetos_brl": linha.opex_total_projetos_brl,
        "lucro_operacional_projetos_brl": (
            linha.lucro_operacional_projetos_brl
        ),
        "taxa_administracao_fundo_brl": taxa_administracao_brl,
        "lucro_liquido_fundo_brl": lucro_liquido_fundo,
        "capital_base_calculo_brl": capital_base,
        "aporte_liquido_mes": linha.aporte_liquido_mes,
        "rentabilidade_mes": rentabilidade_mes,
        "rentabilidade_fundo_pct": rentabilidade_mes * 100,
        "valor_cota": valor_cota_atual,
        "patrimonio_liquido": patrimonio_atual
    })

gold_rentabilidade_fundo = pd.DataFrame(linhas_rentabilidade).round({
    "receita_total_projetos_brl": 2,
    "custo_energia_total_projetos_brl": 2,
    "margem_bruta_total_projetos_brl": 2,
    "opex_total_projetos_brl": 2,
    "lucro_operacional_projetos_brl": 2,
    "taxa_administracao_fundo_brl": 2,
    "lucro_liquido_fundo_brl": 2,
    "capital_base_calculo_brl": 2,
    "aporte_liquido_mes": 2,
    "rentabilidade_mes": 8,
    "rentabilidade_fundo_pct": 4,
    "valor_cota": 4,
    "patrimonio_liquido": 2
})
salvar_gold(gold_rentabilidade_fundo, "gold_rentabilidade_fundo.csv")

selic["data_referencia"] = pd.to_datetime(
    selic["data_referencia"], errors="coerce"
)
selic["ano_mes"] = selic["data_referencia"].dt.to_period("M").astype(str)

# A série 4390 do BCB representa a Selic acumulada no mês em percentual.
selic_mensal = (
    selic.groupby("ano_mes", as_index=False)
    .agg(taxa_selic_mes_pct=("taxa_selic_mes", "last"))
)

gold_fundo_selic = (
    gold_rentabilidade_fundo.merge(selic_mensal, on="ano_mes", how="inner")
    .sort_values("data_referencia")
    .reset_index(drop=True)
)
gold_fundo_selic["retorno_excedente_pp"] = (
    gold_fundo_selic["rentabilidade_fundo_pct"]
    - gold_fundo_selic["taxa_selic_mes_pct"]
).round(4)
gold_fundo_selic["fundo_superou_selic"] = np.where(
    gold_fundo_selic["retorno_excedente_pp"] > 0, "SIM", "NAO"
)
gold_fundo_selic["retorno_fundo_brl"] = (
    gold_fundo_selic["lucro_liquido_fundo_brl"]
).round(2)
gold_fundo_selic["retorno_selic_brl"] = (
    gold_fundo_selic["capital_base_calculo_brl"]
    * gold_fundo_selic["taxa_selic_mes_pct"] / 100
).round(2)
gold_fundo_selic["retorno_excedente_brl"] = (
    gold_fundo_selic["retorno_fundo_brl"]
    - gold_fundo_selic["retorno_selic_brl"]
).round(2)

# Retornos acumulados calculados por capitalização composta.
gold_fundo_selic["rentabilidade_fundo_acumulada_pct"] = (
    (1 + gold_fundo_selic["rentabilidade_mes"]).cumprod() - 1
) * 100
gold_fundo_selic["selic_acumulada_pct"] = (
    (1 + gold_fundo_selic["taxa_selic_mes_pct"] / 100).cumprod() - 1
) * 100
gold_fundo_selic["retorno_excedente_acumulado_pp"] = (
    gold_fundo_selic["rentabilidade_fundo_acumulada_pct"]
    - gold_fundo_selic["selic_acumulada_pct"]
)
gold_fundo_selic["retorno_excedente_acumulado_brl"] = (
    gold_fundo_selic["retorno_excedente_brl"].cumsum()
)
gold_fundo_selic["meses_acima_selic_acumulado"] = (
    gold_fundo_selic["fundo_superou_selic"].eq("SIM").cumsum()
)
gold_fundo_selic["percentual_meses_acima_selic_acumulado"] = (
    gold_fundo_selic["meses_acima_selic_acumulado"]
    / (gold_fundo_selic.index + 1) * 100
)
gold_fundo_selic = gold_fundo_selic.round({
    "rentabilidade_fundo_acumulada_pct": 4,
    "selic_acumulada_pct": 4,
    "retorno_excedente_acumulado_pp": 4,
    "retorno_excedente_acumulado_brl": 2,
    "percentual_meses_acima_selic_acumulado": 2,
    "capital_base_calculo_brl": 2
})

colunas_fundo_selic = [
    "id_fundo", "nome_fundo", "data_referencia", "ano_mes",
    "projetos_em_operacao", "projetos_com_recarga", "quantidade_recargas",
    "receita_total_projetos_brl", "custo_energia_total_projetos_brl",
    "margem_bruta_total_projetos_brl", "opex_total_projetos_brl",
    "lucro_operacional_projetos_brl", "taxa_administracao_fundo_brl",
    "lucro_liquido_fundo_brl", "valor_cota", "patrimonio_liquido",
    "aporte_liquido_mes", "rentabilidade_fundo_pct",
    "taxa_selic_mes_pct", "retorno_excedente_pp", "fundo_superou_selic",
    "capital_base_calculo_brl", "retorno_fundo_brl",
    "retorno_selic_brl", "retorno_excedente_brl",
    "rentabilidade_fundo_acumulada_pct", "selic_acumulada_pct",
    "retorno_excedente_acumulado_pp",
    "retorno_excedente_acumulado_brl",
    "meses_acima_selic_acumulado",
    "percentual_meses_acima_selic_acumulado"
]
gold_fundo_selic = gold_fundo_selic[colunas_fundo_selic]
salvar_gold(gold_fundo_selic, "gold_desempenho_fundo_selic.csv")

if not gold_fundo_selic.empty:
    ultimo = gold_fundo_selic.iloc[-1]
    resumo_fundo_selic = pd.DataFrame([{
        "id_fundo": ultimo["id_fundo"],
        "nome_fundo": ultimo["nome_fundo"],
        "periodo_inicial": gold_fundo_selic["data_referencia"].min(),
        "periodo_final": gold_fundo_selic["data_referencia"].max(),
        "quantidade_meses_analisados": len(gold_fundo_selic),
        "meses_acima_selic": int(
            gold_fundo_selic["fundo_superou_selic"].eq("SIM").sum()
        ),
        "percentual_meses_acima_selic": round(
            gold_fundo_selic["fundo_superou_selic"].eq("SIM").mean() * 100,
            2
        ),
        "rentabilidade_fundo_acumulada_pct": ultimo[
            "rentabilidade_fundo_acumulada_pct"
        ],
        "selic_acumulada_pct": ultimo["selic_acumulada_pct"],
        "retorno_excedente_acumulado_pp": ultimo[
            "retorno_excedente_acumulado_pp"
        ],
        "retorno_excedente_total_brl": round(
            gold_fundo_selic["retorno_excedente_brl"].sum(), 2
        )
    }])
    salvar_gold(resumo_fundo_selic, "gold_resumo_fundo_selic.csv")

# -----------------------------------------------------------------------------
# 8. RESUMO EXECUTIVO GERAL
# Indicadores prontos para cartões da visão do banco.
# -----------------------------------------------------------------------------
municipios_com_demanda = gold_municipios[
    gold_municipios["frota_recarregavel"] > 0
].copy()
correlacao_frota_recargas = municipios_com_demanda[
    ["frota_recarregavel", "quantidade_recargas"]
].corr().iloc[0, 1]
maior_oportunidade = gold_municipios.iloc[0]

resumo_geral = pd.DataFrame([{
    "quantidade_cotistas": int(total_cotistas),
    "valor_total_investido_cotistas_brl": round(total_investido, 2),
    "quantidade_projetos": int(projetos["id_projeto"].nunique()),
    "projetos_em_operacao": int(
        projetos["status"].str.upper().eq("EM OPERAÇÃO").sum()
    ),
    "capex_total_brl": round(projetos["capex"].sum(), 2),
    "quantidade_recargas": int(operacoes["id_operacao"].nunique()),
    "energia_total_fornecida_kwh": round(
        operacoes["energia_consumida_kwh"].sum(), 2
    ),
    "receita_total_recargas_brl": round(
        operacoes["receita_gerada_brl"].sum(), 2
    ),
    "margem_bruta_total_brl": round(
        operacoes["margem_bruta_brl"].sum(), 2
    ),
    "frota_recarregavel_es": int(frota["frota_recarregavel"].sum()),
    "correlacao_frota_recargas_municipio": round(
        correlacao_frota_recargas, 4
    ),
    "municipio_maior_oportunidade": maior_oportunidade["municipio"],
    "indice_maior_oportunidade": maior_oportunidade[
        "indice_oportunidade_investimento"
    ],
    "recomendacao_maior_oportunidade": maior_oportunidade[
        "recomendacao_investimento"
    ]
}])
salvar_gold(resumo_geral, "gold_resumo_executivo.csv")

print("Camada Gold gerada com sucesso.")
