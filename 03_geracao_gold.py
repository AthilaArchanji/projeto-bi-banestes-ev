from pathlib import Path

import numpy as np
import pandas as pd

# A camada Gold contém tabelas prontas para análise e dashboard.
# Ela lê somente dados tratados da Silver e gera indicadores de negócio.
BASE_DIR = Path(__file__).resolve().parent
SILVER_DIR = BASE_DIR / "camada_silver"
GOLD_DIR = BASE_DIR / "camada_gold"
GOLD_DIR.mkdir(exist_ok=True)


def ler_silver(nome_arquivo, colunas_obrigatorias=None):
    """Lê uma tabela Silver e valida se as colunas necessárias existem."""
    caminho = SILVER_DIR / nome_arquivo
    if not caminho.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {caminho}. "
            "Execute primeiro 01_ingestao_bronze.py e 02_tratamento_silver.py."
        )

    df = pd.read_csv(caminho)
    colunas_obrigatorias = colunas_obrigatorias or []
    faltantes = [coluna for coluna in colunas_obrigatorias if coluna not in df.columns]
    if faltantes:
        raise ValueError(
            f"O arquivo {nome_arquivo} não possui as colunas: {faltantes}"
        )
    return df


def salvar_gold(df, nome_arquivo):
    """Salva a tabela Gold e exibe a quantidade de registros gerados."""
    caminho = GOLD_DIR / nome_arquivo
    df.to_csv(caminho, index=False)
    print(f"- {nome_arquivo}: {len(df)} registros")


def divisao_segura(numerador, denominador):
    """Evita divisão por zero nos indicadores."""
    return np.where(denominador > 0, numerador / denominador, np.nan)


print("Iniciando a geração da Camada Gold...")

# -----------------------------------------------------------------------------
# 1. OPORTUNIDADE POR MUNICÍPIO
# Responde:
# 1) Quais municípios possuem maior frota recarregável?
# 2) Quais municípios possuem mais projetos?
# 3) Quais municípios possuem maior número de veículos por projeto?
# -----------------------------------------------------------------------------
frota = ler_silver(
    "ext_senatran_es_silver.csv",
    [
        "uf", "municipio", "frota_eletrica",
        "frota_hibrida_plugin", "frota_recarregavel"
    ]
)
projetos = ler_silver(
    "dim_projetos_silver.csv",
    [
        "id_projeto", "municipio", "uf", "capex", "opex_mensal",
        "qtd_carregadores", "potencia_instalada_kw", "status"
    ]
)

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
        potencia_instalada_total_kw=("potencia_instalada_kw", "sum")
    )
)

gold_municipios = frota.merge(
    projetos_municipio,
    on=["uf", "municipio"],
    how="left"
)

colunas_zerar = [
    "quantidade_projetos", "projetos_em_operacao", "projetos_em_construcao",
    "capex_total_brl", "opex_mensal_total_brl", "quantidade_carregadores",
    "potencia_instalada_total_kw"
]
gold_municipios[colunas_zerar] = gold_municipios[colunas_zerar].fillna(0)

colunas_inteiras = [
    "quantidade_projetos", "projetos_em_operacao", "projetos_em_construcao",
    "quantidade_carregadores", "potencia_instalada_total_kw"
]
gold_municipios[colunas_inteiras] = gold_municipios[colunas_inteiras].astype(int)

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
gold_municipios["possui_projeto"] = np.where(
    gold_municipios["quantidade_projetos"] > 0, "SIM", "NAO"
)
gold_municipios["prioridade_expansao"] = np.select(
    [
        (gold_municipios["quantidade_projetos"] == 0)
        & (gold_municipios["frota_recarregavel"] >= 50),
        gold_municipios["veiculos_por_projeto"] >= 300,
        gold_municipios["veiculos_por_projeto"] >= 100
    ],
    ["ALTA - SEM PROJETO", "ALTA", "MEDIA"],
    default="BAIXA"
)
gold_municipios = gold_municipios.sort_values(
    ["frota_recarregavel", "quantidade_projetos"],
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
operacoes = ler_silver(
    "fato_operacoes_recarga_silver.csv",
    [
        "id_operacao", "id_projeto", "data_hora", "energia_consumida_kwh",
        "tempo_utilizacao_min", "receita_gerada_brl", "custo_energia_brl",
        "margem_bruta_brl", "ano_mes", "hora_recarga"
    ]
)

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
        meses_com_operacao=("ano_mes", "nunique")
    )
)

gold_projetos = projetos.merge(medidas_projeto, on="id_projeto", how="left")
colunas_medidas = [
    "quantidade_recargas", "energia_total_kwh", "tempo_total_utilizacao_min",
    "receita_total_brl", "custo_energia_total_brl",
    "margem_bruta_total_brl", "ticket_medio_brl",
    "energia_media_por_recarga_kwh", "tempo_medio_recarga_min",
    "meses_com_operacao"
]
gold_projetos[colunas_medidas] = gold_projetos[colunas_medidas].fillna(0)
gold_projetos[["quantidade_recargas", "meses_com_operacao"]] = gold_projetos[
    ["quantidade_recargas", "meses_com_operacao"]
].astype(int)
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
gold_projetos["opex_periodo_brl"] = (
    gold_projetos["opex_mensal"] * gold_projetos["meses_com_operacao"]
).round(2)
gold_projetos["margem_apos_opex_brl"] = (
    gold_projetos["margem_bruta_total_brl"]
    - gold_projetos["opex_periodo_brl"]
).round(2)
gold_projetos["projeto"] = (
    "Projeto " + gold_projetos["id_projeto"].astype(str).str.zfill(2)
    + " - " + gold_projetos["municipio"]
)

gold_projetos = gold_projetos.round({
    "energia_total_kwh": 2,
    "tempo_total_utilizacao_min": 2,
    "receita_total_brl": 2,
    "custo_energia_total_brl": 2,
    "margem_bruta_total_brl": 2,
    "ticket_medio_brl": 2,
    "energia_media_por_recarga_kwh": 2,
    "tempo_medio_recarga_min": 2
}).sort_values("receita_total_brl", ascending=False)
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
# 5. DISTRIBUIÇÃO DOS COTISTAS
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
        ["uf", "municipio_origem", "perfil_risco"],
        as_index=False
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
# 6. DESEMPENHO DO FUNDO EM COMPARAÇÃO COM A SELIC
# Responde principalmente:
# 9) Como a rentabilidade do fundo evoluiu em comparação com a Selic?
# 11) Em quais períodos o fundo superou a Selic e qual foi o retorno excedente?
# -----------------------------------------------------------------------------
# O aporte_liquido_mes é obrigatório: a Gold não estima nem cria esse valor.
# Ele deve ter sido gerado na Bronze e validado na Silver.
rentabilidade = ler_silver(
    "fato_rentabilidade_silver.csv",
    [
        "id_fundo", "data_referencia", "valor_cota", "patrimonio_liquido",
        "aporte_liquido_mes", "rentabilidade_mes", "rentabilidade_pct"
    ]
)
selic = ler_silver(
    "ext_selic_silver.csv",
    ["data_referencia", "taxa_selic_mes"]
)
fundo = ler_silver(
    "dim_fundo_silver.csv",
    ["id_fundo", "nome_fundo"]
)

rentabilidade["data_referencia"] = pd.to_datetime(
    rentabilidade["data_referencia"], errors="coerce"
)
selic["data_referencia"] = pd.to_datetime(
    selic["data_referencia"], errors="coerce"
)
rentabilidade["ano_mes"] = rentabilidade["data_referencia"].dt.to_period("M").astype(str)
selic["ano_mes"] = selic["data_referencia"].dt.to_period("M").astype(str)

# A série 4390 do BCB já representa a Selic acumulada no mês em percentual.
selic_mensal = (
    selic.groupby("ano_mes", as_index=False)
    .agg(taxa_selic_mes_pct=("taxa_selic_mes", "last"))
)

gold_fundo_selic = (
    rentabilidade.merge(selic_mensal, on="ano_mes", how="inner")
    .merge(fundo[["id_fundo", "nome_fundo"]], on="id_fundo", how="left")
    .sort_values("data_referencia")
    .reset_index(drop=True)
)

gold_fundo_selic["rentabilidade_fundo_pct"] = (
    gold_fundo_selic["rentabilidade_mes"] * 100
).round(4)
gold_fundo_selic["retorno_excedente_pp"] = (
    gold_fundo_selic["rentabilidade_fundo_pct"]
    - gold_fundo_selic["taxa_selic_mes_pct"]
).round(4)
gold_fundo_selic["fundo_superou_selic"] = np.where(
    gold_fundo_selic["retorno_excedente_pp"] > 0, "SIM", "NAO"
)

# Como a Bronze armazena o aporte líquido do mês, recuperamos o capital
# aplicado antes da rentabilidade: PL final = capital-base * (1+r) + aporte.
gold_fundo_selic["capital_base_calculo_brl"] = (
    (gold_fundo_selic["patrimonio_liquido"]
     - gold_fundo_selic["aporte_liquido_mes"])
    / (1 + gold_fundo_selic["rentabilidade_mes"])
).round(2)

gold_fundo_selic["retorno_fundo_brl"] = (
    gold_fundo_selic["capital_base_calculo_brl"]
    * gold_fundo_selic["rentabilidade_mes"]
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
    "id_fundo", "nome_fundo", "data_referencia", "ano_mes", "valor_cota",
    "patrimonio_liquido", "aporte_liquido_mes", "rentabilidade_fundo_pct",
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

# Uma linha de resumo facilita os cartões executivos do dashboard do banco.
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
# 7. RESUMO EXECUTIVO GERAL
# Indicadores prontos para cartões do dashboard do banco.
# -----------------------------------------------------------------------------
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
    "frota_recarregavel_es": int(frota["frota_recarregavel"].sum())
}])
salvar_gold(resumo_geral, "gold_resumo_executivo.csv")

print("Camada Gold gerada com sucesso.")
