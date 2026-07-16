from pathlib import Path
import re
import unicodedata

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
BRONZE_DIR = BASE_DIR / "camada_bronze"
SILVER_DIR = BASE_DIR / "camada_silver"
SILVER_DIR.mkdir(exist_ok=True)

UF_ES = "ESPIRITO SANTO"
COMBUSTIVEIS_RECARREGAVEIS = {
    "ELETRICO",
    "ELETRICO/FONTE EXTERNA",
    "HIBRIDO PLUG-IN"
}
controle_qualidade = []


def normalizar_texto(valor):
    """Remove acentos, espaços duplicados e padroniza em maiúsculas."""
    if pd.isna(valor):
        return pd.NA
    texto = str(valor).strip().upper()
    texto = "".join(
        caractere for caractere in unicodedata.normalize("NFD", texto)
        if unicodedata.category(caractere) != "Mn"
    )
    return re.sub(r"\s+", " ", texto)


def normalizar_uf(valor):
    """Converte ES ou variações do nome para ESPIRITO SANTO."""
    texto = normalizar_texto(valor)
    if texto in {"ES", "ESPIRITO SANTO"}:
        return UF_ES
    return texto


def registrar_qualidade(tabela, entrada, saida, observacao):
    controle_qualidade.append({
        "tabela": tabela,
        "registros_bronze": entrada,
        "registros_silver": saida,
        "registros_removidos": entrada - saida,
        "observacao": observacao
    })


def validar_colunas(df, tabela, colunas):
    faltantes = [coluna for coluna in colunas if coluna not in df.columns]
    if faltantes:
        raise ValueError(f"{tabela} não possui as colunas: {faltantes}")


print("Iniciando o tratamento da Camada Silver...")

# 1. SENATRAN
# A fonte externa é tratada primeiro para que seus municípios possam validar
# as tabelas internas de projetos, cotistas e operações.
arquivo_senatran = BRONZE_DIR / "frota_senatran_bruta.xlsx"
if not arquivo_senatran.exists():
    raise FileNotFoundError(
        "Arquivo bruto da SENATRAN não encontrado na Camada Bronze."
    )

df_senatran = pd.read_excel(arquivo_senatran)
entrada = len(df_senatran)
df_senatran.columns = [
    normalizar_texto(coluna).lower() for coluna in df_senatran.columns
]
df_senatran = df_senatran.rename(columns={
    "combustivel veiculo": "combustivel",
    "qtd. veiculos": "quantidade_veiculos"
})
validar_colunas(
    df_senatran,
    "frota_senatran_bruta.xlsx",
    ["uf", "municipio", "combustivel", "quantidade_veiculos"]
)

df_senatran["uf"] = df_senatran["uf"].map(normalizar_uf)
df_senatran["municipio"] = df_senatran["municipio"].map(normalizar_texto)
df_senatran["combustivel"] = df_senatran["combustivel"].map(normalizar_texto)
df_senatran["quantidade_veiculos"] = pd.to_numeric(
    df_senatran["quantidade_veiculos"], errors="coerce"
).fillna(0)

df_es = df_senatran[df_senatran["uf"] == UF_ES].copy()
municipios_es = df_es[["uf", "municipio"]].drop_duplicates()
municipios_validos = set(municipios_es["municipio"])

df_recarregaveis = df_es[
    df_es["combustivel"].isin(COMBUSTIVEIS_RECARREGAVEIS)
].copy()

frota_eletrica = (
    df_recarregaveis[
        df_recarregaveis["combustivel"].isin(
            {"ELETRICO", "ELETRICO/FONTE EXTERNA"}
        )
    ]
    .groupby("municipio", as_index=False)["quantidade_veiculos"]
    .sum()
    .rename(columns={"quantidade_veiculos": "frota_eletrica"})
)
frota_hibrida_plugin = (
    df_recarregaveis[
        df_recarregaveis["combustivel"] == "HIBRIDO PLUG-IN"
    ]
    .groupby("municipio", as_index=False)["quantidade_veiculos"]
    .sum()
    .rename(columns={"quantidade_veiculos": "frota_hibrida_plugin"})
)

df_frota_es = (
    municipios_es
    .merge(frota_eletrica, on="municipio", how="left")
    .merge(frota_hibrida_plugin, on="municipio", how="left")
)
df_frota_es[["frota_eletrica", "frota_hibrida_plugin"]] = (
    df_frota_es[["frota_eletrica", "frota_hibrida_plugin"]]
    .fillna(0)
    .astype(int)
)
df_frota_es["frota_recarregavel"] = (
    df_frota_es["frota_eletrica"] + df_frota_es["frota_hibrida_plugin"]
)
total_frota_es = max(int(df_frota_es["frota_recarregavel"].sum()), 1)
maior_frota = max(int(df_frota_es["frota_recarregavel"].max()), 1)
df_frota_es["participacao_frota_es_pct"] = (
    df_frota_es["frota_recarregavel"] / total_frota_es * 100
).round(4)
df_frota_es["indice_demanda_senatran"] = (
    np.sqrt(df_frota_es["frota_recarregavel"] / maior_frota) * 100
).round(2)
df_frota_es["classe_demanda_senatran"] = np.select(
    [
        df_frota_es["indice_demanda_senatran"] >= 70,
        df_frota_es["indice_demanda_senatran"] >= 40,
        df_frota_es["indice_demanda_senatran"] >= 15,
        df_frota_es["frota_recarregavel"] > 0
    ],
    ["MUITO ALTA", "ALTA", "MEDIA", "BAIXA"],
    default="SEM FROTA RECARREGAVEL"
)
df_frota_es = df_frota_es.sort_values(
    "frota_recarregavel", ascending=False
)
df_frota_es.to_csv(
    SILVER_DIR / "ext_senatran_es_silver.csv", index=False
)
registrar_qualidade(
    "ext_senatran_es",
    entrada,
    len(df_frota_es),
    "UF corrigida; somente elétricos, elétricos com fonte externa e híbridos plug-in; índice de demanda criado"
)
print("- ext_senatran_es tratada.")

# 2. Fundo
arquivo = BRONZE_DIR / "dim_fundo.csv"
df_fundo = pd.read_csv(arquivo)
entrada = len(df_fundo)
df_fundo = df_fundo.drop_duplicates(subset=["id_fundo"]).copy()
df_fundo["data_inicio"] = pd.to_datetime(
    df_fundo["data_inicio"], errors="coerce"
)
df_fundo["taxa_administracao"] = pd.to_numeric(
    df_fundo["taxa_administracao"], errors="coerce"
)
df_fundo = df_fundo.dropna(
    subset=["id_fundo", "nome_fundo", "data_inicio"]
)
df_fundo.to_csv(SILVER_DIR / "dim_fundo_silver.csv", index=False)
registrar_qualidade(
    "dim_fundo", entrada, len(df_fundo), "Tipos e chave do fundo validados"
)
print("- dim_fundo tratada.")

# 3. Projetos
arquivo = BRONZE_DIR / "dim_projetos.csv"
df_projetos = pd.read_csv(arquivo)
entrada = len(df_projetos)
validar_colunas(
    df_projetos,
    "dim_projetos.csv",
    [
        "id_projeto", "municipio", "uf", "tipo_local", "capex",
        "opex_mensal", "qtd_carregadores", "potencia_instalada_kw",
        "status", "data_inicio_operacao",
        "frota_eletrica_municipio_ref",
        "frota_hibrida_plugin_municipio_ref",
        "frota_recarregavel_municipio_ref",
        "participacao_frota_es_pct", "indice_demanda_senatran",
        "classe_demanda_senatran", "demanda_mensal_estimada_recargas"
    ]
)
df_projetos = df_projetos.drop_duplicates(subset=["id_projeto"]).copy()
df_projetos["municipio"] = df_projetos["municipio"].map(normalizar_texto)
df_projetos["uf"] = df_projetos["uf"].map(normalizar_uf)
df_projetos["status"] = df_projetos["status"].str.strip().str.title()
df_projetos["classe_demanda_senatran"] = df_projetos[
    "classe_demanda_senatran"
].map(normalizar_texto)
df_projetos["data_inicio_operacao"] = pd.to_datetime(
    df_projetos["data_inicio_operacao"], errors="coerce"
)

colunas_numericas_projetos = [
    "capex", "opex_mensal", "qtd_carregadores",
    "potencia_instalada_kw", "frota_eletrica_municipio_ref",
    "frota_hibrida_plugin_municipio_ref",
    "frota_recarregavel_municipio_ref", "participacao_frota_es_pct",
    "indice_demanda_senatran", "demanda_mensal_estimada_recargas"
]
for coluna in colunas_numericas_projetos:
    df_projetos[coluna] = pd.to_numeric(
        df_projetos[coluna], errors="coerce"
    )

df_projetos = df_projetos[
    (df_projetos["uf"] == UF_ES)
    & df_projetos["municipio"].isin(municipios_validos)
    & (df_projetos["capex"] > 0)
    & (df_projetos["opex_mensal"] > 0)
    & (df_projetos["qtd_carregadores"] > 0)
    & (df_projetos["frota_recarregavel_municipio_ref"] >= 0)
].copy()

# Confere se a referência armazenada na simulação continua igual à fonte real.
referencia_atual = df_frota_es[[
    "municipio", "frota_recarregavel"
]].rename(columns={
    "frota_recarregavel": "frota_recarregavel_senatran_atual"
})
df_projetos = df_projetos.merge(
    referencia_atual, on="municipio", how="left"
)
df_projetos["diferenca_frota_referencia"] = (
    df_projetos["frota_recarregavel_municipio_ref"]
    - df_projetos["frota_recarregavel_senatran_atual"]
).fillna(0).astype(int)

df_projetos.to_csv(
    SILVER_DIR / "dim_projetos_silver.csv", index=False
)
registrar_qualidade(
    "dim_projetos",
    entrada,
    len(df_projetos),
    "Municípios validados pela SENATRAN; investimento, infraestrutura e premissas de demanda padronizados"
)
print("- dim_projetos tratada.")

# 4. Cotistas
arquivo = BRONZE_DIR / "dim_cotistas.csv"
df_cotistas = pd.read_csv(arquivo)
entrada = len(df_cotistas)
df_cotistas = df_cotistas.drop_duplicates(subset=["id_cotista"]).copy()
df_cotistas["municipio_origem"] = df_cotistas[
    "municipio_origem"
].map(normalizar_texto)
df_cotistas["uf"] = df_cotistas["uf"].map(normalizar_uf)
df_cotistas["data_entrada"] = pd.to_datetime(
    df_cotistas["data_entrada"], errors="coerce"
)
df_cotistas["valor_investido"] = pd.to_numeric(
    df_cotistas["valor_investido"], errors="coerce"
)
df_cotistas = df_cotistas[
    (df_cotistas["uf"] == UF_ES)
    & df_cotistas["municipio_origem"].isin(municipios_validos)
    & df_cotistas["data_entrada"].notna()
    & (df_cotistas["valor_investido"] > 0)
].copy()
df_cotistas.to_csv(
    SILVER_DIR / "dim_cotistas_silver.csv", index=False
)
registrar_qualidade(
    "dim_cotistas",
    entrada,
    len(df_cotistas),
    "Municípios de origem validados pela SENATRAN; UF, datas e valores padronizados"
)
print("- dim_cotistas tratada.")

# 5. Movimentações do fundo
# A Silver trata somente os aportes. Rentabilidade, cota e patrimônio não são
# dados de origem: serão calculados na Gold com base no lucro dos projetos.
arquivo = BRONZE_DIR / "fato_movimentacao_fundo.csv"
df_movimentacao_fundo = pd.read_csv(arquivo)
entrada = len(df_movimentacao_fundo)
validar_colunas(
    df_movimentacao_fundo,
    "fato_movimentacao_fundo.csv",
    ["id_fundo", "data_referencia", "aporte_liquido_mes"]
)
df_movimentacao_fundo = df_movimentacao_fundo.drop_duplicates(
    subset=["id_fundo", "data_referencia"]
).copy()
df_movimentacao_fundo["data_referencia"] = pd.to_datetime(
    df_movimentacao_fundo["data_referencia"], errors="coerce"
)
df_movimentacao_fundo["aporte_liquido_mes"] = pd.to_numeric(
    df_movimentacao_fundo["aporte_liquido_mes"], errors="coerce"
)
df_movimentacao_fundo = df_movimentacao_fundo.dropna(
    subset=["id_fundo", "data_referencia", "aporte_liquido_mes"]
)
df_movimentacao_fundo = df_movimentacao_fundo[
    df_movimentacao_fundo["aporte_liquido_mes"] >= 0
].copy()
df_movimentacao_fundo.to_csv(
    SILVER_DIR / "fato_movimentacao_fundo_silver.csv", index=False
)
registrar_qualidade(
    "fato_movimentacao_fundo",
    entrada,
    len(df_movimentacao_fundo),
    "Datas e aportes líquidos convertidos; medidas de rentabilidade reservadas à Gold"
)
print("- fato_movimentacao_fundo tratada.")

# Remove o arquivo legado para evitar que uma rentabilidade antiga continue
# sendo consumida após uma nova execução da Silver.
arquivo_rentabilidade_legado = SILVER_DIR / "fato_rentabilidade_silver.csv"
if arquivo_rentabilidade_legado.exists():
    arquivo_rentabilidade_legado.unlink()

# 6. Operações de recarga
arquivo = BRONZE_DIR / "fato_operacoes_recarga.csv"
df_operacoes = pd.read_csv(arquivo)
entrada = len(df_operacoes)
validar_colunas(
    df_operacoes,
    "fato_operacoes_recarga.csv",
    [
        "id_operacao", "id_projeto", "data_hora",
        "municipio_origem_veiculo", "uf_origem_veiculo",
        "tipo_veiculo_recarregavel", "veiculo_modelo",
        "energia_consumida_kwh", "tempo_utilizacao_min",
        "preco_kwh_brl", "receita_gerada_brl"
    ]
)
df_operacoes = df_operacoes.drop_duplicates(subset=["id_operacao"]).copy()
df_operacoes["data_hora"] = pd.to_datetime(
    df_operacoes["data_hora"], errors="coerce"
)
df_operacoes["municipio_origem_veiculo"] = df_operacoes[
    "municipio_origem_veiculo"
].map(normalizar_texto)
df_operacoes["uf_origem_veiculo"] = df_operacoes[
    "uf_origem_veiculo"
].map(normalizar_uf)
df_operacoes["tipo_veiculo_recarregavel"] = df_operacoes[
    "tipo_veiculo_recarregavel"
].map(normalizar_texto)

for coluna in [
    "energia_consumida_kwh", "tempo_utilizacao_min",
    "preco_kwh_brl", "receita_gerada_brl"
]:
    df_operacoes[coluna] = pd.to_numeric(
        df_operacoes[coluna], errors="coerce"
    )

ids_validos = set(df_projetos["id_projeto"])
df_operacoes = df_operacoes[
    df_operacoes["id_projeto"].isin(ids_validos)
    & df_operacoes["data_hora"].notna()
    & df_operacoes["municipio_origem_veiculo"].isin(municipios_validos)
    & (df_operacoes["uf_origem_veiculo"] == UF_ES)
    & df_operacoes["tipo_veiculo_recarregavel"].isin(
        {"ELETRICO", "HIBRIDO PLUG-IN"}
    )
    & (df_operacoes["energia_consumida_kwh"] > 0)
    & (df_operacoes["receita_gerada_brl"] > 0)
].copy()

# Acrescenta a localização do eletroposto e a referência de demanda do projeto.
localizacao_projeto = df_projetos[[
    "id_projeto", "municipio", "uf", "tipo_local", "qtd_carregadores",
    "potencia_instalada_kw", "frota_recarregavel_municipio_ref",
    "indice_demanda_senatran", "classe_demanda_senatran"
]].rename(columns={
    "municipio": "municipio_eletroposto",
    "uf": "uf_eletroposto"
})
df_operacoes = df_operacoes.merge(
    localizacao_projeto, on="id_projeto", how="left"
)

# Campos derivados para o dashboard e para a Gold.
df_operacoes["data_referencia"] = df_operacoes["data_hora"].dt.normalize()
df_operacoes["ano_mes"] = (
    df_operacoes["data_hora"].dt.to_period("M").astype(str)
)
df_operacoes["hora_recarga"] = df_operacoes["data_hora"].dt.hour
df_operacoes["dia_semana"] = df_operacoes["data_hora"].dt.day_name()
df_operacoes["origem_local"] = np.where(
    df_operacoes["municipio_origem_veiculo"]
    == df_operacoes["municipio_eletroposto"],
    "SIM",
    "NAO"
)
df_operacoes["custo_energia_brl"] = (
    df_operacoes["energia_consumida_kwh"] * 0.90
).round(2)
df_operacoes["margem_bruta_brl"] = (
    df_operacoes["receita_gerada_brl"]
    - df_operacoes["custo_energia_brl"]
).round(2)
df_operacoes.to_csv(
    SILVER_DIR / "fato_operacoes_recarga_silver.csv", index=False
)
registrar_qualidade(
    "fato_operacoes_recarga",
    entrada,
    len(df_operacoes),
    "Origem e localização ligadas a municípios da SENATRAN; datas, custo, margem e origem local criados"
)
print("- fato_operacoes_recarga tratada.")

# 7. Selic: a API é ingerida na Bronze e apenas tratada aqui.
arquivo = BRONZE_DIR / "selic_bcb_bruta.csv"
if arquivo.exists():
    df_selic = pd.read_csv(arquivo)
    entrada = len(df_selic)
    df_selic.columns = [
        normalizar_texto(coluna).lower() for coluna in df_selic.columns
    ]
    df_selic["data"] = pd.to_datetime(
        df_selic["data"], format="%d/%m/%Y", errors="coerce"
    )
    df_selic["valor"] = pd.to_numeric(
        df_selic["valor"].astype(str).str.replace(",", ".", regex=False),
        errors="coerce"
    )
    df_selic = df_selic[df_selic["data"] >= "2023-01-01"].copy()
    df_selic = df_selic.rename(columns={
        "data": "data_referencia",
        "valor": "taxa_selic_mes"
    })
    df_selic = df_selic.dropna(
        subset=["data_referencia", "taxa_selic_mes"]
    )
    df_selic.to_csv(
        SILVER_DIR / "ext_selic_silver.csv", index=False
    )
    registrar_qualidade(
        "ext_selic",
        entrada,
        len(df_selic),
        "Fonte bruta do BCB filtrada a partir de 2023"
    )
    print("- ext_selic tratada.")
else:
    raise FileNotFoundError(
        "Selic bruta não encontrada; execute primeiro 01_ingestao_bronze.py."
    )

pd.DataFrame(controle_qualidade).to_csv(
    SILVER_DIR / "controle_qualidade_silver.csv", index=False
)
print("Camada Silver gerada com sucesso.")
