from pathlib import Path
import re
import unicodedata

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
BRONZE_DIR = BASE_DIR / "camada_bronze"
SILVER_DIR = BASE_DIR / "camada_silver"
SILVER_DIR.mkdir(exist_ok=True)

UF_ES = "ESPIRITO SANTO"
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


print("Iniciando o tratamento da Camada Silver...")

# 1. Fundo
arquivo = BRONZE_DIR / "dim_fundo.csv"
df = pd.read_csv(arquivo)
entrada = len(df)
df = df.drop_duplicates(subset=["id_fundo"]).copy()
df["data_inicio"] = pd.to_datetime(df["data_inicio"], errors="coerce")
df["taxa_administracao"] = pd.to_numeric(
    df["taxa_administracao"], errors="coerce"
)
df = df.dropna(subset=["id_fundo", "nome_fundo", "data_inicio"])
df.to_csv(SILVER_DIR / "dim_fundo_silver.csv", index=False)
registrar_qualidade("dim_fundo", entrada, len(df), "Tipos e chave do fundo validados")
print("- dim_fundo tratada.")

# 2. Projetos
arquivo = BRONZE_DIR / "dim_projetos.csv"
df_projetos = pd.read_csv(arquivo)
entrada = len(df_projetos)
df_projetos = df_projetos.drop_duplicates(subset=["id_projeto"]).copy()
df_projetos["municipio"] = df_projetos["municipio"].map(normalizar_texto)
df_projetos["uf"] = df_projetos["uf"].map(normalizar_uf)
df_projetos["status"] = df_projetos["status"].str.strip().str.title()

colunas_numericas = [
    "capex", "opex_mensal", "qtd_carregadores", "potencia_instalada_kw"
]
for coluna in colunas_numericas:
    df_projetos[coluna] = pd.to_numeric(df_projetos[coluna], errors="coerce")

df_projetos = df_projetos[
    (df_projetos["uf"] == UF_ES)
    & (df_projetos["capex"] > 0)
    & (df_projetos["opex_mensal"] > 0)
    & (df_projetos["qtd_carregadores"] > 0)
].copy()
df_projetos.to_csv(SILVER_DIR / "dim_projetos_silver.csv", index=False)
registrar_qualidade(
    "dim_projetos", entrada, len(df_projetos),
    "Município e UF padronizados; valores inválidos removidos"
)
print("- dim_projetos tratada.")

# 3. Cotistas
arquivo = BRONZE_DIR / "dim_cotistas.csv"
df_cotistas = pd.read_csv(arquivo)
entrada = len(df_cotistas)
df_cotistas = df_cotistas.drop_duplicates(subset=["id_cotista"]).copy()
df_cotistas["municipio_origem"] = df_cotistas["municipio_origem"].map(
    normalizar_texto
)
df_cotistas["uf"] = df_cotistas["uf"].map(normalizar_uf)
df_cotistas["data_entrada"] = pd.to_datetime(
    df_cotistas["data_entrada"], errors="coerce"
)
df_cotistas["valor_investido"] = pd.to_numeric(
    df_cotistas["valor_investido"], errors="coerce"
)
df_cotistas = df_cotistas[
    (df_cotistas["uf"] == UF_ES)
    & df_cotistas["data_entrada"].notna()
    & (df_cotistas["valor_investido"] > 0)
].copy()
df_cotistas.to_csv(SILVER_DIR / "dim_cotistas_silver.csv", index=False)
registrar_qualidade(
    "dim_cotistas", entrada, len(df_cotistas),
    "Município realista, UF, datas e valores padronizados"
)
print("- dim_cotistas tratada.")

# 4. Rentabilidade
arquivo = BRONZE_DIR / "fato_rentabilidade.csv"
df_rentabilidade = pd.read_csv(arquivo)
entrada = len(df_rentabilidade)
df_rentabilidade = df_rentabilidade.drop_duplicates(
    subset=["id_fundo", "data_referencia"]
).copy()
df_rentabilidade["data_referencia"] = pd.to_datetime(
    df_rentabilidade["data_referencia"], errors="coerce"
)
for coluna in [
    "valor_cota", "patrimonio_liquido",
    "aporte_liquido_mes", "rentabilidade_mes"
]:
    df_rentabilidade[coluna] = pd.to_numeric(
        df_rentabilidade[coluna], errors="coerce"
    )
df_rentabilidade = df_rentabilidade.dropna(
    subset=[
        "id_fundo", "data_referencia", "valor_cota",
        "patrimonio_liquido", "aporte_liquido_mes", "rentabilidade_mes"
    ]
)
df_rentabilidade["rentabilidade_pct"] = (
    df_rentabilidade["rentabilidade_mes"] * 100
).round(2)
df_rentabilidade.to_csv(
    SILVER_DIR / "fato_rentabilidade_silver.csv", index=False
)
registrar_qualidade(
    "fato_rentabilidade", entrada, len(df_rentabilidade),
    "Datas, aporte líquido e medidas financeiras convertidos; percentual calculado"
)
print("- fato_rentabilidade tratada.")

# 5. Operações de recarga
arquivo = BRONZE_DIR / "fato_operacoes_recarga.csv"
df_operacoes = pd.read_csv(arquivo)
entrada = len(df_operacoes)
df_operacoes = df_operacoes.drop_duplicates(subset=["id_operacao"]).copy()
df_operacoes["data_hora"] = pd.to_datetime(
    df_operacoes["data_hora"], errors="coerce"
)
for coluna in [
    "energia_consumida_kwh", "tempo_utilizacao_min",
    "preco_kwh_brl", "receita_gerada_brl"
]:
    df_operacoes[coluna] = pd.to_numeric(df_operacoes[coluna], errors="coerce")

ids_validos = set(df_projetos["id_projeto"])
df_operacoes = df_operacoes[
    df_operacoes["id_projeto"].isin(ids_validos)
    & df_operacoes["data_hora"].notna()
    & (df_operacoes["energia_consumida_kwh"] > 0)
    & (df_operacoes["receita_gerada_brl"] > 0)
].copy()

# Campos derivados úteis para o dashboard e para a futura Gold.
df_operacoes["data_referencia"] = df_operacoes["data_hora"].dt.normalize()
df_operacoes["ano_mes"] = df_operacoes["data_hora"].dt.to_period("M").astype(str)
df_operacoes["hora_recarga"] = df_operacoes["data_hora"].dt.hour
df_operacoes["custo_energia_brl"] = (
    df_operacoes["energia_consumida_kwh"] * 0.90
).round(2)
df_operacoes["margem_bruta_brl"] = (
    df_operacoes["receita_gerada_brl"] - df_operacoes["custo_energia_brl"]
).round(2)
df_operacoes.to_csv(
    SILVER_DIR / "fato_operacoes_recarga_silver.csv", index=False
)
registrar_qualidade(
    "fato_operacoes_recarga", entrada, len(df_operacoes),
    "Chaves validadas; datas, ano-mês, hora, custo e margem criados"
)
print("- fato_operacoes_recarga tratada.")

# 6. Selic: a API é ingerida na Bronze e apenas tratada aqui.
arquivo = BRONZE_DIR / "selic_bcb_bruta.csv"
if arquivo.exists():
    df_selic = pd.read_csv(arquivo)
    entrada = len(df_selic)
    df_selic.columns = [normalizar_texto(c).lower() for c in df_selic.columns]
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
    df_selic = df_selic.dropna(subset=["data_referencia", "taxa_selic_mes"])
    df_selic.to_csv(SILVER_DIR / "ext_selic_silver.csv", index=False)
    registrar_qualidade(
        "ext_selic", entrada, len(df_selic),
        "Fonte bruta do BCB filtrada a partir de 2023"
    )
    print("- ext_selic tratada.")
else:
    print("- Selic bruta não encontrada; execute primeiro 01_ingestao_bronze.py.")

# 7. SENATRAN
arquivo = BRONZE_DIR / "frota_senatran_bruta.xlsx"
if arquivo.exists():
    df_senatran = pd.read_excel(arquivo)
    entrada = len(df_senatran)
    df_senatran.columns = [normalizar_texto(c).lower() for c in df_senatran.columns]

    # Após remover acentos, os nomes esperados são estes.
    df_senatran = df_senatran.rename(columns={
        "municipio": "municipio",
        "combustivel veiculo": "combustivel",
        "qtd. veiculos": "quantidade_veiculos"
    })
    df_senatran["uf"] = df_senatran["uf"].map(normalizar_uf)
    df_senatran["municipio"] = df_senatran["municipio"].map(normalizar_texto)
    df_senatran["combustivel"] = df_senatran["combustivel"].map(normalizar_texto)
    df_senatran["quantidade_veiculos"] = pd.to_numeric(
        df_senatran["quantidade_veiculos"], errors="coerce"
    ).fillna(0)

    # O arquivo usa ESPIRITO SANTO, e não ES.
    df_es = df_senatran[df_senatran["uf"] == UF_ES].copy()
    municipios_es = df_es[["uf", "municipio"]].drop_duplicates()

    # Apenas veículos que podem receber recarga em tomada/eletroposto.
    # Não entram híbridos convencionais nem veículos que geram energia a bordo.
    combustiveis_recarregaveis = {
        "ELETRICO",
        "ELETRICO/FONTE EXTERNA",
        "HIBRIDO PLUG-IN"
    }
    df_recarregaveis = df_es[
        df_es["combustivel"].isin(combustiveis_recarregaveis)
    ].copy()

    # Elétricos a bateria e híbridos plug-in são agregados separadamente.
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
    colunas_frota = ["frota_eletrica", "frota_hibrida_plugin"]
    df_frota_es[colunas_frota] = (
        df_frota_es[colunas_frota].fillna(0).astype(int)
    )
    df_frota_es["frota_recarregavel"] = (
        df_frota_es["frota_eletrica"]
        + df_frota_es["frota_hibrida_plugin"]
    )
    df_frota_es = df_frota_es.sort_values(
        "frota_recarregavel", ascending=False
    )
    df_frota_es.to_csv(
        SILVER_DIR / "ext_senatran_es_silver.csv", index=False
    )
    registrar_qualidade(
        "ext_senatran_es", entrada, len(df_frota_es),
        "UF corrigida; filtro limitado a ELETRICO, ELETRICO/FONTE EXTERNA e HIBRIDO PLUG-IN"
    )
    print("- ext_senatran_es tratada.")
else:
    print("- Arquivo bruto da SENATRAN não encontrado.")

pd.DataFrame(controle_qualidade).to_csv(
    SILVER_DIR / "controle_qualidade_silver.csv", index=False
)
print("Camada Silver gerada com sucesso.")
