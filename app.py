import requests
import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime
import base64
import json

# --- Configuração da Página do Streamlit ---
st.set_page_config(page_title="Consulta Taxas DI (B3)", layout="wide")
st.title("Consulta de Taxas Referenciais - DI (B3)")

# --- Funções Auxiliares Adaptadas ---

def gerar_url_b3_base64(data):
    """Gera a URL da B3 com o payload em Base64."""
    # A B3 espera a data no formato YYYY-MM-DD no JSON
    data_iso = data.strftime("%Y-%m-%d")
    params = {
        "language": "pt-br",
        "date": data_iso,
        "id": "PRE"
    }
    # Codifica o JSON em Base64
    json_string = json.dumps(params, separators=(',', ':'))
    json_base64 = base64.b64encode(json_string.encode()).decode()
    
    return f"https://sistemaswebb3-derivativos.b3.com.br/referenceRatesProxy/Search/GetDownloadFile/{json_base64}"

def processar_data(data, session):
    """
    Busca, decodifica e processa os dados de Taxas DI para uma única data.
    """
    url = gerar_url_b3_base64(data)
    data_formatada = data.strftime("%d/%m/%Y")

    try:
        response = session.get(url, timeout=20)
        response.raise_for_status()
        
        # O conteúdo vem como uma string Base64 (podendo conter aspas)
        conteudo_base64 = response.text.strip()
        if conteudo_base64.startswith('"') and conteudo_base64.endswith('"'):
            conteudo_base64 = conteudo_base64[1:-1]
            
        # Decodifica o conteúdo do arquivo
        csv_bytes = base64.b64decode(conteudo_base64)
        
        # Lê o CSV (A B3 usa ';' como separador e 'latin1' como encoding)
        df = pd.read_csv(
            BytesIO(csv_bytes), 
            sep=';', 
            encoding='latin1', 
            decimal=',',
            engine='python'
        )

        if df.empty:
            return None, "Dados não encontrados ou arquivo vazio."

        # Limpeza básica nos nomes das colunas e dados
        df.columns = [col.strip() for col in df.columns]
        df.insert(0, "DATA REFERÊNCIA", data_formatada)
        
        # Renomeia colunas para facilitar o uso (opcional)
        mapa_colunas = {
            'Descrição da Taxa': 'DESCRICAO',
            'Dias Úteis': 'DIAS_UTEIS',
            'Dias Corridos': 'DIAS_CORRIDOS',
            'Preço/Taxa': 'TAXA'
        }
        df = df.rename(columns=mapa_colunas)

        return df, "Sucesso"

    except Exception as e:
        return None, f"Erro ao processar {data_formatada}: {str(e)}"

# --- Interface do Usuário (Mantida do original) ---
st.sidebar.header("Configurações")
modo_consulta = st.sidebar.radio("Modo de Consulta:", ('Data Única', 'Importar Arquivo'))

datas_a_processar = []

if modo_consulta == 'Data Única':
    data_unica = st.sidebar.date_input("Selecione a Data:", value=datetime.now())
    if data_unica: datas_a_processar = [data_unica]
else:
    uploaded_file = st.sidebar.file_uploader("Carregue um arquivo com coluna 'Data'", type=['csv', 'xlsx'])
    if uploaded_file:
        df_datas = pd.read_excel(uploaded_file) if uploaded_file.name.endswith('.xlsx') else pd.read_csv(uploaded_file)
        col_data = next((c for c in df_datas.columns if c.lower() == 'data'), None)
        if col_data:
            datas_validas = pd.to_datetime(df_datas[col_data], errors='coerce').dropna()
            datas_a_processar = sorted([d.date() for d in datas_validas])
            st.sidebar.success(f"{len(datas_a_processar)} datas encontradas.")

# --- Lógica de Processamento ---
if st.sidebar.button("Baixar Dados", type="primary"):
    if not datas_a_processar:
        st.warning("Nenhuma data selecionada.")
    else:
        lista_dfs = []
        session = requests.Session()
        
        progress_bar = st.progress(0)
        for i, data in enumerate(datas_a_processar):
            df, status = processar_data(data, session)
            if df is not None:
                lista_dfs.append(df)
            else:
                st.error(status)
            progress_bar.progress((i + 1) / len(datas_a_processar))
        
        if lista_dfs:
            df_final = pd.concat(lista_dfs, ignore_index=True)
            st.subheader("Visualização dos Dados")
            st.dataframe(df_final)

            # Preparação para download em Excel
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_final.to_excel(writer, index=False, sheet_name='Taxas_DI')
            
            st.download_button(
                label="📥 Baixar em Excel",
                data=output.getvalue(),
                file_name=f"Taxas_DI_B3_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

# --- Rodapé (Mensagem da Fonte de Dados) ---
st.markdown("---")
st.markdown(
    "**Fonte dos dados:** [B3 - Taxas Referenciais (DI)](https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/consultas/mercado-de-derivativos/taxas-referenciais/taxas-referenciais-di/)"
)
st.caption("Esta é uma ferramenta independente para consulta de dados públicos disponibilizados pela B3. Os dados são obtidos via API de Taxas Referenciais.")
