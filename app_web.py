import streamlit as st
import pandas as pd
import json
from datetime import datetime

# ============== DADOS FIXOS DA EMPRESA ==============
EMPRESA = {
    "nome": "RR INOX INDUSTRIA E COMERCIO LTDA",
    "cnpj": "26.137.275/0001-65",
    "endereco": "Avenida Betania, 900 - Jardim Betania - Sorocaba/SP - CEP 18071-590",
}

STATUS_OPTS = ["orçamento enviado", "em negociação", "recusado", "aceito"]

st.set_page_config(page_title="Orçamentos Rep 0.1", page_icon="🧾", layout="wide")

# ================= BASE DE DADOS VIA GOOGLE SHEETS ==================
SHEETS_URL = st.secrets["SHEETS_URL"]

@st.cache_data
def carregar_produtos():
    return pd.read_excel("produtos.xlsx")

def carregar_orcamentos():
    return pd.read_csv(SHEETS_URL)

def salvar_orcamentos(df):
    df.to_csv(SHEETS_URL, index=False)

# ====================== Sequência ======================
def next_sequence(df, width=5):
    if df.empty or "Numero" not in df:
        return str(1).zfill(width)
    try:
        nums = df["Numero"].astype(int).tolist()
        nxt = max(nums) + 1
    except:
        nxt = 1
    return str(nxt).zfill(width)

# ====================== Interface ======================
st.title("🧾 Orçamentos RR Inox Indústria")

abas = st.tabs(["Novo Orçamento", "Lista de Orçamentos", "Consulta de Produtos"])

# ================== Novo Orçamento ==================
with abas[0]:
    st.header("Novo Orçamento")

    cliente_nome = st.text_input("Nome do cliente")
    cliente_cnpj = st.text_input("CNPJ")
    cliente_fone = st.text_input("Telefone")
    cliente_email = st.text_input("Email")
    cliente_endereco = st.text_area("Endereço")
    condicoes = st.text_area("Condições de pagamento")
    validade = st.number_input("Validade (dias)", value=7, min_value=1)

    produtos_df = carregar_produtos()
    itens = []
    with st.form("form_itens"):
        produto = st.selectbox("Produto", produtos_df["Produto"].tolist())
        qtd = st.number_input("Quantidade", min_value=1, value=1)
        add = st.form_submit_button("Adicionar")
        if add:
            preco = produtos_df.loc[produtos_df["Produto"] == produto, "Preço"].values[0]
            itens.append({"Produto": produto, "Qtd": qtd, "Unit": preco, "Total": qtd * preco})

    if st.button("Salvar Orçamento"):
        df_orc = carregar_orcamentos()
        numero = next_sequence(df_orc)
        total = sum(item["Total"] for item in itens)
        novo = pd.DataFrame([{
            "Numero": numero,
            "Data": datetime.now().strftime("%d/%m/%Y"),
            "Cliente": cliente_nome,
            "CNPJ": cliente_cnpj,
            "Telefone": cliente_fone,
            "Email": cliente_email,
            "Endereco": cliente_endereco,
            "Total": total,
            "Status": "orçamento enviado",
            "Condicao": condicoes,
            "Validade": validade,
            "Itens": json.dumps(itens, ensure_ascii=False)
        }])
        df_orc = pd.concat([df_orc, novo], ignore_index=True)
        salvar_orcamentos(df_orc)
        st.success(f"✅ Orçamento {numero} salvo com sucesso!")

# ================== Lista de Orçamentos ==================
with abas[1]:
    st.header("Lista de Orçamentos")
    df_orc = carregar_orcamentos()
    if df_orc.empty:
        st.info("Nenhum orçamento cadastrado ainda.")
    else:
        for i, row in df_orc.iterrows():
            with st.expander(f"📄 Orçamento {row['Numero']} - {row['Cliente']}"):
                st.write(f"**Data:** {row['Data']}")
                st.write(f"**Cliente:** {row['Cliente']}")
                st.write(f"**CNPJ:** {row['CNPJ']}")
                st.write(f"**Telefone:** {row['Telefone']}")
                st.write(f"**Email:** {row['Email']}")
                st.write(f"**Endereço:** {row['Endereco']}")
                st.write(f"**Total:** R$ {row['Total']:.2f}")
                st.write(f"**Status:** {row['Status']}")
                if st.button("🗑️ Excluir", key=f"del_{i}"):
                    df_orc = df_orc.drop(i)
                    salvar_orcamentos(df_orc)
                    st.rerun()

# ================== Consulta de Produtos ==================
with abas[2]:
    st.header("Consulta de Produtos")
    produtos_df = carregar_produtos()
    st.dataframe(produtos_df, use_container_width=True)
