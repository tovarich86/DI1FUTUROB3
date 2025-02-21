import requests
import pandas as pd
from bs4 import BeautifulSoup
import os
import streamlit as st

# Interface do usuário no Streamlit
st.title("Consulta DI Futuro")

data = st.date_input("Selecione a data:").strftime("%d/%m/%Y")

# Gerar a URL do Excel dinamicamente
def gerar_url_excel(data, mercadoria="DI1"):
    base_url = "https://www2.bmf.com.br/pages/portal/bmfbovespa/boletim1/SistemaPregao_excel1.asp"
    return f"{base_url}?Data={data}&Mercadoria={mercadoria}&XLS=true"

url_excel = gerar_url_excel(data)

# Criar uma sessão para manter autenticação
session = requests.Session()
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Referer": "https://www2.bmf.com.br/pages/portal/bmfbovespa/boletim1/SistemaPregao1.asp",
    "Content-Type": "application/x-www-form-urlencoded"
}

# Primeiro, acessar a página inicial para capturar cookies
session.get("https://www2.bmf.com.br/pages/portal/bmfbovespa/boletim1/SistemaPregao1.asp", headers=headers)

# Agora, baixar o arquivo
response = session.get(url_excel, headers=headers)

# Nome do arquivo salvo
downloaded_file = f"DI_FUTURO_{data.replace('/', '-')}.xlsx"

# Verificar se o download foi bem-sucedido
if response.status_code == 200:
    with open(downloaded_file, "wb") as file:
        file.write(response.content)
    print(f"Download do Excel concluído: {downloaded_file}")
    
    # Ler o conteúdo do arquivo como HTML
    with open(downloaded_file, "r", encoding="latin1", errors="ignore") as file:
        content = file.read()
    
    # Usar BeautifulSoup para processar o HTML do arquivo
    soup = BeautifulSoup(content, "html.parser")
    
    # Encontrar todas as tabelas dentro do HTML
    tables = soup.find_all("table")
    print(f"Número total de tabelas encontradas: {len(tables)}")
    
    if len(tables) >= 7:
        # Processar a Tabela 7
        tabela_mercado = tables[6]
        linhas = tabela_mercado.find_all("tr")
        dados_tabela7 = []
    
        for linha in linhas:
            colunas = linha.find_all("td")
            colunas_texto = [col.text.strip() for col in colunas]
            if colunas_texto:
                dados_tabela7.append(colunas_texto)
    
        # Ajustar colunas garantindo que todas tenham o mesmo tamanho
        max_colunas = max(len(linha) for linha in dados_tabela7)
        dados_tabela7_ajustado = [linha + [""] * (max_colunas - len(linha)) for linha in dados_tabela7]
    
        # Usar a segunda linha como cabeçalho real e remover a primeira
        cabecalhos_reais = dados_tabela7_ajustado[1]
        dados_reais = dados_tabela7_ajustado[2:]
        df_tabela7 = pd.DataFrame(dados_reais, columns=cabecalhos_reais)
    
        # Nome do arquivo final
        output_file_tabela7 = f"DI_FUTURO_{data.replace('/', '-')}.xlsx"
        df_tabela7.to_excel(output_file_tabela7, index=False, header=True)
        print(f"Arquivo Excel da Tabela 7 salvo com sucesso: {output_file_tabela7}")
        
        # Criar um botão para baixar o arquivo
        with open(output_file_tabela7, "rb") as file:
            st.download_button(label="Baixar Excel", data=file, file_name=output_file_tabela7, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        
        # Criar um link para acessar o site e capturar evidência
        st.write(f"[Clique aqui para acessar o site e capturar evidência]({url_excel.replace('XLS=true', '')})")
    else:
        print("Erro: A Tabela 7 não foi encontrada no HTML extraído.")
else:
    print(f"Erro no download. Código: {response.status_code}")
