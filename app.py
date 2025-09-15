import requests
import pandas as pd
from bs4 import BeautifulSoup
import streamlit as st
from io import BytesIO
from datetime import datetime
# A biblioteca xlsxwriter é necessária para a formatação
# Instale com: pip install XlsxWriter

# --- Configuração da Página do Streamlit ---
st.set_page_config(page_title="Consulta DI Futuro (B3)", layout="wide")
st.title("Consulta de Dados DI Futuro (B3)")

# --- Funções Auxiliares ---

def gerar_url_excel(data_formatada, mercadoria="DI1"):
    """Gera a URL de download do 'Excel' para a data especificada."""
    base_url = "https://www2.bmf.com.br/pages/portal/bmfbovespa/boletim1/SistemaPregao_excel1.asp"
    return f"{base_url}?Data={data_formatada}&Mercadoria={mercadoria}&XLS=true"

def processar_data(data, session):
    """
    Busca, extrai e processa os dados de DI Futuro para uma única data.
    Usa pd.read_html para robustez.
    """
    data_formatada = data.strftime("%d/%m/%Y")
    url_excel = gerar_url_excel(data_formatada)

    try:
        response = session.get(url_excel, timeout=20)
        response.raise_for_status()
        
        tabelas_dfs = pd.read_html(response.content, encoding='latin1', decimal=',', thousands='.')

        if len(tabelas_dfs) < 7:
            return None, "Dados não encontrados (Tabela 7 ausente). Provavelmente um feriado ou fim de semana."

        df = tabelas_dfs[6]
        
        if len(df) < 2:
            return None, "A tabela de dados encontrada está vazia ou mal formatada."
        
        df.columns = df.iloc[1]
        df = df.iloc[2:].reset_index(drop=True)
        
        if df.iloc[-1, 0] is None or pd.isna(df.iloc[-1, 0]):
            df = df.iloc[:-1]

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
        
        # ### ALTERAÇÃO 1: Colunas "VENCIMENTO" e "PRECO AJUSTE" removidas da lista ###
        colunas_desejadas = ["DATA REFERÊNCIA", "MÊS/ANO VENCIMENTO", "CONTRATOS EM ABERTO", 
                             "VOLUME", "PRECO ABERTURA", "PRECO MINIMO", "PRECO MAXIMO", 
                             "PRECO MEDIO", "ULTIMO PRECO"]
        
        for col in colunas_desejadas:
            if col not in df.columns:
                df[col] = None
        
        df = df[colunas_desejadas]

        df['DATA REFERÊNCIA'] = pd.to_datetime(df['DATA REFERÊNCIA'], format='%d/%m/%Y')
        colunas_numericas = ['CONTRATOS EM ABERTO', 'VOLUME', 'PRECO ABERTURA', 'PRECO MINIMO', 
                             'PRECO MAXIMO', 'PRECO MEDIO', 'ULTIMO PRECO']

        for col in colunas_numericas:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        return df, "Sucesso"

    except requests.exceptions.RequestException as e:
        return None, f"Erro de conexão: {e}"
    except (IndexError, ValueError) as e:
         return None, f"Erro ao processar a tabela. Pode estar mal formatada ou vazia. Detalhe: {e}"
    except Exception as e:
        return None, f"Ocorreu um erro inesperado: {e}"

# --- Interface do Usuário ---
st.sidebar.header("Modo de Consulta")
modo_consulta = st.sidebar.radio(
    "Escolha como fornecer as datas:",
    ('Data Única', 'Importar Arquivo')
)
datas_a_processar = []

if modo_consulta == 'Data Única':
    st.sidebar.subheader("Selecione a Data")
    data_unica = st.sidebar.date_input("Data:", value=datetime.now(), format="DD/MM/YYYY")
    if data_unica: datas_a_processar = [data_unica]
else:
    st.sidebar.subheader("Selecione o Arquivo")
    uploaded_file = st.sidebar.file_uploader("Carregue (CSV, XLS, XLSX)", type=['csv', 'xls', 'xlsx'])
    st.sidebar.markdown("**Instruções:** O arquivo deve ter uma coluna chamada **`Data`**.")
    if uploaded_file:
        try:
            df_datas = pd.read_excel(uploaded_file) if not uploaded_file.name.endswith('.csv') else pd.read_csv(uploaded_file)
            col_data = next((c for c in df_datas.columns if c.lower() == 'data'), None)
            if not col_data:
                st.sidebar.error("Coluna 'Data' não encontrada.")
            else:
                datas_validas = pd.to_datetime(df_datas[col_data], errors='coerce').dropna().unique()
                datas_a_processar = sorted([d.to_pydatetime() for d in datas_validas])
                st.sidebar.success(f"Encontradas {len(datas_a_processar)} datas válidas.")
        except Exception as e:
            st.sidebar.error(f"Erro ao ler o arquivo: {e}")

# --- Botão de Processamento e Lógica Principal ---
if st.sidebar.button("Processar Dados", type="primary"):
    if not datas_a_processar:
        st.warning("Nenhuma data válida para processar.")
    else:
        dataframes_consolidados = []
        erros = []
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0"})
        st.info(f"Iniciando processamento de {len(datas_a_processar)} data(s)...")
        progress_bar = st.progress(0)
        status_text = st.empty()
        for i, data in enumerate(datas_a_processar):
            data_str = data.strftime("%d/%m/%Y")
            status_text.text(f"Processando: {data_str} ({i+1}/{len(datas_a_processar)})")
            df, status = processar_data(data, session)
            if df is not None: dataframes_consolidados.append(df)
            else:
                if "Dados não encontrados" not in status: erros.append({'data': data_str, 'motivo': status})
            progress_bar.progress((i + 1) / len(datas_a_processar))
        status_text.text("Processamento concluído!")

        st.success(f"**{len(dataframes_consolidados)}** data(s) processada(s) com sucesso.")
        if erros:
            st.warning(f"**{len(erros)}** data(s) falharam.")
            with st.expander("Ver detalhes dos erros"): st.table(erros)

        if dataframes_consolidados:
            df_final = pd.concat(dataframes_consolidados, ignore_index=True)
            st.subheader("Amostra dos Dados Consolidados")
            st.dataframe(df_final.head())

            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_final.to_excel(writer, index=False, sheet_name='DI_Futuro_Consolidado')
                
                workbook  = writer.book
                worksheet = writer.sheets['DI_Futuro_Consolidado']
                
                formato_data = workbook.add_format({'num_format': 'dd/mm/yyyy'})
                formato_numero = workbook.add_format({'num_format': '#,##0.00'})
                formato_inteiro = workbook.add_format({'num_format': '#,##0'})

                # ### ALTERAÇÃO 2: "PRECO AJUSTE" removido do dicionário de formatos ###
                formatos_colunas = {
                    'DATA REFERÊNCIA': formato_data, 'CONTRATOS EM ABERTO': formato_inteiro,
                    'VOLUME': formato_inteiro, 'PRECO ABERTURA': formato_numero,
                    'PRECO MINIMO': formato_numero, 'PRECO MAXIMO': formato_numero,
                    'PRECO MEDIO': formato_numero, 'ULTIMO PRECO': formato_numero
                }

                for col_name, formato in formatos_colunas.items():
                    if col_name in df_final.columns:
                        col_idx = df_final.columns.get_loc(col_name)
                        worksheet.set_column(col_idx, col_idx, width=15, cell_format=formato)

            nome_arquivo = f"DI_FUTURO_{datas_a_processar[0].strftime('%Y-%m-%d')}.xlsx" if len(datas_a_processar) == 1 else f"DI_FUTURO_CONSOLIDADO_{datetime.now().strftime('%Y%m%d')}.xlsx"
            st.download_button(
                label="📥 Baixar Planilha Excel Formatada",
                data=output.getvalue(),
                file_name=nome_arquivo,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.error("Nenhum dado foi extraído com sucesso.")
else:
    st.info("Selecione o modo de consulta, forneça a data ou o arquivo e clique em 'Processar Dados' na barra lateral.")

# --- Rodapé ---
st.markdown("---") 
st.markdown(
    "**Fonte dos dados:** [B3 / BMF&Bovespa - Sistema de Pregão - Resumo Estatístico](https://www2.bmf.com.br/pages/portal/bmfbovespa/boletim1/SistemaPregao1.asp)"
)
st.caption("Esta é uma ferramenta independente e não possui vínculo oficial com a B3.")
