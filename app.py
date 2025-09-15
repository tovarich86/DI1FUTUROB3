import requests
import pandas as pd
from bs4 import BeautifulSoup # BeautifulSoup ainda é útil para checagem inicial
import streamlit as st
from io import BytesIO
from datetime import datetime

# --- Configuração da Página do Streamlit ---
st.set_page_config(page_title="Consulta DI Futuro (B3)", layout="wide")
st.title("Consulta de Dados DI Futuro (B3)")

# --- Funções Auxiliares ---

def gerar_url_excel(data_formatada, mercadoria="DI1"):
    """Gera a URL de download do 'Excel' para a data especificada."""
    base_url = "https://www2.bmf.com.br/pages/portal/bmfbovespa/boletim1/SistemaPregao_excel1.asp"
    return f"{base_url}?Data={data_formatada}&Mercadoria={mercadoria}&XLS=true"

# ==============================================================================
# FUNÇÃO ATUALIZADA PARA SER MAIS ROBUSTA
# ==============================================================================
def processar_data(data, session):
    """
    Busca, extrai e processa os dados de DI Futuro para uma única data.
    Agora usa pd.read_html para maior robustez contra mudanças na estrutura da tabela.
    """
    data_formatada = data.strftime("%d/%m/%Y")
    url_excel = gerar_url_excel(data_formatada)

    try:
        response = session.get(url_excel, timeout=20)
        response.raise_for_status()

        # Usamos pandas para ler TODAS as tabelas da página de uma só vez.
        # Ele lida com colunas inconsistentes de forma muito mais inteligente.
        tabelas_dfs = pd.read_html(
            response.content, 
            encoding='latin1', 
            decimal=',', 
            thousands='.'
        )

        if len(tabelas_dfs) < 7:
            return None, "Dados não encontrados (Tabela 7 ausente). Provavelmente um feriado ou fim de semana."

        # A tabela de interesse ainda é a sétima (índice 6).
        df = tabelas_dfs[6]

        # Limpeza do DataFrame lido pelo pd.read_html:
        # 1. A segunda linha (índice 1) contém os nomes corretos das colunas.
        if len(df) < 2:
            return None, "A tabela de dados encontrada está vazia ou mal formatada."
        
        df.columns = df.iloc[1]
        
        # 2. Remover as duas primeiras linhas, que eram cabeçalhos.
        df = df.iloc[2:].reset_index(drop=True)
        
        # 3. Remover a última linha se for um totalizador (verificando se VENC. é nulo)
        if df.iloc[-1, 0] is None or pd.isna(df.iloc[-1, 0]):
            df = df.iloc[:-1]

        # O restante do código de transformação continua o mesmo
        df.insert(0, "DATA REFERÊNCIA", data_formatada)

        def converter_vencimento(di_code):
            meses = {"F": "01", "G": "02", "H": "03", "J": "04", "K": "05", "M": "06", 
                     "N": "07", "Q": "08", "U": "09", "V": "10", "X": "11", "Z": "12"}
            if isinstance(di_code, str) and len(di_code) == 3 and di_code[0] in meses:
                ano = 2000 + int(di_code[1:])
                return f"{meses[di_code[0]]}/{ano}"
            return ""

        # A coluna com o código de vencimento agora é a primeira do df original.
        df.insert(1, "MÊS/ANO VENCIMENTO", df.iloc[:, 1].apply(converter_vencimento))

        mapa_colunas = {
            'VENC.': 'VENCIMENTO', 'CONTR. ABERT.(1)': 'CONTRATOS EM ABERTO',
            'VOL.': 'VOLUME', 'PREÇO ABERTU.': 'PRECO ABERTURA',
            'PREÇO MÍN.': 'PRECO MINIMO', 'PREÇO MÁX.': 'PRECO MAXIMO',
            'PREÇO MÉD.': 'PRECO MEDIO', 'ÚLT. PREÇO': 'ULTIMO PRECO',
            'AJUSTE': 'PRECO AJUSTE'
        }
        df = df.rename(columns=mapa_colunas)
        
        colunas_desejadas = ["DATA REFERÊNCIA", "MÊS/ANO VENCIMENTO", "VENCIMENTO", "CONTRATOS EM ABERTO", 
                             "VOLUME", "PRECO ABERTURA", "PRECO MINIMO", "PRECO MAXIMO", 
                             "PRECO MEDIO", "ULTIMO PRECO", "PRECO AJUSTE"]
        
        for col in colunas_desejadas:
            if col not in df.columns:
                df[col] = None # Adiciona coluna se não existir
        
        return df[colunas_desejadas], "Sucesso"

    except requests.exceptions.RequestException as e:
        return None, f"Erro de conexão: {e}"
    except IndexError:
         return None, f"Erro ao processar a tabela. Pode ter menos de 7 tabelas na página."
    except ValueError as e:
        return None, f"Erro de valor ao processar a tabela, possivelmente vazia: {e}"
    except Exception as e:
        return None, f"Ocorreu um erro inesperado: {e}"

# --- Interface do Usuário (sem alterações) ---

st.sidebar.header("Modo de Consulta")
modo_consulta = st.sidebar.radio(
    "Escolha como fornecer as datas:",
    ('Data Única', 'Importar Arquivo')
)

datas_a_processar = []

if modo_consulta == 'Data Única':
    st.sidebar.subheader("Selecione a Data")
    data_unica = st.sidebar.date_input(
        "Data:",
        value=datetime.now(),
        format="DD/MM/YYYY"
    )
    if data_unica:
        datas_a_processar = [data_unica]

else: # modo_consulta == 'Importar Arquivo'
    st.sidebar.subheader("Selecione o Arquivo")
    uploaded_file = st.sidebar.file_uploader(
        "Carregue um arquivo (CSV, XLS, XLSX)",
        type=['csv', 'xls', 'xlsx']
    )
    st.sidebar.markdown("""
    **Instruções:**
    1. Crie um arquivo Excel ou CSV.
    2. Adicione uma coluna chamada **`Data`**.
    3. Preencha com as datas e salve o arquivo.
    """)
    if uploaded_file:
        try:
            if uploaded_file.name.endswith('.csv'):
                df_datas = pd.read_csv
