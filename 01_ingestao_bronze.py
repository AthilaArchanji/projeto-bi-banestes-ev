from datetime import datetime, timedelta
from pathlib import Path
import random

import numpy as np
import pandas as pd
import requests
from faker import Faker

# Caminhos relativos ao próprio projeto. Assim, os scripts funcionam mesmo
# quando são executados a partir de outra pasta.
BASE_DIR = Path(__file__).resolve().parent
BRONZE_DIR = BASE_DIR / "camada_bronze"
BRONZE_DIR.mkdir(exist_ok=True)

# Semente fixa para que a geração fake seja reproduzível.
SEMENTE = 42
random.seed(SEMENTE)
np.random.seed(SEMENTE)
Faker.seed(SEMENTE)
fake = Faker("pt_BR")

UF_ES = "ESPIRITO SANTO"

# Municípios reais do Espírito Santo usados nos dados internos simulados.
# Os pesos deixam a distribuição mais concentrada na Grande Vitória e em
# municípios economicamente maiores, sem impedir o aparecimento dos demais.
MUNICIPIOS_ES = [
    "Vitória", "Vila Velha", "Serra", "Cariacica", "Viana", "Guarapari",
    "Fundão", "Domingos Martins", "Santa Teresa", "Aracruz", "Linhares",
    "Colatina", "São Mateus", "Nova Venécia", "Barra de São Francisco",
    "Cachoeiro de Itapemirim", "Castelo", "Alegre", "Marataízes",
    "Itapemirim", "Anchieta", "Piúma", "Venda Nova do Imigrante",
    "Santa Maria de Jetibá", "Afonso Cláudio", "Conceição da Barra",
    "Jaguaré", "Ibiraçu", "João Neiva", "Mimoso do Sul"
]
PESOS_MUNICIPIOS = [
    12, 14, 14, 11, 4, 6, 2, 3, 2, 5, 7, 6, 5, 3, 2,
    7, 2, 2, 3, 3, 3, 2, 3, 3, 2, 2, 2, 2, 2, 2
]


def escolher_municipio():
    return random.choices(MUNICIPIOS_ES, weights=PESOS_MUNICIPIOS, k=1)[0]


print("Iniciando a ingestão e geração da Camada Bronze...")

# 1. Cadastro do fundo
pd.DataFrame({
    "id_fundo": [1],
    "nome_fundo": ["Banestes Infra EV ESG FII"],
    "taxa_administracao": [0.015],
    "benchmark": ["IPCA + 6%"],
    "data_inicio": ["2023-01-01"]
}).to_csv(BRONZE_DIR / "dim_fundo.csv", index=False)

# 2. Projetos de eletropostos
# A coluna UF já nasce com o padrão esperado pelo projeto.
tipos_local = [
    "Shopping", "Posto de Combustível", "Rodovia",
    "Supermercado", "Estacionamento Privado"
]
projetos = []
for id_projeto in range(1, 31):
    status = random.choices(
        ["Em Operação", "Em Construção"], weights=[0.8, 0.2], k=1
    )[0]
    projetos.append({
        "id_projeto": id_projeto,
        "municipio": escolher_municipio(),
        "uf": UF_ES,
        "tipo_local": random.choice(tipos_local),
        "capex": round(random.uniform(150_000, 450_000), 2),
        "opex_mensal": round(random.uniform(2_000, 5_000), 2),
        "qtd_carregadores": random.randint(2, 6),
        "potencia_instalada_kw": random.choice([50, 100, 150]),
        "status": status
    })

df_projetos = pd.DataFrame(projetos)
df_projetos.to_csv(BRONZE_DIR / "dim_projetos.csv", index=False)

# 3. Cotistas do fundo
# Não usamos Faker.city(), pois ele gerava nomes que pareciam sobrenomes.
perfis = ["Conservador", "Moderado", "Arrojado"]
cotistas = []
for _ in range(150):
    cotistas.append({
        "id_cotista": fake.unique.random_int(min=1000, max=9999),
        "perfil_risco": random.choices(
            perfis, weights=[0.2, 0.5, 0.3], k=1
        )[0],
        "municipio_origem": escolher_municipio(),
        "uf": UF_ES,
        "data_entrada": fake.date_between(start_date="-2y", end_date="today"),
        "valor_investido": round(random.uniform(5_000, 150_000), 2)
    })

pd.DataFrame(cotistas).to_csv(BRONZE_DIR / "dim_cotistas.csv", index=False)

# 4. Rentabilidade mensal do fundo
# ME = último dia de cada mês.
datas_rentabilidade = pd.date_range(
    start="2023-01-01", end=datetime.today(), freq="ME"
)
rentabilidade = []
cota_atual = 100.0
pl_atual = 15_000_000.0

for data in datas_rentabilidade:
    variacao = random.uniform(-0.01, 0.025)
    aporte_liquido = random.uniform(50_000, 200_000)
    cota_atual *= 1 + variacao
    pl_atual = pl_atual * (1 + variacao) + aporte_liquido

    rentabilidade.append({
        "id_fundo": 1,
        "data_referencia": data.strftime("%Y-%m-%d"),
        "valor_cota": round(cota_atual, 2),
        "patrimonio_liquido": round(pl_atual, 2),
        # Entradas menos saídas de recursos dos cotistas no mês.
        # O campo permite separar crescimento por captação de crescimento
        # causado pela rentabilidade do fundo.
        "aporte_liquido_mes": round(aporte_liquido, 2),
        "rentabilidade_mes": round(variacao, 4)
    })

pd.DataFrame(rentabilidade).to_csv(
    BRONZE_DIR / "fato_rentabilidade.csv", index=False
)

# 5. Operações de recarga
# A hora é sorteada diretamente para evitar horários fora do intervalo 06h-23h.
projetos_ativos = df_projetos.loc[
    df_projetos["status"] == "Em Operação", "id_projeto"
].tolist()
modelos_veiculos = [
    "BYD Dolphin", "BYD Seal", "Volvo EX30", "GWM Ora 03",
    "Nissan Leaf", "Porsche Taycan", "Renault Kwid E-Tech"
]
operacoes = []
data_inicial = datetime.now().date() - timedelta(days=365)

for _ in range(8_000):
    dia = data_inicial + timedelta(days=random.randint(0, 365))
    data_recarga = datetime.combine(
        dia,
        datetime.min.time()
    ) + timedelta(
        hours=random.randint(6, 23),
        minutes=random.randint(0, 59),
        seconds=random.randint(0, 59)
    )
    energia_kwh = round(random.uniform(10, 60), 2)
    preco_kwh = random.choice([1.99, 2.10, 2.29, 2.49])

    operacoes.append({
        "id_operacao": fake.unique.uuid4(),
        "id_projeto": random.choice(projetos_ativos),
        "data_hora": data_recarga.strftime("%Y-%m-%d %H:%M:%S"),
        "veiculo_modelo": random.choice(modelos_veiculos),
        "energia_consumida_kwh": energia_kwh,
        "tempo_utilizacao_min": random.randint(20, 120),
        "preco_kwh_brl": preco_kwh,
        "receita_gerada_brl": round(energia_kwh * preco_kwh, 2)
    })

pd.DataFrame(operacoes).to_csv(
    BRONZE_DIR / "fato_operacoes_recarga.csv", index=False
)

# 6. Ingestão bruta da Selic
# A Bronze guarda os campos exatamente como chegam da API. O tratamento e a
# mudança de nomes ficam exclusivamente no script da Silver.
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

# O arquivo da SENATRAN é uma fonte externa bruta fornecida manualmente.
caminho_senatran = BRONZE_DIR / "frota_senatran_bruta.xlsx"
if caminho_senatran.exists():
    print("- Arquivo bruto da SENATRAN localizado na Camada Bronze.")
else:
    print("- Atenção: inclua frota_senatran_bruta.xlsx na Camada Bronze.")

print("Camada Bronze gerada com sucesso.")
