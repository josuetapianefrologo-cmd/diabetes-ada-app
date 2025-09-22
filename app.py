# app.py — Diabetes ADA MX (PLUS/PRO) Premium
# © 2025 — Herramienta de apoyo clínico (no sustituye juicio profesional).

import os, json
import streamlit as st
import numpy as np
import pandas as pd
from io import BytesIO
from datetime import date, datetime

# PDFs
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch

# ================== Apariencia "premium" ==================
st.set_page_config(
    page_title="Diabetes ADA MX – PLUS/PRO",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      :root{
        --accent:#2563eb; --muted:#64748b; --bg:#f8fafc; --card:#ffffff;
        --good:#16a34a; --warn:#f59e0b; --bad:#dc2626;
      }
      .block-container{padding-top:2.2rem;}
      .card{background:var(--card);padding:1rem 1.1rem;border:1px solid #e5e7eb;border-radius:.8rem}
      .small{font-size:.92rem}
      hr{border:0;border-top:1px solid #e5e7eb;margin:1rem 0}
      .stDownloadButton>button{width:100%}
    </style>
    """,
    unsafe_allow_html=True,
)

# ================== Encabezado ==================
c1, c2, c3 = st.columns([1.4, 0.9, 1.0])
with c1:
    st.markdown("### 🩺 **Diabetes ADA MX**")
    st.caption("eGFR CKD-EPI 2021 · Motor de decisiones ADA · PDFs · Modo PLUS/PRO · Modo Docente")

with c2:
    modo = st.radio(
        "Modo de trabajo",
        options=["PLUS", "PRO"],
        index=0,
        horizontal=True,
        help="PRO incluye calculadora 500/1800 y exporta sus parámetros al PDF."
    )
with c3:
    docente = st.toggle("🎓 Modo docente", value=False, help="Muestra el 'por qué' y fórmulas clave.")
    st.caption("")

# ================== Utilidades base ==================
def mgdl_to_mmoll(v):
    try: return round(float(v)/18.0, 1)
    except: return None

def mmoll_to_mgdl(v):
    try: return round(float(v)*18.0, 0)
    except: return None

def to_mgdl_val(val, unidad):
    try:
        return mmoll_to_mgdl(val) if unidad == "mmol/L" else float(val)
    except:
        return None

def egfr_ckdepi_2021(scr_mgdl: float, age: int, sex: str) -> float:
    is_female = str(sex).lower().startswith(("f", "muj"))
    K = 0.7 if is_female else 0.9
    a = -0.241 if is_female else -0.302
    egfr = 142 * (min(scr_mgdl/K, 1) ** a) * (max(scr_mgdl/K, 1) ** -1.200) * (0.9938 ** age)
    if is_female: egfr *= 1.012
    return float(np.round(egfr, 1))

def bmi(kg, cm):
    try:
        m = cm/100.0
        if m <= 0: return None
        return round(kg/(m*m), 1)
    except:
        return None

def uacr_categoria(uacr_mgg):
    try: v = float(uacr_mgg)
    except: return "ND"
    if v < 30: return "A1 (<30 mg/g)"
    if v < 300: return "A2 (30-299 mg/g)"
    return "A3 (≥300 mg/g)"

# ====================== Perfiles de Pacientes (CSV local) ======================
PACIENTES_CSV = "data/pacientes.csv"
PACIENTES_COLUMNS = [
    "id","nombre","edad","sexo","dx","peso_kg","talla_cm","a1c_pct",
    "unidad_gluc","gluc_ayunas","gluc_pp",
    "creatinina_mgdl","uacr_mgg","ascvd","ic","ckd_conocida",
    "meds_json","notas","fecha_ultima_actualizacion"
]

def _ensure_pacientes_csv():
    os.makedirs(os.path.dirname(PACIENTES_CSV), exist_ok=True)
    if not os.path.exists(PACIENTES_CSV):
        pd.DataFrame(columns=PACIENTES_COLUMNS).to_csv(PACIENTES_CSV, index=False)

def cargar_pacientes() -> pd.DataFrame:
    _ensure_pacientes_csv()
    try:
        df = pd.read_csv(PACIENTES_CSV, dtype=str).fillna("")
    except Exception:
        df = pd.DataFrame(columns=PACIENTES_COLUMNS)
    if "id" in df.columns and df["id"].eq("").any():
        df.loc[df["id"].eq(""), "id"] = df.index.astype(str)
    return df

def guardar_pacientes(df: pd.DataFrame):
    _ensure_pacientes_csv()
    for col in PACIENTES_COLUMNS:
        if col not in df.columns: df[col] = ""
    df = df[PACIENTES_COLUMNS].fillna("")
    df.to_csv(PACIENTES_CSV, index=False)

def _nuevo_id(df: pd.DataFrame) -> str:
    if df.empty: return "1"
    try: mx = max(int(x) for x in df["id"] if str(x).isdigit())
    except ValueError: mx = 0
    return str(mx + 1)

def recolectar_datos_actuales() -> dict:
    return {
        "nombre": st.session_state.get("nombre", ""),
        "edad":   st.session_state.get("edad", 0),
        "sexo":   st.session_state.get("sexo", ""),
        "dx":     st.session_state.get("dx", ""),
        "peso_kg": st.session_state.get("peso", ""),
        "talla_cm": st.session_state.get("talla", ""),
        "a1c_pct": st.session_state.get("a1c", ""),
        "unidad_gluc": st.session_state.get("unidad_gluc", "mg/dL"),
        "gluc_ayunas": st.session_state.get("ay_mgdL" if st.session_state.get("unidad_gluc")=="mg/dL" else "ay_mmolL", ""),
        "gluc_pp": st.session_state.get("pp_mgdL" if st.session_state.get("unidad_gluc")=="mg/dL" else "pp_mmolL", ""),
        "creatinina_mgdl": st.session_state.get("scr", ""),
        "uacr_mgg": st.session_state.get("uacr", ""),
        "ascvd": "Sí" if st.session_state.get("ascvd", False) else "No",
        "ic":    "Sí" if st.session_state.get("ic", False) else "No",
        "ckd_conocida": "Sí" if st.session_state.get("ckd_conocida", False) else "No",
        "meds_json": json.dumps(st.session_state.get("plan_meds", {}), ensure_ascii=False),
        "notas": st.session_state.get("notas_paciente", "")
    }

def aplicar_a_widgets(p: dict):
    st.session_state["nombre"] = p.get("nombre","")
    try: st.session_state["edad"] = int(float(p.get("edad","") or 0))
    except: st.session_state["edad"] = 0
    st.session_state["sexo"] = p.get("sexo","") or "Femenino"
    st.session_state["dx"]   = p.get("dx","") or "DM2"
    try: st.session_state["peso"] = float(p.get("peso_kg","") or 0.0)
    except: st.session_state["peso"] = 0.0
    try: st.session_state["talla"] = int(float(p.get("talla_cm","") or 0))
    except: st.session_state["talla"] = 0
    try: st.session_state["a1c"] = float(p.get("a1c_pct","") or 0.0)
    except: st.session_state["a1c"] = 0.0
    st.session_state["unidad_gluc"] = p.get("unidad_gluc","mg/dL")
    # Glucosas por unidad
    try:
        if st.session_state["unidad_gluc"] == "mg/dL":
            st.session_state["ay_mgdL"] = float(p.get("gluc_ayunas","") or 0.0)
            st.session_state["pp_mgdL"] = float(p.get("gluc_pp","") or 0.0)
        else:
            st.session_state["ay_mmolL"] = float(p.get("gluc_ayunas","") or 0.0)
            st.session_state["pp_mmolL"] = float(p.get("gluc_pp","") or 0.0)
    except: pass
    try: st.session_state["scr"]  = float(p.get("creatinina_mgdl","") or 0.0)
    except: st.session_state["scr"] = 0.0
    try: st.session_state["uacr"] = float(p.get("uacr_mgg","") or 0.0)
    except: st.session_state["uacr"] = 0.0
    st.session_state["ascvd"] = (p.get("ascvd","No") == "Sí")
    st.session_state["ic"]    = (p.get("ic","No") == "Sí")
    st.session_state["ckd_conocida"] = (p.get("ckd_conocida","No") == "Sí")
    try: st.session_state["plan_meds"] = json.loads(p.get("meds_json","{}"))
    except: st.session_state["plan_meds"] = {}
    st.session_state["notas_paciente"] = p.get("notas","")

def ui_perfiles_pacientes():
    """Gestor de perfiles: requiere helpers definidos arriba."""
    st.markdown("### 👤 Perfiles de pacientes")
    df = cargar_pacientes()

    # Listado
    col_top = st.columns([2, 1])
    with col_top[0]:
        if df.empty or "id" not in df.columns:
            listado, elegido = [], None
        else:
            listado = (df["id"].astype(str) + " — " + df["nombre"].fillna("")).tolist()
            elegido = st.selectbox("Perfiles guardados", listado, index=0 if listado else None, placeholder="—")
        id_sel = elegido.split(" — ")[0] if elegido else None

    # Defaults rápidos
    def _defaults_dict():
        return {
            "unidad_gluc":"mg/dL","nombre":"","edad":55,"sexo":"Femenino","dx":"DM2",
            "peso":80.0,"talla":170,"a1c":8.2,"scr":1.0,"uacr":20.0,
            "ascvd":False,"ic":False,"ckd_conocida":False,
            "ay_mgdL":150.0,"pp_mgdL":190.0,"ay_mmolL":8.3,"pp_mmolL":10.5,
        }

    def guardar_perfil_actual():
        base = cargar_pacientes()
        datos = recolectar_datos_actuales()
        datos["fecha_ultima_actualizacion"] = datetime.utcnow().strftime("%Y-%m-%d %H:%MZ")
        if id_sel and (not base.empty) and (base["id"].astype(str) == str(id_sel)).any():
            idx = base.index[base["id"].astype(str) == str(id_sel)]
            datos["id"] = str(id_sel)
            for k in PACIENTES_COLUMNS:
                if k not in base.columns: base[k] = ""
            for k, v in datos.items():
                if k not in base.columns: base[k] = ""
                base.loc[idx, k] = str(v)
            guardar_pacientes(base)
            return f"Perfil actualizado: {datos.get('nombre','')}"
        else:
            nuevo = pd.DataFrame([{**datos, "id": _nuevo_id(base)}])
            for k in PACIENTES_COLUMNS:
                if k not in nuevo.columns: nuevo[k] = ""
            guardar_pacientes(pd.concat([base, nuevo], ignore_index=True))
            return f"Perfil creado: {datos.get('nombre','')}"

    def eliminar_perfil_actual():
        base = cargar_pacientes()
        if base.empty or not id_sel: return "No hay perfil seleccionado."
        guardar_pacientes(base[base["id"].astype(str) != str(id_sel)].copy())
        return "Perfil eliminado."

    # Botonera
    st.markdown("**Acciones rápidas**")
    bcols = st.columns([1,1,1,1], gap="small")
    with bcols[0]:
        if st.button("📂", use_container_width=True, help="Cargar perfil seleccionado", key="btn_load_profile"):
            if id_sel and not df.empty and (df["id"].astype(str) == str(id_sel)).any():
                p = df[df["id"].astype(str) == str(id_sel)].iloc[0].to_dict()
                aplicar_a_widgets(p); st.success(f"Perfil '{p.get('nombre','')}' cargado."); st.rerun()
            else:
                st.info("Elige un perfil en la lista.")
        st.caption("Cargar")

    with bcols[1]:
        if st.button("➕", use_container_width=True, help="Nuevo formulario", key="btn_new_profile"):
            for k, v in _defaults_dict().items(): st.session_state[k] = v
            st.session_state["notas_paciente"] = ""
            st.success("Formulario en blanco."); st.rerun()
        st.caption("Nuevo")

    with bcols[2]:
        if st.button("💾", use_container_width=True, help="Guardar/actualizar perfil", key="btn_save_profile"):
            st.success(guardar_perfil_actual()); st.rerun()
        st.caption("Guardar")

    with bcols[3]:
        if st.button("🗑️", use_container_width=True, help="Eliminar perfil", type="secondary", key="btn_del_profile"):
            if id_sel: st.warning(eliminar_perfil_actual()); st.rerun()
            else: st.info("Elige un perfil.")
        st.caption("Eliminar")

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Descargar CSV de perfiles**")
        buf = BytesIO(); cargar_pacientes().to_csv(buf, index=False); buf.seek(0)
        st.download_button("⬇️ Descargar `pacientes.csv`", data=buf, file_name="pacientes.csv", mime="text/csv", use_container_width=True)
    with c2:
        st.markdown("**Subir/Unir CSV**")
        f = st.file_uploader("Carga un `pacientes.csv` para unir o reemplazar", type=["csv"], label_visibility="collapsed")
        modo_up = st.radio("Modo de carga", ["Unir (merge)", "Reemplazar"], horizontal=True)
        if f and st.button("Procesar CSV", use_container_width=True, key="btn_process_csv"):
            try:
                up = pd.read_csv(f, dtype=str).fillna("")
                if modo_up.startswith("Reemplazar"):
                    guardar_pacientes(up); st.success("Archivo reemplazado."); st.rerun()
                else:
                    base = cargar_pacientes()
                    if "id" not in up.columns:
                        st.error("El CSV subido no tiene columna 'id'.")
                    else:
                        mezcla = pd.concat([base[~base["id"].astype(str).isin(up["id"].astype(str))], up], ignore_index=True)
                        guardar_pacientes(mezcla); st.success("Perfiles unidos correctamente."); st.rerun()
            except Exception as e:
                st.error(f"Error al procesar CSV: {e}")

# ================== Catálogo de fármacos (sin instituciones) ==================
CATALOGO = [
    ("Metformina","Metformina","500 mg c/12 h","1000 mg c/12 h","Subir cada 1–2 semanas si tolera GI; con comida."),
    ("SGLT2i","Empagliflozina","10 mg c/24 h","25 mg c/24 h","eGFR ≥20 para protección renal/CV; menor efecto glucémico <45."),
    ("SGLT2i","Dapagliflozina","10 mg c/24 h","10 mg c/24 h","eGFR ≥20 protección renal/CV; dosis única."),
    ("SGLT2i","Canagliflozina","100 mg c/24 h","300 mg c/24 h","Ajustar por eGFR; vigilar pie/óseo."),
    ("GLP-1 RA","Semaglutida sc semanal","0.25 mg/sem","2.0 mg/sem (DM)","Subir cada 4 semanas si tolera GI."),
    ("GLP-1 RA","Dulaglutida sc semanal","0.75 mg/sem","1.5–4.5 mg/sem","Aumentar gradual cada 4 semanas."),
    ("GLP-1 RA","Liraglutida sc diaria","0.6 mg c/24 h","1.8 mg c/24 h","Subir cada 1–2 semanas si tolera."),
    ("DPP-4","Linagliptina","5 mg c/24 h","5 mg c/24 h","Sin ajuste renal."),
    ("DPP-4","Sitagliptina","100 mg c/24 h","100 mg c/24 h","50 mg si eGFR 30–44; 25 mg si eGFR <30."),
    ("SU","Glipizida","2.5–5 mg c/24 h","20 mg/día","Preferir en CKD; menos hipo que gliburida."),
    ("TZD","Pioglitazona","15 mg c/24 h","45 mg c/24 h","Vigilar edema/IC."),
    ("Insulina basal","NPH","10 U/d","—","Titular +2 U cada 3 días hasta ayuno 80–130 mg/dL."),
    ("Insulina basal","Glargina U100","10 U/d","—","Titular +2 U cada 3 días; si >0.5 U/kg/d considerar bolo."),
    ("Insulina basal","Degludec","10 U/d","—","Similar a glargina; larga duración."),
    ("Insulina prandial","Regular","4 U/comida","—","Añadir si A1c alta con ayuno OK o basal >0.5 U/kg/d."),
    ("Insulina prandial","Aspart/Lispro","4 U/comida","—","Reglas 500/1800 o según CGM."),
]
CLASES = sorted(list({c for c,_,_,_,_ in CATALOGO}))

def alternativas_de_clase(clase, excluir=None):
    out = [d for d in CATALOGO if d[0] == clase]
    if excluir: out = [d for d in out if d[1] != excluir]
    return out

def sugerencia_para(farmaco):
    rows = [d for d in CATALOGO if d[1] == farmaco]
    if not rows: return None
    c, n, inicio, maxd, nota = rows[0]
    return f"Inicio sugerido: **{inicio}** · **Máxima:** {maxd}. {nota}"

# ================== Sidebar: datos del paciente (keys estables) ==================
with st.sidebar:
    st.header("Paciente")
    DEFAULTS = {
        "unidad_gluc":"mg/dL","nombre":"","edad":55,"sexo":"Femenino","dx":"DM2",
        "peso":80.0,"talla":170,"a1c":8.2,"scr":1.0,"uacr":20.0,
        "ascvd":False,"ic":False,"ckd_conocida":False,
    }
    for k,v in DEFAULTS.items():
        if k not in st.session_state: st.session_state[k] = v

    unidad_gluc = st.selectbox("Unidades de glucosa", ["mg/dL","mmol/L"], key="unidad_gluc")
    nombre = st.text_input("Nombre", value=st.session_state.get("nombre",""), key="nombre")
    edad = st.number_input("Edad (años)", 18, 100, st.session_state.get("edad",55), key="edad")
    sexo = st.selectbox("Sexo biológico", ["Femenino","Masculino"], key="sexo")
    dx = st.selectbox("Diagnóstico", ["DM2","DM1"], key="dx")
    peso = st.number_input("Peso (kg)", 25.0, 300.0, st.session_state.get("peso",80.0), step=0.5, key="peso")
    talla = st.number_input("Talla (cm)", 120, 230, st.session_state.get("talla",170), key="talla")
    imc_val = bmi(st.session_state["peso"], st.session_state["talla"])
    st.caption(f"IMC: **{imc_val if imc_val else 'ND'} kg/m²**")

    st.divider()
    # Glucosas: keys separadas por unidad (sin '/')
    ay_min = 2.0 if unidad_gluc == "mmol/L" else 50.0
    ay_max = 33.3 if unidad_gluc == "mmol/L" else 600.0
    pp_min = 2.0 if unidad_gluc == "mmol/L" else 50.0
    pp_maxx = 33.3 if unidad_gluc == "mmol/L" else 600.0
    ay_key = f"ay_{'mmolL' if unidad_gluc=='mmol/L' else 'mgdL'}"
    pp_key = f"pp_{'mmolL' if unidad_gluc=='mmol/L' else 'mgdL'}"
    if ay_key not in st.session_state: st.session_state[ay_key] = 8.3 if unidad_gluc=="mmol/L" else 150.0
    if pp_key not in st.session_state: st.session_state[pp_key] = 10.5 if unidad_gluc=="mmol/L" else 190.0

    gluc_ayunos = st.number_input(f"Glucosa en ayunas ({unidad_gluc})",
                                  min_value=ay_min, max_value=ay_max,
                                  value=st.session_state[ay_key], key=ay_key)
    gluc_pp_in = st.number_input(f"Glucosa 120 min ({unidad_gluc})",
                                 min_value=pp_min, max_value=pp_maxx,
                                 value=st.session_state[pp_key], key=pp_key)
    gluc_ayunas = to_mgdl_val(gluc_ayunos, unidad_gluc)
    gluc_pp = to_mgdl_val(gluc_pp_in, unidad_gluc)

    st.number_input("A1c (%)", 4.0, 15.0, st.session_state.get("a1c", 8.2), step=0.1, key="a1c")
    st.number_input("Creatinina sérica (mg/dL)", 0.2, 12.0, st.session_state.get("scr",1.0), step=0.1, key="scr")
    st.number_input("UACR (mg/g)", 0.0, 10000.0, st.session_state.get("uacr",20.0), step=1.0, key="uacr")
    uacr_cat = uacr_categoria(st.session_state["uacr"])
    ascvd = st.checkbox("ASCVD (IAM/angina/ictus/PAD)", key="ascvd")
    ic = st.checkbox("Insuficiencia cardiaca", key="ic")
    ckd_conocida = st.checkbox("CKD conocida", key="ckd_conocida")

# ===== Valores seguros antes de cálculos (evita NameError si sidebar no corrió) =====
def _ss(key, default):
    return st.session_state[key] if key in st.session_state else default

edad_i = int(float(_ss("edad", 55))) if str(_ss("edad", 55)).strip() else 55
sexo_str = str(_ss("sexo", "Femenino")) or "Femenino"
scr_f = float(_ss("scr", 1.0)) if str(_ss("scr",1.0)).strip() else 1.0

egfr = egfr_ckdepi_2021(scr_f, edad_i, sexo_str)
edad = edad_i; sexo = sexo_str; scr = scr_f  # alias locales

# ================== Metas activas (robustas) ==================
def metas_glicemicas_default(edad_int: int):
    if edad_int >= 65: return {"A1c_max": 7.5, "pre_min": 80, "pre_max": 130, "pp_max": 180}
    return {"A1c_max": 7.0, "pre_min": 80, "pre_max": 130, "pp_max": 180}

if ("metas_defaults" not in st.session_state) or (st.session_state.get("edad_for_metas") != edad):
    st.session_state["metas_defaults"] = metas_glicemicas_default(edad)
    st.session_state["edad_for_metas"] = edad
metas = st.session_state["metas_defaults"]

st.subheader("Metas activas")
a1c_meta = st.number_input(
    "A1c meta (%)", min_value=5.5, max_value=9.0,
    value=float(metas.get("A1c_max", 7.0)), step=0.1, key="a1c_meta"
)

# Límites por unidad
if unidad_gluc == "mmol/L":
    pre_min_lo, pre_min_hi = 3.5, 22.2
    pre_max_lo, pre_max_hi = 4.0, 22.2
    pp_max_lo,  pp_max_hi  = 5.5, 22.2
    pre_min_def = mgdl_to_mmoll(metas.get("pre_min",80.0))
    pre_max_def = mgdl_to_mmoll(metas.get("pre_max",130.0))
    pp_max_def  = mgdl_to_mmoll(metas.get("pp_max",180.0))
else:
    pre_min_lo, pre_min_hi = 60.0, 400.0
    pre_max_lo, pre_max_hi = 70.0, 400.0
    pp_max_lo,  pp_max_hi  = 100.0, 400.0
    pre_min_def = float(metas.get("pre_min",80.0))
    pre_max_def = float(metas.get("pre_max",130.0))
    pp_max_def  = float(metas.get("pp_max",180.0))

def _clamp(v, lo, hi):
    try: v=float(v)
    except: v=lo
    return max(lo, min(hi, v))

pre_min_def = _clamp(pre_min_def, pre_min_lo, pre_min_hi)
pre_max_def = _clamp(pre_max_def, pre_max_lo, pre_max_hi)
pp_max_def  = _clamp(pp_max_def,  pp_max_lo,  pp_max_hi)

col_m1, col_m2, col_m3 = st.columns(3)
with col_m1:
    pre_min = st.number_input(f"Preprandial mín ({unidad_gluc})",
        min_value=pre_min_lo, max_value=pre_min_hi, value=pre_min_def, step=0.1, key=f"pre_min_{unidad_gluc}")
with col_m2:
    pre_max = st.number_input(f"Preprandial máx ({unidad_gluc})",
        min_value=pre_max_lo, max_value=pre_max_hi, value=pre_max_def, step=0.1, key=f"pre_max_{unidad_gluc}")
with col_m3:
    pp_max = st.number_input(f"Posprandial máx 1–2 h ({unidad_gluc})",
        min_value=pp_max_lo, max_value=pp_max_hi, value=pp_max_def, step=0.1, key=f"pp_max_{unidad_gluc}")

st.caption(f"eGFR (CKD-EPI 2021): **{egfr} mL/min/1.73m²** · UACR: **{st.session_state['uacr']} mg/g** ({uacr_cat})")

# ================== Motor de recomendaciones y reglas de insulina ==================
def recomendacion_farmacos(tipo_dm, a1c, gl_ay, gl_pp, egfr, ckd, ascvd, ic, imc, a1c_target=7.0):
    lines, just = [], []
    if tipo_dm == "DM1":
        lines.append("DM1 → necesario esquema con **insulina basal-bolo** o sistema AID; educación y conteo CHO.")
        if docente: just.append("DM1 depende de insulina exógena – los orales no cubren déficit absoluto.")
        return lines, just
    if (a1c is not None and a1c > 10) or (gl_ay is not None and gl_ay >= 300):
        lines.append("**Iniciar/optimizar insulina** (basal ± prandial) desde el inicio.")
        if docente: just.append("A1c >10% o glucosa ≥300 mg/dL o síntomas catabólicos.")
    if ic:
        lines.append("**IC** → priorizar **SGLT2i** (beneficio en IC).")
        if docente: just.append("SGLT2i reduce hospitalización por IC.")
    if ascvd:
        lines.append("**ASCVD** → **GLP-1 RA** con beneficio CV o **SGLT2i**.")
    if imc and imc >= 30:
        lines.append("**Obesidad** → preferir **GLP-1 RA** por efecto en peso.")
    if (ckd or egfr < 60):
        if egfr >= 20:
            lines.append("**CKD** → agregar **SGLT2i** (eGFR ≥20) para protección renal/CV.")
            if docente: just.append("Menor efecto glucémico <45, pero persiste beneficio renal/CV.")
        else:
            lines.append("**CKD avanzada** (eGFR <20) → preferir **GLP-1 RA** para control glucémico.")
        if "A2" in uacr_cat or "A3" in uacr_cat:
            lines.append("**Albuminuria A2/A3** → considerar **IECA/ARA2** si procede.")
    # Metformina
    if egfr >= 45: lines.append("**Metformina** útil y segura (eGFR ≥45).")
    elif 30 <= egfr < 45: lines.append("Metformina si ya la usaba → **máx 1000 mg/d**; **evitar iniciar** en 30–44.")
    else: lines.append("**Metformina contraindicada** eGFR <30.")
    # Posprandial
    if gl_pp is not None and gl_pp > 180:
        lines.append("**Posprandial alta** → **GLP-1 RA** o añadir **bolo prandial**; revisar raciones/tiempos.")
    # Bajo riesgo global
    if not (ic or ascvd or ckd or egfr < 60) and not (
        (a1c is not None and a1c > a1c_target) and (gl_ay is not None and gl_ay > 130)
    ):
        lines.append("**Metformina** + estilos de vida; valorar **GLP-1 RA** o **SGLT2i** si no alcanza meta.")
    return lines, just

def basal_init_titration(dx, peso_kg, a1c, alto_riesgo_hipo=False):
    if dx == "DM1":
        tdd = round(0.5 * peso_kg, 1)
        basal = round(tdd * 0.5, 1); prandial = round(tdd * 0.5 / 3, 1)
        return (f"TDD≈{tdd} U/d. **Basal {basal} U/d**; **prandial {prandial} U** antes de cada comida.",
                ["Ajustar con SMBG/CGM y conteo CHO.","Vigilar hipoglucemias nocturnas."])
    base = max(10, round(0.1 * peso_kg))
    if a1c and a1c >= 9 and not alto_riesgo_hipo: base = max(base, round(0.2 * peso_kg))
    reglas = ["Titular **+2 U cada 3 días** hasta ayuno **80–130 mg/dL**.",
              "Si hipo <70 mg/dL → bajar 10–20%.",
              "Si A1c alta con ayuno controlado o basal >0.5 U/kg/d → añadir **bolo**."]
    return (f"Iniciar insulina basal en **{base} U/d** (0.1–0.2 U/kg/d).", reglas)

def intensificacion_prandial(basal_ud, peso_kg):
    umbral = round(0.5 * peso_kg, 1); inicio = max(4, int(round(basal_ud * 0.1)))
    return [f"Si basal > **{umbral} U/d** o A1c alta con ayuno OK → bolo en comida principal: **{inicio} U**.",
            "Luego 2 comidas; después 3 (**basal-bolo**).",
            "Alternativa: **GLP-1 RA** antes del bolo (peso/adhesión)."]

def ajustes_por_egfr(egfr):
    out = []
    if egfr >= 45: out.append("Metformina: **dosis plena** si tolera.")
    elif 30 <= egfr < 45: out.append("Metformina: si ya estaba, **máx 1000 mg/d**; **evitar iniciar**.")
    else: out.append("Metformina: **contraindicada** (<30).")
    if egfr >= 20: out.append("SGLT2i: indicado en T2D+CKD con eGFR ≥20 (beneficio renal/CV).")
    else: out.append("SGLT2i: evitar iniciar con eGFR <20.")
    out += ["DPP-4: **linagliptina 5 mg** sin ajuste; **sitagliptina** 50 mg (eGFR 30–44) o 25 mg (<30).",
            "GLP-1 RA: sema/dula/lira sin ajuste; **evitar exenatida** si eGFR <30.",
            "SU: preferir **glipizida**; evitar gliburida (hipo).",
            "TZD: sin ajuste renal; vigilar **edema/IC**."]
    return out

# ================== Tratamiento actual y titulación (editor) ==================
st.subheader("Tratamiento actual y titulación")
st.caption("Registra lo que usa el/la paciente para sugerir escalamiento, dosis máxima o cambio de clase.")

df_cols = ["clase","fármaco","dosis actual","frecuencia"]
ejemplo = [{"clase":"Metformina","fármaco":"Metformina","dosis actual":"850 mg","frecuencia":"c/12 h"},
           {"clase":"DPP-4","fármaco":"Linagliptina","dosis actual":"5 mg","frecuencia":"c/24 h"}]
key_data = "tabla_trat"
if key_data not in st.session_state:
    st.session_state[key_data] = pd.DataFrame(ejemplo, columns=df_cols)
base_df = st.session_state[key_data].copy()
for col in df_cols:
    if col not in base_df.columns: base_df[col] = ""
base_df = base_df[df_cols].astype(str)

cfg = {
    "clase": st.column_config.SelectboxColumn("Clase", options=CLASES, required=True, help="Clase farmacológica"),
    "fármaco": st.column_config.SelectboxColumn("Fármaco", options=[d[1] for d in CATALOGO], required=True),
    "dosis actual": st.column_config.TextColumn("Dosis actual", help="Ej. 850 mg / 10 U"),
    "frecuencia": st.column_config.TextColumn("Frecuencia", help="Ej. c/12 h, c/24 h, desayuno/cena"),
}
try:
    edit_df = st.data_editor(base_df, num_rows="dynamic", column_config=cfg, use_container_width=True, hide_index=True)
except TypeError:
    edit_df = st.data_editor(base_df, num_rows="dynamic", use_container_width=True, hide_index=True)
st.session_state[key_data] = edit_df

sug_txt = []
for _, row in edit_df.iterrows():
    tip = sugerencia_para(row["fármaco"])
    if tip: sug_txt.append(f"- {row['fármaco']}: {tip}")

if sug_txt:
    st.markdown("**Sugerencias de titulación:**")
    for t in sug_txt: st.markdown(t)

# ================== Gestor de perfiles (zona principal) ==================
st.divider()
with st.expander("👤 Perfiles de pacientes (guardar, nuevo, cargar, exportar/importar)", expanded=False):
    ui_perfiles_pacientes()

# ================== Tabs: Resumen | Plan | Catálogo | Educación ==================
tab_res, tab_plan, tab_cat, tab_edu = st.tabs(["📊 Resumen","🧭 Plan terapéutico","💊 Catálogo","📚 Educación"])

with tab_res:
    st.markdown("#### Panorama clínico")
    st.markdown(
        f"""
        <div class="card small">
        <b>eGFR:</b> {egfr} mL/min/1.73m² · <b>UACR:</b> {st.session_state['uacr']} mg/g ({uacr_cat}) ·
        <b>A1c:</b> {st.session_state.get('a1c','—')}% · <b>Ayuno:</b> {gluc_ayunos} mg/dL ·
        <b>120 min:</b> {gluc_pp} mg/dL · <b>IMC:</b> {imc_val if imc_val else 'ND'} kg/m²
        </div>
        """, unsafe_allow_html=True
    )

    recs, just = recomendacion_farmacos(
        dx, st.session_state.get('a1c'), gluc_ayunas, gluc_pp, egfr,
        st.session_state.get('ckd_conocida'), st.session_state.get('ascvd'),
        st.session_state.get('ic'), imc_val, a1c_target=a1c_meta
    )
    st.markdown("#### Recomendación terapéutica (ADA – priorización por riesgo)")
    for r in recs: st.markdown(f"- {r}")
    if docente and just:
        st.markdown("**Justificación (docente):**")
        for j in just: st.markdown(f"• {j}")

    st.markdown("#### Insulina: dosis de inicio y titulación")
    intro_basal, reglas_basal = basal_init_titration(dx, peso, st.session_state.get('a1c'), alto_riesgo_hipo=False)
    st.markdown(f"- {intro_basal}")
    for rr in reglas_basal: st.markdown(f"  - {rr}")
    if dx == "DM2":
        basal_ref = max(10, round(0.1 * peso))
        st.markdown("**Intensificación prandial (si A1c persiste alta):**")
        for p in intensificacion_prandial(basal_ud=basal_ref, peso_kg=peso): st.markdown(f"- {p}")

    st.markdown("#### Ajustes por función renal")
    for a in ajustes_por_egfr(egfr): st.markdown(f"- {a}")

    if modo == "PRO":
        st.markdown("---"); st.markdown("### PRO · Calculadora (reglas 500/1800)")
        colc1, colc2, colc3 = st.columns(3)
        with colc1:
            tdd_man = st.number_input("TDD (U/d) si ya usa insulina", 0.0, 300.0, 0.0, step=1.0, key="tdd_man")
        tdd = tdd_man if tdd_man > 0 else round((0.5 if dx=="DM1" else 0.3) * peso, 1)
        with colc2:
            icr = st.number_input("ICR (g/U) – 0 para 500/TDD", 0.0, 250.0, 0.0, step=0.5, key="icr")
        with colc3:
            cf = st.number_input("CF (mg/dL/U) – 0 para 1800/TDD", 0.0, 600.0, 0.0, step=1.0, key="cf")
        if icr == 0: icr = round(500.0 / tdd, 1) if tdd > 0 else 0.0
        if cf == 0: cf = round(1800.0 / tdd, 0) if tdd > 0 else 0.0

        colp1, colp2, colp3 = st.columns(3)
        with colp1:
            carbs = st.number_input("Carbohidratos (g)", 0.0, 300.0, 45.0, step=1.0, key="carbs")
        with colp2:
            g_act = st.number_input("Glucosa actual (mg/dL)", 40.0, 600.0, 160.0, key="gact_mgdl")
        with colp3:
            g_obj = st.number_input("Glucosa objetivo (mg/dL)", 70.0, 300.0, 110.0, key="gobj_mgdl")

        if g_act < 70:
            st.warning("Glucosa actual <70 mg/dL: tratar hipoglucemia antes de bolo."); dosis_bolo = 0.0
        else:
            dosis_bolo = max(0.0, carbs/(icr if icr>0 else 1e9) + max(0.0, (g_act-g_obj)/(cf if cf>0 else 1e9)))
            dosis_bolo = round(dosis_bolo * 2) / 2.0
        st.metric("Dosis de bolo sugerida", f"{dosis_bolo} U")
        if docente:
            st.caption("Docente: ICR≈500/TDD, CF≈1800/TDD; bolo = CHO/ICR + (Gact−Gobj)/CF. Ajustar por CGM/SMBG y actividad.")

        st.session_state["pro_block"] = {
            "tdd": tdd, "icr": icr, "cf": cf, "carbs": carbs,
            "g_act": g_act, "g_obj": g_obj, "dosis_bolo": dosis_bolo, "unidad": "mg/dL"
        }
    else:
        st.session_state["pro_block"] = None

with tab_plan:
    st.markdown("#### Plan terapéutico imprimible")
    recs_plan, just_plan = recomendacion_farmacos(
        dx, st.session_state.get('a1c'), gluc_ayunas, gluc_pp, egfr,
        st.session_state.get('ckd_conocida'), st.session_state.get('ascvd'),
        st.session_state.get('ic'), imc_val, a1c_target=a1c_meta
    )
    texto_basal, reglas_basal = basal_init_titration(dx, peso, st.session_state.get('a1c'))
    plan = recs_plan + [f"Inicio de insulina: {texto_basal}"] + reglas_basal
    if dx == "DM2": plan += intensificacion_prandial(max(10, round(0.1*peso)), peso)
    plan += ajustes_por_egfr(egfr)

    tratamiento_actual_lines = []
    for _, row in edit_df.iterrows():
        clase = str(row.get("clase","") or "—")
        farm  = str(row.get("fármaco","") or "—")
        dosis = str(row.get("dosis actual","") or "—")
        freq  = str(row.get("frecuencia","") or "—")
        tratamiento_actual_lines.append(f"{clase} · {farm}: {dosis} {freq}")

    titulacion_sugerida_lines = list(sug_txt)

    def _wraplines(c, left, y, width, text, bullet="- "):
        for seg in [text[i:i+95] for i in range(0, len(text), 95)]:
            c.drawString(left, y, f"{bullet}{seg}"); y -= 14
            if y < 72: c.showPage(); y = letter[1] - 72
        return y

    def pdf_plan(datos_paciente, tratamiento_actual, titulacion_sugerida, recomendaciones, justificacion, pro_block=None):
        buffer = BytesIO(); c = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter; left = 1*inch; y = height - 1*inch
        c.setFont("Helvetica-Bold", 12); c.drawString(left, y, "Plan terapéutico para Diabetes (ADA 2025)"); y -= 20
        c.setFont("Helvetica", 10)
        for k, v in datos_paciente.items(): y = _wraplines(c, left, y, width, f"{k}: {v}", bullet="")
        y -= 8; c.setFont("Helvetica-Bold", 11); c.drawString(left, y, "Tratamiento actual:"); y -= 16; c.setFont("Helvetica", 10)
        if not tratamiento_actual:
            y = _wraplines(c, left, y, width, "— Sin registros —")
        else:
            for line in tratamiento_actual: y = _wraplines(c, left, y, width, line)
        y -= 6; c.setFont("Helvetica-Bold", 11); c.drawString(left, y, "Sugerencias de titulación:"); y -= 16; c.setFont("Helvetica", 10)
        if not titulacion_sugerida:
            y = _wraplines(c, left, y, width, "— No hay sugerencias —", bullet="• ")
        else:
            for line in titulacion_sugerida: y = _wraplines(c, left, y, width, line, bullet="• ")
        y -= 6; c.setFont("Helvetica-Bold", 11); c.drawString(left, y, "Recomendaciones ADA:"); y -= 16; c.setFont("Helvetica", 10)
        for line in recomendaciones: y = _wraplines(c, left, y, width, line)
        y -= 6; c.setFont("Helvetica-Bold", 11); c.drawString(left, y, "Justificación clínica:"); y -= 16; c.setFont("Helvetica", 10)
        for line in justificacion: y = _wraplines(c, left, y, width, line, bullet="• ")
        if pro_block:
            y -= 6; c.setFont("Helvetica-Bold", 11); c.drawString(left, y, "Cálculos PRO (500/1800):"); y -= 16; c.setFont("Helvetica", 10)
            unidad = pro_block.get("unidad","mg/dL")
            items = [
                f"TDD usada: {pro_block.get('tdd','—')} U/d",
                f"ICR: {pro_block.get('icr','—')} g/U",
                f"CF: {pro_block.get('cf','—')} mg/dL/U",
                f"Carbohidratos: {pro_block.get('carbs','—')} g",
                f"Glucosa actual: {pro_block.get('g_act','—')} {unidad}",
                f"Objetivo: {pro_block.get('g_obj','—')} {unidad}",
                f"Dosis de bolo sugerida: {pro_block.get('dosis_bolo','—')} U"
            ]
            for line in items: y = _wraplines(c, left, y, width, line, bullet="• ")
        c.setFont("Helvetica-Oblique", 8); y -= 10
        c.drawString(left, y, "Basado en ADA Standards of Care 2025; esta hoja no sustituye el juicio clínico.")
        c.save(); buffer.seek(0); return buffer

    def pdf_registro(nombre, unidad):
        buffer = BytesIO(); c = canvas.Canvas(buffer, pagesize=letter)
        left = 0.7*inch; top = letter[1] - 0.7*inch
        c.setFont("Helvetica-Bold", 12); c.drawString(left, top, f"Registro de glucosa capilar (7 días) – Unidades: {unidad}")
        c.setFont("Helvetica", 10); c.drawString(left, top-16, f"Paciente: {nombre}    Fecha inicio: {date.today().isoformat()}")
        cols = ["Día","Ayunas","Des","Comida","Cena","2h Des","2h Com","2h Cena"]; col_w = [0.8,0.8,0.8,0.8,0.8,0.9,0.9,0.9]
        y = top - 40; c.setFont("Helvetica-Bold", 9)
        for i, h in enumerate(cols): c.drawString(left + sum(col_w[:i])*inch, y, h)
        c.setLineWidth(0.5); y -= 4; c.line(left, y, left + sum(col_w)*inch, y)
        c.setFont("Helvetica", 9)
        for d in range(1, 8):
            y -= 18; c.drawString(left, y, f"D{d}")
            for i in range(1, len(cols)): c.drawString(left + sum(col_w[:i])*inch + 4, y, "____")
            c.line(left, y-4, left + sum(col_w)*inch, y-4)
        c.save(); buffer.seek(0); return buffer

    def pdf_alta(nombre, unidad):
        buffer = BytesIO(); c = canvas.Canvas(buffer, pagesize=letter)
        left = 0.7*inch; top = letter[1] - 0.7*inch
        c.setFont("Helvetica-Bold", 12); c.drawString(left, top, "Hoja de alta y señales de alarma")
        c.setFont("Helvetica", 10); y = top - 16
        c.drawString(left, y, f"Paciente: {nombre}    Fecha: {date.today().isoformat()}    Unidades: {unidad}"); y -= 16
        secciones = [
            ("Cuidados generales", [
                "Tomar medicamentos según indicación; no suspender sin consultar.",
                "Monitorear glucosa con la frecuencia indicada; registrar valores.",
                "Hidratación, alimentación balanceada y actividad física segura."
            ]),
            ("Señales de alarma – acudir a urgencias", [
                f"Hipoglucemia severa: glucosa <70 {unidad} con síntomas o pérdida de conciencia.",
                f"Hiperglucemia persistente: >300 {unidad} repetida o síntomas de cetoacidosis.",
                "Infección grave, dolor torácico, déficit neurológico súbito, deshidratación marcada."
            ])
        ]
        for titulo, items in secciones:
            y -= 10; c.setFont("Helvetica-Bold", 11); c.drawString(left, y, titulo); y -= 14; c.setFont("Helvetica", 10)
            for it in items:
                for seg in [it[i:i+95] for i in range(0, len(it), 95)]:
                    c.drawString(left, y, f"• {seg}"); y -= 14
                    if y < 72: c.showPage(); y = letter[1] - 72
        c.save(); buffer.seek(0); return buffer

    datos = {
        "Nombre": nombre or "—",
        "Edad": f"{edad} años",
        "Sexo": sexo,
        "Diagnóstico": dx,
        "Peso/Talla/IMC": f"{peso} kg / {talla} cm / {imc_val if imc_val else 'ND'} kg/m²",
        "A1c": f"{st.session_state.get('a1c','—')} %",
        "Ayunas": f"{gluc_ayunas} mg/dL",
        "Posprandial 120 min": f"{gluc_pp} mg/dL",
        "Creatinina": f"{scr} mg/dL",
        "eGFR (CKD-EPI 2021)": f"{egfr} mL/min/1.73 m²",
        "UACR": f"{st.session_state.get('uacr','—')} mg/g ({uacr_cat})",
        "Fecha": date.today().isoformat()
    }

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("Generar PDF del plan"):
            pdf_bytes = pdf_plan(datos, tratamiento_actual_lines, titulacion_sugerida_lines, plan, just_plan, st.session_state.get("pro_block"))
            st.download_button("Descargar plan.pdf", data=pdf_bytes, file_name="plan_tratamiento_diabetes.pdf", mime="application/pdf")
    with c2:
        if st.button("Generar PDF de registro"):
            pdf_reg = pdf_registro(nombre or "—", unidad_gluc)
            st.download_button("Descargar registro.pdf", data=pdf_reg, file_name="registro_glucosa_capilar.pdf", mime="application/pdf")
    with c3:
        if st.button("Generar PDF hoja de alta"):
            pdf_ha = pdf_alta(nombre or "—", unidad_gluc)
            st.download_button("Descargar alta.pdf", data=pdf_ha, file_name="hoja_alta_diabetes.pdf", mime="application/pdf")

with tab_cat:
    st.markdown("#### Medicamentos disponibles (ADA)")
    st.caption("Catálogo sin dependencias por institución. Elige alternativas si no hay disponibilidad o hay intolerancia.")
    f_clase = st.multiselect("Filtrar por clase", CLASES, default=CLASES)
    tabla = pd.DataFrame([{"clase":c,"fármaco":n,"inicio":i,"máxima":m,"nota":nota}
                          for c,n,i,m,nota in CATALOGO if c in f_clase])
    st.dataframe(tabla, use_container_width=True, hide_index=True)

    st.markdown("#### Sugerir alternativa")
    g1, g2 = st.columns(2)
    with g1: clase_sel = st.selectbox("Clase objetivo", CLASES, index=0)
    with g2: farm_sel = st.selectbox("Si no disponible / intolerancia a", [d[1] for d in CATALOGO if d[0]==clase_sel])
    alts = alternativas_de_clase(clase_sel, excluir=farm_sel)
    if alts:
        st.markdown("**Alternativas en la misma clase:**")
        for c,n,i,m,nota in alts: st.markdown(f"- {n}: inicio **{i}**, máxima **{m}**. {nota}")
    else:
        st.info("No hay alternativas para la combinación elegida.")

with tab_edu:
    st.markdown("#### Glosario educativo: mitos y realidades")
    st.markdown("""
- **“Si empiezo insulina, ya no hay regreso.”** → Puede ser temporal o permanente según control y evolución.  
- **“El medicamento daña el riñón.”** → El mal control glucémico/HTA daña el riñón; SGLT2i **protegen**.  
- **“Si me siento bien, puedo dejar el tratamiento.”** → Puede no haber síntomas; la adherencia evita complicaciones.  
- **“Todas las sulfonilureas son iguales.”** → Diferencias de seguridad; en CKD se prefiere **glipizida**.  
- **“La metformina siempre causa daño.”** → Segura en eGFR ≥45; 30–44 dosis reducida; evitar si <30.  
""")
    st.markdown("#### Glosario de términos")
    st.markdown("""
- **TDD (Total Daily Dose)**: dosis total diaria de insulina (basal + prandial), U/día.  
- **ICR (Insulin-to-Carb Ratio)**: gramos de carbohidrato cubiertos por 1 U. Estimación: **ICR ≈ 500/TDD**.  
- **CF (Correction Factor)**: mg/dL que baja 1 U. Estimación: **CF ≈ 1800/TDD**.  
- **Conteo de carbohidratos (CHO)**: ajustar bolo según gramos de CHO ingeridos.  
""")
    st.markdown("#### ¿Cómo calcular carbohidratos para un bolo?")
    st.markdown("""
1) **Estimar CHO** del plato (etiquetas, equivalentes; 1 ración = 15 g).  
2) **Bolo CHO** = **CHO (g) / ICR (g/U)**.  
3) **Corrección** si Gact>Gobj: **(Gact − Gobj) / CF**.  
4) **Bolo total** = bolo CHO + corrección. Ajustar por actividad física y tendencia de CGM.  
5) Redondear a incrementos prácticos (0.5–1 U) según dispositivo.  
""")
    st.markdown("#### Advertencias clínicas importantes")
    st.markdown("""
- **Betabloqueadores**: pueden enmascarar síntomas adrenérgicos de hipoglucemia (temblor, taquicardia).  
- **Fluoroquinolonas**: riesgo de hipo/hiperglucemia → vigilar y ajustar.  
- **Corticosteroides**: elevan glucosa (posprandial) → puede requerir correcciones.  
- **SGLT2i**: riesgo de cetoacidosis euglucémica (ayunos, enfermedad aguda, posquirúrgico) → educar y suspender si aplica.  
- **Sulfonilureas**: mayor riesgo de hipo en adultos mayores y CKD → preferir **glipizida**, evitar **gliburida**.  
- **Insulina + GLP-1 RA**: útil para reducir A1c y peso; puede requerir bajar basal al iniciar GLP-1 RA.  
""")
    st.markdown("#### Bibliografía (enlaces)")
    st.markdown("""
- ADA **Standards of Care in Diabetes 2025** – https://professional.diabetes.org/standards-of-care  
- ADA (español – diagnóstico/educación) – https://diabetes.org/espanol/diagnostico  
- KDIGO/ADA – Diabetes y ERC – https://kdigo.org/guidelines/diabetes-ckd/  
- CKD-EPI 2021 – https://www.kidney.org/professionals/kdoqi/gfr_calculator  
""")

st.caption("© 2025. Esta app no sustituye el juicio profesional ni las guías oficiales.")
