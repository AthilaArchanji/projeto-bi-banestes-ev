import pandas as pd
import numpy as np
from faker import Faker
import random
from datetime import datetime, timedelta
import os

# Configurando o Faker para o Brasil
fake = Faker('pt_BR')

# Criando o diretório para salvar os CSVs
os.makedirs('camada_bronze', exist_ok=True)

print("Iniciando a geração de dados fake para o Fundo de Eletropostos...")

# 1. Cadastro do Fundo
fundo_data = {
    'id_fundo': [1],
    'nome_fundo': ['Banestes Infra EV ESG FII'],
    'taxa_administracao': [0.015], # 1.5% ao ano
    'benchmark': ['IPCA + 6%'],
    'data_inicio': ['2023-01-01']
}
df_fundo = pd.DataFrame(fundo_data)
df_fundo.to_csv('camada_bronze/dim_fundo.csv', index=False)

# 2. Projetos de Eletropostos (No Espírito Santo)
municipios_es = ['Vitória', 'Vila Velha', 'Serra', 'Cariacica', 'Linhares', 'Cachoeiro de Itapemirim', 'Guarapari', 'Colatina', 'Aracruz', 'São Mateus']
tipos_local = ['Shopping', 'Posto de Combustível', 'Rodovia', 'Supermercado', 'Estacionamento Privado']

projetos = []
for i in range(1, 21): # 20 projetos
    projetos.append({
        'id_projeto': i,
        'municipio': random.choice(municipios_es),
        'tipo_local': random.choice(tipos_local),
        'capex': round(random.uniform(150000, 450000), 2), # Custo de implantação
        'opex_mensal': round(random.uniform(2000, 5000), 2), # Custo operacional
        'qtd_carregadores': random.randint(2, 6),
        'potencia_instalada_kw': random.choice([50, 100, 150]),
        'status': random.choices(['Em Operação', 'Em Construção'], weights=[0.8, 0.2])[0]
    })
df_projetos = pd.DataFrame(projetos)
df_projetos.to_csv('camada_bronze/dim_projetos.csv', index=False)


# 3. Cotistas do Fundo
cotistas = []
perfis = ['Conservador', 'Moderado', 'Arrojado']
for i in range(1, 151): # 150 cotistas
    cotistas.append({
        'id_cotista': fake.unique.random_int(min=1000, max=9999),
        'perfil_risco': random.choices(perfis, weights=[0.2, 0.5, 0.3])[0],
        'municipio_origem': fake.city(),
        'data_entrada': fake.date_between(start_date='-2y', end_date='today'),
        'valor_investido': round(random.uniform(5000, 150000), 2)
    })
df_cotistas = pd.DataFrame(cotistas)
df_cotistas.to_csv('camada_bronze/dim_cotistas.csv', index=False)


# 4. Rentabilidade Mensal do Fundo 
datas_rentabilidade = pd.date_range(start='2023-01-01', end=datetime.today(), freq='ME')
rentabilidade = []
cota_atual = 100.00
pl_atual = 15000000.00 # 15 Milhões

for data in datas_rentabilidade:
    variacao = random.uniform(-0.01, 0.025) # Variação entre -1% e +2.5% ao mês
    cota_atual = cota_atual * (1 + variacao)
    pl_atual = pl_atual * (1 + variacao) + random.uniform(50000, 200000) # Simula novos aportes
    
    rentabilidade.append({
        'id_fundo': 1,
        'data_referencia': data.strftime('%Y-%m-%d'),
        'valor_cota': round(cota_atual, 2),
        'patrimonio_liquido': round(pl_atual, 2),
        'rentabilidade_mes': round(variacao, 4)
    })
df_rentabilidade = pd.DataFrame(rentabilidade)
df_rentabilidade.to_csv('camada_bronze/fato_rentabilidade.csv', index=False)

# 5. Operações de Recarga (Fato)
# Gera cerca de 5000 transações de recarga no último ano
projetos_ativos = df_projetos[df_projetos['status'] == 'Em Operação']['id_projeto'].tolist()
modelos_veiculos = ['BYD Dolphin', 'BYD Seal', 'Volvo XC40', 'GWM Ora', 'Nissan Leaf', 'Porsche Taycan', 'Renault Kwid E-Tech']

operacoes = []
data_inicio_op = datetime.now() - timedelta(days=365)

for _ in range(5000):
    data_recarga = data_inicio_op + timedelta(days=random.randint(0, 365), hours=random.randint(6, 23), minutes=random.randint(0, 59))
    energia_kwh = round(random.uniform(10, 60), 2)
    preco_kwh = 2.10 # R$ 2,10 por kWh
    
    operacoes.append({
        'id_operacao': fake.unique.uuid4(),
        'id_projeto': random.choice(projetos_ativos),
        'data_hora': data_recarga.strftime('%Y-%m-%d %H:%M:%S'),
        'veiculo_modelo': random.choice(modelos_veiculos),
        'energia_consumida_kwh': energia_kwh,
        'tempo_utilizacao_min': random.randint(20, 120),
        'receita_gerada_brl': round(energia_kwh * preco_kwh, 2)
    })
df_operacoes = pd.DataFrame(operacoes)
df_operacoes.to_csv('camada_bronze/fato_operacoes_recarga.csv', index=False)

print("✅ Dados gerados com sucesso na pasta 'camada_bronze'!")