import streamlit as st
import pandas as pd
import json
from datetime import datetime, timedelta
from io import BytesIO

import gspread
from google.oauth2.service_account import Credentials

# ===== CONFIG GERAL =====
st.set_page_config(page_title="Orçamentos Rep 0.1", page_icon="🧾", layout="wide")

EMPRESA = {
    "nome": "RR INOX INDUSTRIA E COMERCIO LTDA",
    "cnpj": "26.137.275/0001-65",
    "endereco": "Avenida Betania, 900 - Jardim Betania - Sorocaba/SP - CEP 18071-590",
}
STATUS_OPTS = ["orçamento enviado", "em negociação", "recusado", "aceito"]

def format_currency(v):
    try:
        return f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return v

# ===== GOOGLE SHEETS =====
@st.cache_resource(show_spinner=False)
def get_gsheets_client():
    required = ["TYPE","PROJECT_ID","PRIVATE_KEY_ID","PRIVATE_KEY","CLIENT_EMAIL","CLIENT_ID","TOKEN_URI","SHEETS_URL"]
    miss = [k for k in required if k not in st.secrets]
    if miss:
        st.error("Faltam secrets: " + ", ".join(miss))
        st.stop()
    info = {
        "type": st.secrets["TYPE"],
        "project_id": st.secrets["PROJECT_ID"],
        "private_key_id": st.secrets["PRIVATE_KEY_ID"],
        "private_key": st.secrets["PRIVATE_KEY"].replace("\\n", "\n"),
        "client_email": st.secrets["CLIENT_EMAIL"],
        "client_id": st.secrets["CLIENT_ID"],
        "token_uri": st.secrets["TOKEN_URI"],
    }
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    return gspread.authorize(creds)

def wsheets():
    gc = get_gsheets_client()
    try:
        sh = gc.open_by_url(st.secrets["SHEETS_URL"])
        ws_prod = sh.worksheet("Produtos")
        ws_crm = sh.worksheet("Orcamentos")
        return ws_prod, ws_crm
    except Exception as e:
        st.error("Erro ao abrir a planilha: %s" % e)
        st.stop()

def load_products_df():
    ws_prod, _ = wsheets()
    data = ws_prod.get_all_records()
    df = pd.DataFrame(data)
    if "ValorUnitario" in df.columns:
        df["ValorUnitario"] = pd.to_numeric(df["ValorUnitario"], errors="coerce").fillna(0.0)
    return df

def load_crm_df():
    _, ws_crm = wsheets()
    data = ws_crm.get_all_records()
    df = pd.DataFrame(data)
    cols = ["Numero","Data","Cliente","CNPJ","Telefone","Email","Endereco",
            "Total","Status","Observacoes","Condicao","ValidadeDias","ValidadeData","ItensJSON","PDF_Name"]
    for c in cols:
        if c not in df.columns: df[c] = ""
    if "Total" in df.columns:
        df["Total"] = pd.to_numeric(df["Total"], errors="coerce")
    return df[cols], ws_crm

def append_crm_row(row_dict):
    df, ws_crm = load_crm_df()
    cols = list(df.columns)
    row = [row_dict.get(c, "") for c in cols]
    ws_crm.append_row(row, value_input_option="USER_ENTERED")

def save_status_updates(updates: dict):
    df, ws_crm = load_crm_df()
    for numero, st_new in updates.items():
        df.loc[df["Numero"].astype(str) == str(numero), "Status"] = st_new
    ws_crm.clear()
    ws_crm.update([df.columns.tolist()] + df.astype(str).values.tolist())

def delete_by_numero(numero):
    df, ws_crm = load_crm_df()
    df = df[df["Numero"].astype(str) != str(numero)]
    ws_crm.clear()
    ws_crm.update([df.columns.tolist()] + df.astype(str).values.tolist())

def next_sequence(df):
    try:
        nums = df["Numero"].astype(str).str.extract(r"(\\d+)")[0].dropna().astype(int)
        nxt = (nums.max() + 1) if len(nums) else 1
    except Exception:
        nxt = 1
    return str(nxt).zfill(5)

# ===== PDF =====
def gerar_pdf(payload) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import Table, TableStyle, SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet

    styles = getSampleStyleSheet()
    buff = BytesIO()
    doc = SimpleDocTemplate(buff, pagesize=A4, rightMargin=18*mm, leftMargin=18*mm, topMargin=15*mm, bottomMargin=15*mm)
    story = []

    story.append(Paragraph(f"<b>{EMPRESA['nome']}</b>", styles["Title"]))
    story.append(Paragraph(f"CNPJ: {EMPRESA['cnpj']}", styles["Normal"]))
    story.append(Paragraph(f"Endereço: {EMPRESA['endereco']}", styles["Normal"]))
    story.append(Spacer(1, 8))
    story.append(Paragraph("<b>ORÇAMENTO</b>", styles["Heading1"]))
    story.append(Paragraph(f"Nº: {payload['numero']} &nbsp;&nbsp; Data: {payload['data']}", styles["Normal"]))

    story.append(Paragraph("<b>Cliente</b>", styles["Heading2"]))
    story.append(Paragraph(f"Nome/Razão Social: {payload['cliente_nome']}", styles["Normal"]))
    story.append(Paragraph(f"CNPJ: {payload['cliente_cnpj']}", styles["Normal"]))
    story.append(Paragraph(f"Endereço: {payload['cliente_endereco']}", styles["Normal"]))
    if payload.get("cliente_telefone"): story.append(Paragraph(f"Telefone: {payload['cliente_telefone']}", styles["Normal"]))
    if payload.get("cliente_email"): story.append(Paragraph(f"E-mail: {payload['cliente_email']}", styles["Normal"]))
    story.append(Spacer(1, 8))

    data = [["Cód.", "Produto", "Qtd", "Vlr Unit.", "Subtotal"]]
    for it in payload["itens"]:
        data.append([it.get("Codigo",""), it.get("Produto",""), str(it.get("Quantidade",0)),
                     format_currency(it.get("ValorUnitario",0)), format_currency(it.get("Subtotal",0))])
    t = Table(data, colWidths=[25*mm, 65*mm, 18*mm, 28*mm, 28*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
        ("ALIGN", (2,1), (4,-1), "RIGHT"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,0), 10),
        ("FONTSIZE", (0,1), (-1,-1), 9),
    ]))
    story.append(t)
    story.append(Spacer(1, 8))

    story.append(Paragraph(f"<b>Total:</b> {format_currency(payload['total'])}", styles["Heading2"]))

    if payload.get("observacoes"):
        story.append(Spacer(1, 8))
        story.append(Paragraph("<b>Observações</b>", styles["Heading2"]))
        story.append(Paragraph(payload["observacoes"], styles["Normal"]))

    doc.build(story)
    return buff.getvalue()

# ===== UI =====
tab1, tab2, tab3 = st.tabs(["➕ Novo Orçamento", "📋 Lista de Orçamentos", "🔎 Consulta de Produtos"])

# --- NOVO ORÇAMENTO ---
with tab1:
    st.title("Orçamentos RR Inox Indústria")
    df_prod = load_products_df()
    if df_prod.empty:
        st.stop()

    st.subheader("1) Dados do Cliente")
    col1, col2 = st.columns(2)
    with col1:
        cliente_nome = st.text_input("Nome/Razão Social")
        cliente_cnpj = st.text_input("CNPJ")
        cliente_endereco = st.text_input("Endereço")
    with col2:
        cliente_telefone = st.text_input("Telefone")
        cliente_email = st.text_input("E-mail")
        df_crm, _ = load_crm_df()
        numero_orc = st.text_input("Número do Orçamento", next_sequence(df_crm))

    st.subheader("2) Itens do Orçamento")
    if "itens_rows" not in st.session_state:
        st.session_state.itens_rows = []
        st.session_state.next_item_id = 1

    def add_item():
        first = df_prod.iloc[0]
        st.session_state.itens_rows.append({
            "id": st.session_state.next_item_id,
            "Produto": first.get("Produto",""),
            "Codigo": str(first.get("Codigo","")),
            "Quantidade": 1.0,
            "ValorUnitario": float(first.get("ValorUnitario",0.0)),
        })
        st.session_state.next_item_id += 1

    def remove_item(item_id):
        st.session_state.itens_rows = [r for r in st.session_state.itens_rows if r["id"] != item_id]

    cols_head = st.columns([4, 1.2, 1.5, 1, 0.8])
    cols_head[0].markdown("**Produto**")
    cols_head[1].markdown("**Qtd**")
    cols_head[2].markdown("**Vlr Unit.**")
    cols_head[3].markdown("**Subtotal**")
    cols_head[4].markdown("**Remover**")

    opcoes_prod = df_prod["Produto"].tolist() if "Produto" in df_prod.columns else []
    itens_payload, to_delete = [], None

    for row in st.session_state.itens_rows:
        c1, c2, c3, c4, c5 = st.columns([4, 1.2, 1.5, 1, 0.8])
        with c1:
            idx = opcoes_prod.index(row["Produto"]) if row["Produto"] in opcoes_prod else 0
            selected = st.selectbox(f"prod_{row['id']}", opcoes_prod, index=idx, label_visibility="collapsed", key=f"sb_{row['id']}")
            if selected != row["Produto"]:
                row["Produto"] = selected
                linha = df_prod.loc[df_prod["Produto"] == selected].iloc[0]
                row["Codigo"] = str(linha.get("Codigo",""))
                row["ValorUnitario"] = float(linha.get("ValorUnitario",0.0))
        with c2:
            row["Quantidade"] = st.number_input(f"Qtd_{row['id']}", min_value=0.0, step=1.0, value=float(row["Quantidade"]), label_visibility="collapsed", key=f"q_{row['id']}")
        with c3:
            row["ValorUnitario"] = st.number_input(f"VU_{row['id']}", min_value=0.0, step=0.01, value=float(row["ValorUnitario"]), label_visibility="collapsed", key=f"vu_{row['id']}")
        with c4:
            subtotal = row["Quantidade"] * row["ValorUnitario"]
            st.metric("Subtotal", format_currency(subtotal), label_visibility="collapsed")
        with c5:
            if st.button("🗑️", key=f"del_{row['id']}"):
                to_delete = row["id"]
        itens_payload.append({
            "Codigo": row.get("Codigo",""),
            "Produto": row["Produto"],
            "Quantidade": float(row["Quantidade"]),
            "ValorUnitario": float(row["ValorUnitario"]),
            "Subtotal": float(row["Quantidade"]) * float(row["ValorUnitario"]),
        })
    if to_delete is not None:
        remove_item(to_delete)
        st.experimental_rerun()

    if len(st.session_state.itens_rows) == 0:
        add_item()

    col_add = st.columns([1,4])[0]
    with col_add:
        if st.button("➕ Adicionar item"):
            add_item()

    observacoes = st.text_area("Observações")

    if st.button("📄 Gerar PDF e Salvar no CRM"):
        subtotal = sum(i["Subtotal"] for i in itens_payload)
        total = subtotal
        payload = {
            "numero": numero_orc,
            "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "cliente_nome": cliente_nome,
            "cliente_cnpj": cliente_cnpj,
            "cliente_endereco": cliente_endereco,
            "cliente_telefone": cliente_telefone,
            "cliente_email": cliente_email,
            "itens": itens_payload,
            "subtotal": subtotal,
            "total": total,
            "observacoes": observacoes,
        }
        pdf_bytes = gerar_pdf(payload)
        pdf_name = f"orcamento_{numero_orc}.pdf"

        append_crm_row({
            "Numero": numero_orc,
            "Data": payload["data"],
            "Cliente": cliente_nome,
            "CNPJ": cliente_cnpj,
            "Telefone": cliente_telefone,
            "Email": cliente_email,
            "Endereco": cliente_endereco,
            "Total": round(float(total),2),
            "Status": "orçamento enviado",
            "Observacoes": observacoes.replace("\\n"," "),
            "Condicao": "",
            "ValidadeDias": "",
            "ValidadeData": "",
            "ItensJSON": json.dumps(itens_payload, ensure_ascii=False),
            "PDF_Name": pdf_name,
        })

        st.success("Orçamento salvo no CRM.")
        st.download_button("⬇️ Baixar PDF", data=pdf_bytes, file_name=pdf_name, mime="application/pdf")

# --- LISTA ---
with tab2:
    st.title("📋 Lista de Orçamentos")
    df, _ = load_crm_df()
    if df.empty:
        st.info("Nenhum orçamento salvo ainda.")
    else:
        st.dataframe(df[["Numero","Data","Cliente","CNPJ","Telefone","Email","Total","Status"]], use_container_width=True)

# --- CONSULTA DE PRODUTOS ---
with tab3:
    st.title("🔎 Consulta de Produtos")
    dfp = load_products_df()
    if dfp.empty:
        st.info("Sem produtos.")
    else:
        st.dataframe(dfp, use_container_width=True)
