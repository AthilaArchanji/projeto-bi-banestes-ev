import pandas as pd
import requests
import os

# Criando o diretório para a Camada Silver
os.makedirs('camada_silver', exist_ok=True)

print("Iniciando o tratamento de dados (Camada Silver)...")


# 1. Tratamento: Projetos (Eletropostos)
df_projetos = pd.read_csv('camada_bronze/dim_projetos.csv')
# Garantindo que os nomes dos municípios estejam padronizados (maiúsculas) para cruzar depois
df_projetos['municipio'] = df_projetos['municipio'].str.upper()
df_projetos.to_csv('camada_silver/dim_projetos_silver.csv', index=False)
print("- dim_projetos tratada.")


# 2. Tratamento: Cotistas
df_cotistas = pd.read_csv('camada_bronze/dim_cotistas.csv')
# Convertendo string para formato de data
df_cotistas['data_entrada'] = pd.to_datetime(df_cotistas['data_entrada'])
df_cotistas.to_csv('camada_silver/dim_cotistas_silver.csv', index=False)
print("- dim_cotistas tratada.")

# 3. Tratamento: Operações de Recarga
df_operacoes = pd.read_csv('camada_bronze/fato_operacoes_recarga.csv')
df_operacoes['data_hora'] = pd.to_datetime(df_operacoes['data_hora'])
# Criando uma coluna extra apenas com a data (útil para cruzar com a Selic depois)
df_operacoes['data_referencia'] = df_operacoes['data_hora'].dt.date
df_operacoes.to_csv('camada_silver/fato_operacoes_recarga_silver.csv', index=False)
print("- fato_operacoes_recarga tratada.")

# 4. Obtenção de Dados Externos (API do Banco Central - Selic)
print("\nBuscando dados reais da Selic na API do Banco Central...")
url_bcb = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.4390/dados?formato=json"

try:
    response = requests.get(url_bcb)
    dados_selic = response.json()
    df_selic = pd.DataFrame(dados_selic)
    
    # Tratamento da base do BCB
    df_selic['data'] = pd.to_datetime(df_selic['data'], format='%d/%m/%Y')
    df_selic['valor'] = df_selic['valor'].astype(float)
    
    # Filtrando apenas dados a partir de 2023 (início do fundo)
    df_selic = df_selic[df_selic['data'] >= '2023-01-01']
    df_selic.rename(columns={'data': 'data_referencia', 'valor': 'taxa_selic_mes'}, inplace=True)
    
    df_selic.to_csv('camada_silver/ext_selic_silver.csv', index=False)
    print("- Dados da Selic importados e tratados com sucesso.")
except Exception as e:
    print(f"Erro ao buscar dados do BCB: {e}")

# 5. Tratamento de Dados Externos: SENATRAN
print("\nProcessando dados reais do SENATRAN...")
caminho_senatran = 'camada_bronze/frota_senatran_bruta.xlsx'

try:
    df_senatran_bruto = pd.read_excel(caminho_senatran)
    
    # Padronizando o nome das colunas para minúsculo
    df_senatran_bruto.columns = df_senatran_bruto.columns.str.lower().str.strip()
    
    # 1. Filtrando apenas o Espírito Santo
    df_es = df_senatran_bruto[df_senatran_bruto['uf'] == 'ES'].copy()
    
    # 2. Mapeando os combustíveis que são híbridos ou elétricos
    combustiveis_eletricos = ['ELÉTRICO', 'GASOLINA/ELÉTRICO', 'ALCOOL/GASOLINA/ELÉTRICO']
    df_es_eletricos = df_es[df_es['combustível veículo'].str.upper().isin(combustiveis_eletricos)]
    
    # 3. Agrupando por município e somando a quantidade
    df_frota_es = df_es_eletricos.groupby('município')['qtd. veículos'].sum().reset_index()
    
    # Padronizando para salvar
    df_frota_es.rename(columns={'município': 'municipio', 'qtd. veículos': 'frota_eletrica_hibrida'}, inplace=True)
    df_frota_es['municipio'] = df_frota_es['municipio'].str.upper()
    
    # Salvando o resultado final já tratado como CSV na Silver
    df_frota_es.to_csv('camada_silver/ext_senatran_es_silver.csv', index=False)
    print("- Dados de frota do SENATRAN (ES) processados com sucesso.")

except FileNotFoundError:
    print(f"⚠️ ALERTA: Arquivo '{caminho_senatran}' não encontrado.")
except Exception as e:
    print(f"⚠️ Ocorreu um erro ao processar o arquivo do SENATRAN: {e}")