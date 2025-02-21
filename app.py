import requests
import pandas as pd
from bs4 import BeautifulSoup
import streamlit as st
from io import BytesIO

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

# Verificar se o download foi bem-sucedido
if response.status_code == 200:
    # Ler o conteúdo do arquivo como HTML
    content = response.content.decode('latin1')
    
    # Usar BeautifulSoup para processar o HTML do arquivo
    soup = BeautifulSoup(content, "html.parser")
    
    # Encontrar todas as tabelas dentro do HTML
    tables = soup.find_all("table")
    
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

        # Criar coluna de mês e ano de vencimento baseando-se no código DI1
        def converter_vencimento(di_code):
            meses = {"F": "01", "G": "02", "H": "03", "J": "04", "K": "05", "M": "06", "N": "07", "Q": "08", "U": "09", "V": "10", "X": "11", "Z": "12"}
            if len(di_code) == 3 and di_code[0] in meses:
                return f"{meses[di_code[0]]}-{2000 + int(di_code[1:])}"
            return ""

        df_tabela7.insert(1, "MÊS/ANO VENCIMENTO", df_tabela7.iloc[:, 0].apply(converter_vencimento))

        # Corrigir defasagem capturando dados da próxima coluna no HTML
        colunas_precos = ["PREÇO ABERTU.", "PREÇO MÍN.", "PREÇO MÁX.", "PREÇO MÉD.", "ÚLT. PREÇO", "AJUSTE"]
        for i, col in enumerate(colunas_precos[:-1]):  # Evitar ultrapassar limites
            if col in df_tabela7.columns and colunas_precos[i + 1] in df_tabela7.columns:
                df_tabela7[col] = df_tabela7[colunas_precos[i + 1]]

        # Selecionar apenas as colunas desejadas
        colunas_desejadas = ["DATA REFERÊNCIA", "MÊS/ANO VENCIMENTO", "CONTR. ABERT.(1)", "VOL.", "PREÇO ABERTU.", "PREÇO MÍN.", "PREÇO MÁX.", "PREÇO MÉD.", "ÚLT. PREÇO", "AJUSTE"]
        colunas_disponiveis = [col for col in colunas_desejadas if col in df_tabela7.columns]
        df_tabela7 = df_tabela7[colunas_disponiveis]

        # Adicionar coluna com a data de referência
        df_tabela7.insert(0, "DATA REFERÊNCIA", data)

        # Criar um buffer de bytes para salvar o Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_tabela7.to_excel(writer, index=False, sheet_name='Sheet1')
        
        # Criar um botão para baixar o arquivo
        st.download_button(
            label="Baixar Excel",
            data=output.getvalue(),
            file_name=f"DI_FUTURO_{data.replace('/', '-')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        # Criar um link para acessar o site e capturar evidência
        st.write(f"[Clique aqui para acessar o site e capturar evidência]({url_excel.replace('XLS=true', '')})")
    else:
        st.error("Erro: A Tabela 7 não foi encontrada no HTML extraído.")
else:
    st.error(f"Erro no download. Código: {response.status_code}")
