from datetime import datetime, timedelta
from pathlib import Path
import random
import re
import unicodedata

import numpy as np
import pandas as pd
import requests
from faker import Faker

# Caminhos relativos ao próprio projeto.
BASE_DIR = Path(__file__).resolve().parent
BRONZE_DIR = BASE_DIR / "camada_bronze"
BRONZE_DIR.mkdir(exist_ok=True)

# Semente fixa para que os dados simulados possam ser reproduzidos.
SEMENTE = 42
random.seed(SEMENTE)
np.random.seed(SEMENTE)
Faker.seed(SEMENTE)
fake = Faker("pt_BR")

UF_ES = "ESPIRITO SANTO"
COMBUSTIVEIS_RECARREGAVEIS = {
    "ELETRICO",
    "ELETRICO/FONTE EXTERNA",
    "HIBRIDO PLUG-IN"
}


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


def carregar_frota_recarregavel_senatran():
    """
    Lê a fonte bruta da SENATRAN e cria uma referência municipal usada
    somente para orientar a simulação dos dados internos da Bronze.

    A planilha original continua preservada como fonte bruta. O resultado
    agregado e oficialmente tratado será gerado no script da Silver.
    """
    caminho = BRONZE_DIR / "frota_senatran_bruta.xlsx"
    if not caminho.exists():
        raise FileNotFoundError(
            "Inclua camada_bronze/frota_senatran_bruta.xlsx antes de executar "
            "a geração da Bronze. Os dados internos dependem dessa referência."
        )

    df = pd.read_excel(caminho)
    df.columns = [normalizar_texto(coluna).lower() for coluna in df.columns]
    df = df.rename(columns={
        "combustivel veiculo": "combustivel",
        "qtd. veiculos": "quantidade_veiculos"
    })

    colunas_esperadas = {
        "uf", "municipio", "combustivel", "quantidade_veiculos"
    }
    faltantes = colunas_esperadas.difference(df.columns)
    if faltantes:
        raise ValueError(
            f"A planilha da SENATRAN não possui as colunas: {sorted(faltantes)}"
        )

    for coluna in ["uf", "municipio", "combustivel"]:
        df[coluna] = df[coluna].map(normalizar_texto)
    df["quantidade_veiculos"] = pd.to_numeric(
        df["quantidade_veiculos"], errors="coerce"
    ).fillna(0)

    df_es = df[df["uf"] == UF_ES].copy()
    municipios_es = df_es[["municipio"]].drop_duplicates()
    recarregaveis = df_es[
        df_es["combustivel"].isin(COMBUSTIVEIS_RECARREGAVEIS)
    ].copy()

    eletricos = (
        recarregaveis[
            recarregaveis["combustivel"].isin(
                {"ELETRICO", "ELETRICO/FONTE EXTERNA"}
            )
        ]
        .groupby("municipio", as_index=False)["quantidade_veiculos"]
        .sum()
        .rename(columns={"quantidade_veiculos": "frota_eletrica"})
    )
    plugins = (
        recarregaveis[recarregaveis["combustivel"] == "HIBRIDO PLUG-IN"]
        .groupby("municipio", as_index=False)["quantidade_veiculos"]
        .sum()
        .rename(columns={"quantidade_veiculos": "frota_hibrida_plugin"})
    )

    frota = (
        municipios_es
        .merge(eletricos, on="municipio", how="left")
        .merge(plugins, on="municipio", how="left")
    )
    frota[["frota_eletrica", "frota_hibrida_plugin"]] = (
        frota[["frota_eletrica", "frota_hibrida_plugin"]]
        .fillna(0)
        .astype(int)
    )
    frota["frota_recarregavel"] = (
        frota["frota_eletrica"] + frota["frota_hibrida_plugin"]
    )

    total_es = max(int(frota["frota_recarregavel"].sum()), 1)
    maior_frota = max(int(frota["frota_recarregavel"].max()), 1)
    frota["participacao_frota_es_pct"] = (
        frota["frota_recarregavel"] / total_es * 100
    ).round(4)

    # Raiz quadrada reduz a distância entre a capital e cidades menores,
    # mantendo uma relação crescente com a frota real.
    frota["indice_demanda_senatran"] = (
        np.sqrt(frota["frota_recarregavel"] / maior_frota) * 100
    ).round(2)
    frota["classe_demanda_senatran"] = np.select(
        [
            frota["indice_demanda_senatran"] >= 70,
            frota["indice_demanda_senatran"] >= 40,
            frota["indice_demanda_senatran"] >= 15,
            frota["frota_recarregavel"] > 0
        ],
        ["MUITO ALTA", "ALTA", "MEDIA", "BAIXA"],
        default="SEM FROTA RECARREGAVEL"
    )
    return frota.sort_values("frota_recarregavel", ascending=False).reset_index(
        drop=True
    )


def escolha_ponderada(valores, pesos):
    """Escolhe um valor usando pesos numéricos seguros."""
    pesos = np.asarray(pesos, dtype=float)
    if pesos.sum() <= 0:
        pesos = np.ones(len(valores), dtype=float)
    return random.choices(list(valores), weights=pesos, k=1)[0]


print("Iniciando a ingestão e geração da Camada Bronze...")

# A fonte externa é lida antes da simulação para orientar projetos, cotistas
# e operações de recarga por município.
frota_senatran = carregar_frota_recarregavel_senatran()
frota_positiva = frota_senatran[
    frota_senatran["frota_recarregavel"] > 0
].copy()
print(
    f"- Referência SENATRAN carregada: "
    f"{int(frota_senatran['frota_recarregavel'].sum())} veículos "
    f"recarregáveis em {len(frota_senatran)} municípios do ES."
)

# 1. Cadastro do fundo
pd.DataFrame({
    "id_fundo": [1],
    "nome_fundo": ["Banestes Infra EV ESG FII"],
    "taxa_administracao": [0.015],
    "benchmark": ["IPCA + 6%"],
    "data_inicio": ["2023-01-01"]
}).to_csv(BRONZE_DIR / "dim_fundo.csv", index=False)

# 2. Projetos de eletropostos
# Os 12 municípios com maior frota recebem pelo menos um projeto. Os demais
# projetos são distribuídos por peso crescente da frota real da SENATRAN.
quantidade_projetos = 30
quantidade_municipios_garantidos = min(12, len(frota_positiva))
municipios_projetos = frota_positiva.head(
    quantidade_municipios_garantidos
)["municipio"].tolist()

quantidade_restante = quantidade_projetos - len(municipios_projetos)
pesos_expansao = np.power(
    frota_positiva["frota_recarregavel"].to_numpy() + 1,
    0.78
)
municipios_projetos.extend(
    random.choices(
        frota_positiva["municipio"].tolist(),
        weights=pesos_expansao,
        k=quantidade_restante
    )
)
random.shuffle(municipios_projetos)
projetos_por_municipio = pd.Series(municipios_projetos).value_counts().to_dict()

linhas_frota = frota_senatran.set_index("municipio").to_dict("index")
tipos_urbanos = [
    "Shopping", "Supermercado", "Estacionamento Privado",
    "Posto de Combustível", "Rodovia"
]
tipos_rodoviarios = [
    "Posto de Combustível", "Rodovia", "Supermercado",
    "Estacionamento Privado", "Shopping"
]
projetos = []
hoje = datetime.now().date()

for id_projeto, municipio in enumerate(municipios_projetos, start=1):
    ref = linhas_frota[municipio]
    indice_demanda = float(ref["indice_demanda_senatran"])
    numero_projetos_cidade = projetos_por_municipio[municipio]

    if indice_demanda >= 70:
        qtd_carregadores = random.randint(5, 8)
        potencia = random.choice([100, 150, 150])
        tipo_local = random.choices(
            tipos_urbanos, weights=[28, 27, 22, 18, 5], k=1
        )[0]
        prob_operacao = 0.94
    elif indice_demanda >= 40:
        qtd_carregadores = random.randint(4, 7)
        potencia = random.choice([100, 100, 150])
        tipo_local = random.choices(
            tipos_urbanos, weights=[22, 25, 20, 23, 10], k=1
        )[0]
        prob_operacao = 0.88
    elif indice_demanda >= 15:
        qtd_carregadores = random.randint(3, 5)
        potencia = random.choice([50, 100, 100])
        tipo_local = random.choices(
            tipos_rodoviarios, weights=[28, 22, 22, 18, 10], k=1
        )[0]
        prob_operacao = 0.82
    else:
        qtd_carregadores = random.randint(2, 4)
        potencia = random.choice([50, 50, 100])
        tipo_local = random.choices(
            tipos_rodoviarios, weights=[32, 28, 20, 15, 5], k=1
        )[0]
        prob_operacao = 0.72

    status = random.choices(
        ["Em Operação", "Em Construção"],
        weights=[prob_operacao, 1 - prob_operacao],
        k=1
    )[0]

    # O investimento cresce com número de carregadores e potência instalada.
    capex_base = 70_000 + qtd_carregadores * 42_000 + potencia * 450
    capex = capex_base * random.uniform(0.93, 1.08)
    opex = (
        1_200 + qtd_carregadores * 480 + potencia * 8
    ) * random.uniform(0.92, 1.08)

    # Estimativa simples: parte da frota local tende a realizar recargas
    # públicas, dividida pelos projetos existentes no município.
    demanda_mensal = max(
        12,
        round(
            (ref["frota_recarregavel"] / numero_projetos_cidade)
            * random.uniform(0.28, 0.42)
            + qtd_carregadores * random.uniform(5, 9)
        )
    )

    if status == "Em Operação":
        inicio_minimo = hoje - timedelta(days=730)
        inicio_maximo = hoje - timedelta(days=60)
        intervalo = max((inicio_maximo - inicio_minimo).days, 1)
        data_inicio_operacao = inicio_minimo + timedelta(
            days=random.randint(0, intervalo)
        )
    else:
        data_inicio_operacao = pd.NaT

    projetos.append({
        "id_projeto": id_projeto,
        "municipio": municipio,
        "uf": UF_ES,
        "tipo_local": tipo_local,
        "capex": round(capex, 2),
        "opex_mensal": round(opex, 2),
        "qtd_carregadores": qtd_carregadores,
        "potencia_instalada_kw": potencia,
        "status": status,
        "data_inicio_operacao": (
            data_inicio_operacao.strftime("%Y-%m-%d")
            if pd.notna(data_inicio_operacao) else ""
        ),
        "frota_eletrica_municipio_ref": int(ref["frota_eletrica"]),
        "frota_hibrida_plugin_municipio_ref": int(
            ref["frota_hibrida_plugin"]
        ),
        "frota_recarregavel_municipio_ref": int(
            ref["frota_recarregavel"]
        ),
        "participacao_frota_es_pct": float(
            ref["participacao_frota_es_pct"]
        ),
        "indice_demanda_senatran": indice_demanda,
        "classe_demanda_senatran": ref["classe_demanda_senatran"],
        "demanda_mensal_estimada_recargas": demanda_mensal,
        "fonte_demanda": "SENATRAN"
    })

df_projetos = pd.DataFrame(projetos)
df_projetos.to_csv(BRONZE_DIR / "dim_projetos.csv", index=False)

# 3. Cotistas do fundo
# A cidade de origem também é escolhida com base na presença real de veículos
# recarregáveis, mas com expoente menor para não concentrar todos os cotistas
# apenas na Grande Vitória.
perfis = ["Conservador", "Moderado", "Arrojado"]
pesos_cotistas = np.power(
    frota_senatran["frota_recarregavel"].to_numpy() + 1,
    0.55
)
cotistas = []
for _ in range(150):
    municipio = escolha_ponderada(
        frota_senatran["municipio"], pesos_cotistas
    )
    perfil = random.choices(
        perfis, weights=[0.2, 0.5, 0.3], k=1
    )[0]
    faixas_valor = {
        "Conservador": (5_000, 80_000),
        "Moderado": (10_000, 130_000),
        "Arrojado": (15_000, 180_000)
    }
    minimo, maximo = faixas_valor[perfil]
    cotistas.append({
        "id_cotista": fake.unique.random_int(min=1000, max=9999),
        "perfil_risco": perfil,
        "municipio_origem": municipio,
        "uf": UF_ES,
        "data_entrada": fake.date_between(start_date="-2y", end_date="today"),
        "valor_investido": round(random.uniform(minimo, maximo), 2)
    })

pd.DataFrame(cotistas).to_csv(BRONZE_DIR / "dim_cotistas.csv", index=False)

# 4. Movimentações mensais do fundo
# A Bronze registra somente o fato bruto de entrada de capital. Valor da cota,
# patrimônio e rentabilidade são medidas consolidadas posteriormente na Gold.
# ME = último dia de cada mês.
datas_movimentacao = pd.date_range(
    start="2023-01-01", end=datetime.today(), freq="ME"
)
movimentacoes_fundo = []

for data in datas_movimentacao:
    # Mantém o avanço da sequência pseudoaleatória das versões anteriores para
    # que a simulação posterior das operações não seja alterada por esta troca.
    # O valor consumido não representa nem é armazenado como rentabilidade.
    random.random()
    aporte_liquido = random.uniform(50_000, 200_000)
    movimentacoes_fundo.append({
        "id_fundo": 1,
        "data_referencia": data.strftime("%Y-%m-%d"),
        "aporte_liquido_mes": round(aporte_liquido, 2)
    })

pd.DataFrame(movimentacoes_fundo).to_csv(
    BRONZE_DIR / "fato_movimentacao_fundo.csv", index=False
)

# Remove o arquivo legado para impedir o uso acidental de rentabilidade
# simulada diretamente na Bronze.
arquivo_rentabilidade_legado = BRONZE_DIR / "fato_rentabilidade.csv"
if arquivo_rentabilidade_legado.exists():
    arquivo_rentabilidade_legado.unlink()

# 5. Operações de recarga
# A quantidade de recargas por projeto é distribuída usando a frota local,
# a demanda estimada e a quantidade de carregadores. Assim, cidades com mais
# veículos recarregáveis tendem a registrar mais operações.
projetos_ativos = df_projetos[df_projetos["status"] == "Em Operação"].copy()
if projetos_ativos.empty:
    raise ValueError("Nenhum projeto em operação foi gerado.")

projetos_ativos["peso_operacoes"] = (
    np.power(
        projetos_ativos["frota_recarregavel_municipio_ref"] + 5,
        0.82
    )
    * np.power(projetos_ativos["qtd_carregadores"], 0.65)
    / np.power(
        projetos_ativos.groupby("municipio")["id_projeto"].transform("count"),
        0.55
    )
    * np.random.uniform(0.90, 1.10, len(projetos_ativos))
)

quantidade_operacoes = 220000 # 1 carga a cada 2 semanas por veículo
minimo_por_projeto = 20
base_total = minimo_por_projeto * len(projetos_ativos)
restante = max(quantidade_operacoes - base_total, 0)
probabilidades = (
    projetos_ativos["peso_operacoes"]
    / projetos_ativos["peso_operacoes"].sum()
).to_numpy()
alocacao = np.random.multinomial(restante, probabilidades)
projetos_ativos["quantidade_operacoes"] = minimo_por_projeto + alocacao

modelos_eletricos = [
    "BYD Dolphin", "BYD Seal", "Volvo EX30", "GWM Ora 03",
    "Nissan Leaf", "Renault Kwid E-Tech", "Porsche Taycan"
]
modelos_plugin = [
    "BYD Song Plus DM-i", "GWM Haval H6 PHEV",
    "Volvo XC60 Recharge", "Jeep Compass 4xe"
]
horas = list(range(6, 24))
pesos_horas = [2, 2, 3, 4, 5, 6, 7, 8, 8, 7, 6, 7, 8, 9, 10, 9, 6, 3]
data_inicial_geral = hoje - timedelta(days=365)
municipios_origem = frota_senatran["municipio"].tolist()
pesos_origem = np.power(
    frota_senatran["frota_recarregavel"].to_numpy() + 1,
    0.72
)
operacoes = []

for _, projeto in projetos_ativos.iterrows():
    inicio_projeto = pd.to_datetime(
        projeto["data_inicio_operacao"], errors="coerce"
    ).date()
    inicio_operacoes = max(data_inicial_geral, inicio_projeto)
    intervalo_dias = max((hoje - inicio_operacoes).days, 0)

    total_local = max(
        int(projeto["frota_recarregavel_municipio_ref"]), 1
    )
    proporcao_eletricos = (
        projeto["frota_eletrica_municipio_ref"] / total_local
    )

    for _ in range(int(projeto["quantidade_operacoes"])):
        dia = inicio_operacoes + timedelta(
            days=random.randint(0, intervalo_dias)
        )
        hora = random.choices(horas, weights=pesos_horas, k=1)[0]
        data_recarga = datetime.combine(
            dia, datetime.min.time()
        ) + timedelta(
            hours=hora,
            minutes=random.randint(0, 59),
            seconds=random.randint(0, 59)
        )

        # Aproximadamente 82% das sessões são de veículos registrados na
        # própria cidade; o restante representa deslocamentos intermunicipais.
        if random.random() < 0.82:
            municipio_origem = projeto["municipio"]
        else:
            municipio_origem = escolha_ponderada(
                municipios_origem, pesos_origem
            )

        if random.random() < proporcao_eletricos:
            tipo_veiculo = "ELETRICO"
            modelo = random.choice(modelos_eletricos)
            energia_kwh = float(np.clip(np.random.normal(37, 12), 12, 70))
            potencia_efetiva = min(
                float(projeto["potencia_instalada_kw"]), 90
            )
        else:
            tipo_veiculo = "HIBRIDO PLUG-IN"
            modelo = random.choice(modelos_plugin)
            energia_kwh = float(np.clip(np.random.normal(16, 5), 6, 30))
            potencia_efetiva = min(
                float(projeto["potencia_instalada_kw"]), 22
            )

        energia_kwh = round(energia_kwh, 2)
        tempo_min = round(
            energia_kwh / max(potencia_efetiva * 0.82, 1) * 60
            + random.uniform(5, 15)
        )
        tempo_min = int(np.clip(tempo_min, 15, 150))

        preco_base = 2.00 + projeto["potencia_instalada_kw"] / 300
        preco_kwh = round(
            preco_base + random.choice([0.00, 0.10, 0.20, 0.30]), 2
        )

        operacoes.append({
            "id_operacao": fake.unique.uuid4(),
            "id_projeto": int(projeto["id_projeto"]),
            "data_hora": data_recarga.strftime("%Y-%m-%d %H:%M:%S"),
            "municipio_origem_veiculo": municipio_origem,
            "uf_origem_veiculo": UF_ES,
            "tipo_veiculo_recarregavel": tipo_veiculo,
            "veiculo_modelo": modelo,
            "energia_consumida_kwh": energia_kwh,
            "tempo_utilizacao_min": tempo_min,
            "preco_kwh_brl": preco_kwh,
            "receita_gerada_brl": round(energia_kwh * preco_kwh, 2)
        })

pd.DataFrame(operacoes).to_csv(
    BRONZE_DIR / "fato_operacoes_recarga.csv", index=False
)

# 6. Ingestão bruta da Selic
# A Bronze guarda os campos exatamente como chegam da API.
url_bcb = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.4390/dados?formato=json"
caminho_selic_bruta = BRONZE_DIR / "selic_bcb_bruta.csv"

try:
    resposta = requests.get(url_bcb, timeout=30)
    resposta.raise_for_status()
    pd.DataFrame(resposta.json()).to_csv(caminho_selic_bruta, index=False)
    print("- Selic bruta obtida da API do Banco Central.")
except Exception as erro:
    if caminho_selic_bruta.exists():
        print(f"- API da Selic indisponível; arquivo Bronze existente mantido: {erro}")
    else:
        print(f"- Não foi possível obter a Selic: {erro}")

print(
    "- Projetos e operações foram distribuídos conforme a frota recarregável "
    "municipal da SENATRAN."
)
print("Camada Bronze gerada com sucesso.")
