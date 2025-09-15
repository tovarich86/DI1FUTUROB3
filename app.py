import requests
import pandas as pd
from bs4 import BeautifulSoup
import streamlit as st
from io import BytesIO
from datetime import datetime

# --- Configuração da Página do Streamlit ---
st.set_page_config(page_title="Consulta DI Futuro (B3)", layout="wide")
st.title("Consulta de Dados DI Futuro (B3)")

# --- Funções Auxiliares (sem alterações) ---

def gerar_url_excel(data_formatada, mercadoria="DI1"):
    """Gera a URL de download do 'Excel' para a data especificada."""
    base_url = "https://www2.bmf.com.br/pages/portal/bmfbovespa/boletim1/SistemaPregao_excel1.asp"
    return f"{base_url}?Data={data_formatada}&Mercadoria={mercadoria}&XLS=true"

def processar_data(data, session):
    """
    Busca, extrai e processa os dados de DI Futuro para uma única data.
    Retorna um DataFrame com os dados ou uma tupla (None, mensagem_de_erro).
    """
    data_formatada = data.strftime("%d/%m/%Y")
    url_excel = gerar_url_excel(data_formatada)

    try:
        response = session.get(url_excel, timeout=15)
        response.raise_for_status()

        content = response.content.decode('latin1')
        soup = BeautifulSoup(content, "html.parser")
        tables = soup.find_all("table")

        if len(tables) < 7:
            return None, "Dados não encontrados (Tabela 7 ausente). Provavelmente um feriado ou fim de semana."

        tabela_mercado = tables[6]
        linhas = tabela_mercado.find_all("tr")
        
        if len(linhas) < 3:
            return None, "A tabela de dados encontrada está vazia."

        dados_tabela = [[col.text.strip() for col in linha.find_all("td")] for linha in linhas]
        dados_tabela = [linha for linha in dados_tabela if any(linha)]
        
        cabecalhos_reais = dados_tabela[1]
        dados_reais = dados_tabela[2:]
        df = pd.DataFrame(dados_reais, columns=cabecalhos_reais)

        df.insert(0, "DATA REFERÊNCIA", data_formatada)

        def converter_vencimento(di_code):
            meses = {"F": "01", "G": "02", "H": "03", "J": "04", "K": "05", "M": "06", 
                     "N": "07", "Q": "08", "U": "09", "V": "10", "X": "11", "Z": "12"}
            if isinstance(di_code, str) and len(di_code) == 3 and di_code[0] in meses:
                ano = 2000 + int(di_code[1:])
                return f"{meses[di_code[0]]}/{ano}"
            return ""

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
                df[col] = None
        
        return df[colunas_desejadas], "Sucesso"

    except requests.exceptions.RequestException as e:
        return None, f"Erro de conexão: {e}"
    except IndexError as e:
        return None, f"Erro ao analisar a estrutura da página (IndexError): {e}"
    except Exception as e:
        return None, f"Ocorreu um erro inesperado: {e}"

# --- Interface do Usuário com Seletor de Modo ---

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
                df_datas = pd.read_csv(uploaded_file)
            else:
                df_datas = pd.read_excel(uploaded_file)

            coluna_data_nome = next((col for col in df_datas.columns if col.lower() == 'data'), None)
            if not coluna_data_nome:
                st.sidebar.error("Coluna 'Data' não encontrada no arquivo.")
            else:
                datas_validas = pd.to_datetime(df_datas[coluna_data_nome], errors='coerce').dropna().unique()
                datas_a_processar = sorted([d.to_pydatetime() for d in datas_validas])
                st.sidebar.success(f"Encontradas {len(datas_a_processar)} datas únicas e válidas.")
        except Exception as e:
            st.sidebar.error(f"Erro ao ler o arquivo: {e}")

# --- Botão de Processamento e Lógica Principal ---

if st.sidebar.button("Processar Dados", type="primary"):
    if not datas_a_processar:
        st.warning("Nenhuma data válida para processar. Por favor, selecione uma data ou carregue um arquivo.")
    else:
        dataframes_consolidados = []
        erros = []
        
        session = requests.Session()
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
        session.headers.update(headers)

        st.info(f"Iniciando processamento de {len(datas_a_processar)} data(s)...")
        progress_bar = st.progress(0)
        status_text = st.empty()

        for i, data in enumerate(datas_a_processar):
            data_str = data.strftime("%d/%m/%Y")
            status_text.text(f"Processando data: {data_str} ({i+1}/{len(datas_a_processar)})")
            
            df, status = processar_data(data, session)
            
            if df is not None and not df.empty:
                dataframes_consolidados.append(df)
            else:
                if "Dados não encontrados" not in status:
                    erros.append({'data': data_str, 'motivo': status})

            progress_bar.progress((i + 1) / len(datas_a_processar))

        status_text.text("Processamento concluído!")

        # --- Exibição dos Resultados ---
        st.success(f"**{len(dataframes_consolidados)}** data(s) processada(s) com sucesso.")
        
        if erros:
            st.warning(f"**{len(erros)}** data(s) falharam.")
            with st.expander("Clique aqui para ver os detalhes dos erros"):
                st.table(erros)

        if dataframes_consolidados:
            df_final = pd.concat(dataframes_consolidados, ignore_index=True)
            
            st.subheader("Amostra dos Dados Consolidados")
            st.dataframe(df_final.head())

            # --- Botão de Download ---
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_final.to_excel(writer, index=False, sheet_name='DI_Futuro_Consolidado')
            
            # Nome do arquivo dinâmico
            if len(datas_a_processar) == 1:
                nome_arquivo = f"DI_FUTURO_{datas_a_processar[0].strftime('%Y-%m-%d')}.xlsx"
            else:
                nome_arquivo = f"DI_FUTURO_CONSOLIDADO_{datetime.now().strftime('%Y%m%d')}.xlsx"

            st.download_button(
                label="📥 Baixar Planilha Excel",
                data=output.getvalue(),
                file_name=nome_arquivo,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.error("Nenhum dado foi extraído com sucesso para a(s) data(s) informada(s).")
else:
    st.info("Selecione o modo de consulta, forneça a data ou o arquivo e clique em 'Processar Dados' na barra lateral.")
