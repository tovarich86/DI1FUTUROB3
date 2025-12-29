import streamlit as st
import pandas as pd
import polars as pl
import io
import zipfile
import requests
import urllib3
from datetime import datetime, date, timedelta
from concurrent.futures import ThreadPoolExecutor

# Configurações de Segurança e Interface
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="Consulta DI Futuro (Nativa B3)", layout="wide")

# --- 1. LÓGICA DE FERIADOS E DIAS ÚTEIS (Baseada no finbr.dias_uteis) ---

def _calc_pascoa(ano: int):
    """Algoritmo de Meeus/Jones/Butcher para data da Páscoa."""
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return date(ano, mes, dia)

def obter_feriados_b3(ano: int):
    """Lista feriados nacionais que impactam o pregão."""
    pascoa = _calc_pascoa(ano)
    feriados = [
        date(ano, 1, 1), pascoa - timedelta(days=48), pascoa - timedelta(days=47), # Ano Novo, Carnaval
        pascoa - timedelta(days=2), date(ano, 4, 21), date(ano, 5, 1),           # Sesta-Feira Santa, Tiradentes, Trabalho
        pascoa + timedelta(days=60), date(ano, 9, 7), date(ano, 10, 12),          # Corpus Christi, Independência, Aparecida
        date(ano, 11, 2), date(ano, 11, 15), date(ano, 12, 25)                   # Finados, República, Natal
    ]
    if ano >= 2024: feriados.append(date(ano, 11, 20)) # Consciência Negra
    return feriados

def eh_dia_util(data_ref):
    if data_ref.weekday() >= 5: return False
    if data_ref in obter_feriados_b3(data_ref.year): return False
    return True

# --- 2. LÓGICA DE EXTRAÇÃO E PARSING B3 (Baseada no finbr.b3.cotahist) ---

FIELD_SIZES = {
    'DATA_DO_PREGAO': 8, 'CODIGO_DE_NEGOCIACAO': 12, 'PRECO_DE_ABERTURA': 13,
    'PRECO_MAXIMO': 13, 'PRECO_MINIMO': 13, 'PRECO_MEDIO': 13, 'PRECO_ULTIMO_NEGOCIO': 13,
    'QUANTIDADE_NEGOCIADA': 18, 'VOLUME_TOTAL_NEGOCIADO': 18
}

def extrair_di_b3(data_pregao, session):
    """Baixa o ZIP da B3 e extrai apenas contratos que começam com 'DI1'."""
    if not eh_dia_util(data_pregao): return None
    
    url = f'https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_D{data_pregao.strftime("%d%m%Y")}.ZIP'
    try:
        r = session.get(url, verify=False, timeout=10)
        if r.status_code == 404: return None
        
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            with z.open(z.namelist()[0]) as f:
                content = f.read()

        # Parsing de largura fixa usando Polars para performance
        df = pl.read_csv(io.BytesIO(content), has_header=False, new_columns=['raw'], encoding='latin1', separator='|')
        
        # Filtra na string bruta para economizar processamento
        df_di = df.slice(1, -1).filter(pl.col('raw').str.slice(12, 3) == "DI1")
        
        if df_di.is_empty(): return None

        # Fatiamento das colunas (Baseado no dicionário FIELD_SIZES)
        res = df_di.with_columns([
            pl.col('raw').str.slice(2, 8).alias('DATA REFERÊNCIA'),
            pl.col('raw').str.slice(12, 12).str.strip_chars().alias('TICKER'),
            pl.col('raw').str.slice(56, 13).cast(pl.Float64).truediv(100).alias('PRECO ABERTURA'),
            pl.col('raw').str.slice(69, 13).cast(pl.Float64).truediv(100).alias('PRECO MAXIMO'),
            pl.col('raw').str.slice(82, 13).cast(pl.Float64).truediv(100).alias('PRECO MINIMO'),
            pl.col('raw').str.slice(95, 13).cast(pl.Float64).truediv(100).alias('PRECO MEDIO'),
            pl.col('raw').str.slice(108, 13).cast(pl.Float64).truediv(100).alias('ULTIMO PRECO'),
            pl.col('raw').str.slice(152, 18).cast(pl.Float64).alias('CONTRATOS NEGOCIADOS'),
            pl.col('raw').str.slice(170, 18).cast(pl.Float64).alias('VOLUME')
        ]).drop('raw')

        return res.to_pandas()
    except: return None

# --- 3. INTERFACE STREAMLIT ---

st.title("Consulta de Dados DI Futuro (Extração Direta B3)")
st.info("Este script processa arquivos oficiais COTAHIST para garantir que os dados não quebrem com mudanças no site da B3.")

with st.sidebar:
    st.header("Configurações")
    data_consulta = st.date_input("Selecione a data:", value=date(2023, 10, 20))
    botao_buscar = st.button("Buscar Dados B3", type="primary")

if botao_buscar:
    with st.spinner(f"Extraindo dados de {data_consulta}..."):
        with requests.Session() as session:
            df_final = extrair_di_b3(data_consulta, session)
            
        if df_final is not None:
            # Lógica para Mês/Ano de Vencimento (F=Jan, G=Fev, etc.)
            meses_map = {'F': '01', 'G': '02', 'H': '03', 'J': '04', 'K': '05', 'M': '06', 
                         'N': '07', 'Q': '08', 'U': '09', 'V': '10', 'X': '11', 'Z': '12'}
            
            def format_venc(ticker):
                try:
                    letra = ticker[3]
                    ano = "20" + ticker[4:]
                    return f"{meses_map[letra]}/{ano}"
                except: return ""

            df_final['MÊS/ANO VENCIMENTO'] = df_final['TICKER'].apply(format_venc)
            df_final = df_final[['DATA REFERÊNCIA', 'TICKER', 'MÊS/ANO VENCIMENTO', 'CONTRATOS NEGOCIADOS', 'VOLUME', 'PRECO ABERTURA', 'PRECO MINIMO', 'PRECO MAXIMO', 'ULTIMO PRECO']]
            
            st.success(f"Encontrados {len(df_final)} contratos negociados.")
            st.dataframe(df_final, use_container_width=True)
            
            # Download Excel
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_final.to_excel(writer, index=False, sheet_name='DI1_Futuro')
            st.download_button("📥 Baixar Planilha Excel", data=output.getvalue(), file_name=f"DI1_{data_consulta}.xlsx")
        else:
            st.error("Nenhum dado encontrado. Verifique se a data é um dia útil ou se o arquivo já foi disponibilizado pela B3.")

st.markdown("---")
st.caption("Fonte: Arquivos Históricos Oficiais da B3 (COTAHIST). Lógica de extração baseada na arquitetura da biblioteca finbr.")
