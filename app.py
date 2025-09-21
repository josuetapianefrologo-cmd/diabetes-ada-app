# app.py — Diabetes ADA MX (PLUS / PRO) Premium con PDFs, Perfiles Locales y Modo Docente
# © 2025. Herramienta de apoyo clínico (no sustituye juicio profesional).

import os, json, platform
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
        --accent:#2563eb;      /* azul */
        --muted:#64748b;       /* gris */
        --bg:#f8fafc;
        --card:#ffffff;
        --good:#16a34a;
        --warn:#f59e0b;
        --bad:#dc2626;
      }
      .block-container{padding-top:2.4rem;}
      .badge{display:inline-block;padding:.20rem .55rem;border-radius:999px;font-size:.75rem;
             background:rgba(37,99,235,.10);color:#1d4ed8;border:1px solid rgba(37,99,235,.20);margin-right:.35rem}
      .muted{color:var(--muted);font-size:.9rem}
      .card{background:var(--card);padding:1rem 1.1rem;border:1px solid #e5e7eb;border-radius:.8rem}
      hr{border:0;border-top:1px solid #e5e7eb;margin:1rem 0}
      .small{font-size:.9rem}
    </style>
    """,
    unsafe_allow_html=True,
)

# ================== Encabezado ==================
left, mid, right = st.columns([1.4, 0.9, 1.0])
with left:
    st.markdown("### 🩺 **Diabetes ADA MX**")
    st.caption("eGFR CKD-EPI 2021 · Motor de decisiones ADA · PDFs · PLUS/PRO · Docente · Perfiles locales")

with mid:
    modo = st.radio(
        "Modo de trabajo",
        options=["PLUS", "PRO"],
        index=0,
        horizontal=True,
        help="PRO incluye calculadora 500/1800 y exporta parámetros al PDF."
    )

with right:
    docente = st.toggle("🎓 Modo docente", value=False, help="Muestra el 'por qué' y las fórmulas detrás de cada regla.")
    st.caption("")

# ================== Utilidades ==================
def mgdl_to_mmoll(v):
    try:
        return round(float(v) / 18.0, 1)
    except Exception:
        return None

def mmoll_to_mgdl(v):
    try:
        return round(float(v) * 18.0, 0)
    except Exception:
        return None

def to_mgdl_val(val, unidad):
    return mmoll_to_mgdl(val) if unidad == "mmol/L" else float(val)

def egfr_ckdepi_2021(scr_mgdl: float, age: int, sex: str) -> float:
    is_female = str(sex).lower().startswith(("f", "muj"))
    K = 0.7 if is_female else 0.9
    a = -0.241 if is_female else -0.302
    egfr = 142 * (min(scr_mgdl / K, 1) ** a) * (max(scr_mgdl / K, 1) ** -1.200) * (0.9938 ** age)
    if is_female:
        egfr *= 1.012
    return float(np.round(egfr, 1))

def bmi(kg, cm):
    try:
        m = cm / 100.0
        if m <= 0:
            return None
        return round(kg / (m * m), 1)
    except Exception:
        return None

def uacr_categoria(uacr_mgg):
    try:
        v = float(uacr_mgg)
    except:
        return "ND"
    if v < 30: return "A1 (<30 mg/g)"
    if v < 300: return "A2 (30-299 mg/g)"
    return "A3 (≥300 mg/g)"

def metas_glicemicas_default(edad):
    if edad >= 65:
        return {"A1c_max": 7.5, "pre_min": 80, "pre_max": 130, "pp_max": 180}
    return {"A1c_max": 7.0, "pre_min": 80, "pre_max": 130, "pp_max": 180}

# ================== Blindaje de privacidad y almacenamiento local ==================
def _sugerir_carpeta_por_defecto():
    home = os.path.expanduser("~")
    if platform.system().lower().startswith("win"):
        base = os.path.join(home, "Documents", "DiabetesADA")
    elif platform.system().lower().startswith("darwin"):
        base = os.path.join(home, "Documents", "DiabetesADA")  # macOS
    else:
        base = os.path.join(home, "DiabetesADA")               # Linux
    return base

if "local_guardado_aceptado" not in st.session_state:
    st.session_state["local_guardado_aceptado"] = False
if "local_medico_firma" not in st.session_state:
    st.session_state["local_medico_firma"] = ""
if "local_carpeta" not in st.session_state:
    st.session_state["local_carpeta"] = _sugerir_carpeta_por_defecto()

st.divider()
st.subheader("🔒 Privacidad y guardado local")

with st.container():
    st.markdown(
        """
        **Aviso de privacidad (guardado local):**  
        Los datos ingresados se guardarán **únicamente en la carpeta local** que elijas en esta computadora.
        No se enviarán a servidores externos por esta función.  
        Asegúrate de **proteger el equipo** (contraseña/sistema operativo) y, si exportas a USB, resguardar ese medio.

        Para habilitar el guardado local, escribe tu **firma (nombre del médico)** y marca **Acepto**.
        """
    )
    colp1, colp2 = st.columns([2,1])
    with colp1:
        st.session_state["local_medico_firma"] = st.text_input(
            "Firma (nombre del médico responsable)", 
            st.session_state["local_medico_firma"],
            placeholder="Dr. Nombre Apellido"
        )
    with colp2:
        aceptar = st.checkbox("Acepto", value=st.session_state["local_guardado_aceptado"])
        if st.button("Confirmar", use_container_width=True):
            st.session_state["local_guardado_aceptado"] = bool(aceptar and st.session_state["local_medico_firma"].strip())

    st.caption("Estado: " + ("✅ ACEPTADO (guardado habilitado)" if st.session_state["local_guardado_aceptado"] else "⛔ No aceptado (guardado deshabilitado)"))

    st.markdown("**Carpeta local donde se guardarán los datos:**")
    st.session_state["local_carpeta"] = st.text_input(
        "Ruta completa de la carpeta local",
        st.session_state["local_carpeta"],
        help="Ej., C:\\Usuarios\\TuNombre\\Documentos\\DiabetesADA (Windows) o /Users/TuNombre/Documents/DiabetesADA (macOS)"
    )

def _carpeta_valida(path: str) -> bool:
    try:
        if not path: 
            return False
        os.makedirs(path, exist_ok=True)
        # prueba de escritura mínima
        test_file = os.path.join(path, ".probe_write.tmp")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(test_file)
        return True
    except Exception:
        return False

def _ruta_pacientes_csv_local():
    base = st.session_state.get("local_carpeta", "").strip()
    if not base:
        return None
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "pacientes.csv")

def _ruta_metadata_local():
    base = st.session_state.get("local_carpeta", "").strip()
    if not base:
        return None
    return os.path.join(base, "metadata.json")

# ====================== Perfiles de Pacientes (CSV local repo o local PC) ======================
PACIENTES_COLUMNS = [
    "id","nombre","edad","sexo","dx","peso_kg","talla_cm","a1c_pct",
    "unidad_gluc","gluc_ayunas","gluc_pp",
    "creatinina_mgdl","uacr_mgg","ascvd","ic",
    "meds_json","notas","fecha_ultima_actualizacion"
]

def _storage_mode_and_path():
    """
    Devuelve ('local', ruta) si aceptado + carpeta válida.
    Si no, ('repo', 'data/pacientes.csv').
    """
    if st.session_state.get("local_guardado_aceptado") and st.session_state.get("local_medico_firma","").strip():
        target = _ruta_pacientes_csv_local()
        if target and _carpeta_valida(os.path.dirname(target)):
            return "local", target
    return "repo", os.path.join("data", "pacientes.csv")

def _ensure_path_for(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        pd.DataFrame(columns=PACIENTES_COLUMNS).to_csv(path, index=False)

def cargar_pacientes() -> pd.DataFrame:
    modo, path = _storage_mode_and_path()
    _ensure_path_for(path)
    try:
        df = pd.read_csv(path, dtype=str).fillna("")
    except Exception:
        df = pd.DataFrame(columns=PACIENTES_COLUMNS)
    if "id" in df.columns and df["id"].eq("").any():
        df.loc[df["id"].eq(""), "id"] = df.index.astype(str)
    return df

def guardar_pacientes(df: pd.DataFrame):
    modo, path = _storage_mode_and_path()
    _ensure_path_for(path)
    for col in PACIENTES_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df[PACIENTES_COLUMNS].fillna("")
    df.to_csv(path, index=False)
    # metadata con firma
    meta_path = _ruta_metadata_local() if modo == "local" else os.path.join("data", "metadata.json")
    try:
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "modo": modo,
                    "ruta": path,
                    "medico_firma": st.session_state.get("local_medico_firma", ""),
                    "fecha": datetime.utcnow().isoformat() + "Z",
                    "equipo": platform.node(),
                    "so": platform.platform()
                },
                f,
                ensure_ascii=False,
                indent=2
            )
    except Exception:
        pass

def recolectar_datos_actuales() -> dict:
    # Lectura usando keys dinámicas por unidad
    u = ss("unidad_gluc", "mg/dL")
    ay_key = f"ay_{u}"
    pp_key = f"pp_{u}"
    return {
        "nombre": ss("nombre", ""),
        "edad":   ss("edad", ""),
        "sexo":   ss("sexo", ""),
        "dx":     ss("dx", ""),
        "peso_kg": ss("peso", ""),
        "talla_cm": ss("talla", ""),
        "a1c_pct": ss("a1c", ""),
        "unidad_gluc": u,
        "gluc_ayunas": ss(ay_key, ""),
        "gluc_pp":     ss(pp_key, ""),
        "creatinina_mgdl": ss("scr", ""),
        "uacr_mgg": ss("uacr", ""),
        "ascvd": "Sí" if ss("ascvd", False) else "No",
        "ic":    "Sí" if ss("ic", False) else "No",
        "meds_json": json.dumps(ss("plan_meds", {}), ensure_ascii=False),
        "notas": ss("notas_paciente", "")
    }

def aplicar_a_widgets(p: dict):
    st.session_state["nombre"] = p.get("nombre","")
    st.session_state["edad"] = int(float(p["edad"])) if str(p.get("edad","")).strip() else 0
    st.session_state["sexo"] = p.get("sexo","")
    st.session_state["dx"] = p.get("dx","")
    st.session_state["peso"] = float(p["peso_kg"]) if str(p.get("peso_kg","")).strip() else 0.0
    st.session_state["talla"] = int(float(p["talla_cm"])) if str(p.get("talla_cm","")).strip() else 0
    st.session_state["a1c"] = float(p["a1c_pct"]) if str(p.get("a1c_pct","")).strip() else 0.0

    # Fija unidad y vuelve a escribir glucosas en las keys dinámicas actuales
    u = p.get("unidad_gluc","mg/dL") or "mg/dL"
    st.session_state["unidad_gluc"] = u
    ay_key = f"ay_{u}"
    pp_key = f"pp_{u}"
    try:
        st.session_state[ay_key] = float(p["gluc_ayunas"]) if str(p.get("gluc_ayunas","")).strip() else 0.0
    except Exception:
        st.session_state[ay_key] = 0.0
    try:
        st.session_state[pp_key] = float(p["gluc_pp"]) if str(p.get("gluc_pp","")).strip() else 0.0
    except Exception:
        st.session_state[pp_key] = 0.0

    st.session_state["scr"]  = float(p["creatinina_mgdl"]) if str(p.get("creatinina_mgdl","")).strip() else 0.0
    st.session_state["uacr"] = float(p["uacr_mgg"]) if str(p.get("uacr_mgg","")).strip() else 0.0
    st.session_state["ascvd"] = True if p.get("ascvd","No") == "Sí" else False
    st.session_state["ic"]    = True if p.get("ic","No") == "Sí" else False
    try:
        st.session_state["plan_meds"] = json.loads(p.get("meds_json","{}"))
    except Exception:
        st.session_state["plan_meds"] = {}
    st.session_state["notas_paciente"] = p.get("notas","")

def ui_perfiles_pacientes():
    st.markdown("### 👤 Perfiles de pacientes")
    df = cargar_pacientes()

# --- Botonera compacta (iconos) ---
    st.markdown("*Acciones rápidas*")
    bcols = st.columns([1,1,1,1], gap="small")

    with bcols[0]:
        if st.button("📂", use_container_width=True, help="Cargar perfil seleccionado", key="btn_load_profile"):
            if id_sel:
                p = df[df["id"]==id_sel].iloc[0].to_dict()
                aplicar_a_widgets(p)
                st.success(f"Perfil '{p.get('nombre','')}' cargado.")
            else:
                st.info("Elige un perfil en la lista.")
        st.caption("Cargar")

    with bcols[1]:
        if st.button("➕", use_container_width=True, help="Iniciar un nuevo formulario", key="btn_new_profile"):
            st.session_state["nombre"] = ""
            st.session_state["notas_paciente"] = ""
            st.info("Formulario en blanco.")
        st.caption("Nuevo")

    with bcols[2]:
        if st.button("💾", use_container_width=True, help="Guardar/actualizar perfil", key="btn_save_profile"):
            datos = recolectar_datos_actuales()
            ahora = datetime.utcnow().strftime("%Y-%m-%d %H:%MZ")
            datos["fecha_ultima_actualizacion"] = ahora
            if id_sel and (df["id"]==id_sel).any():
                idx = df.index[df["id"]==id_sel]
                datos["id"] = id_sel
                for k,v in datos.items():
                    df.loc[idx, k] = str(v)
                guardar_pacientes(df)
                st.success(f"Perfil actualizado: {datos['nombre']}")
            else:
                nuevo = pd.DataFrame([{**datos, "id": _nuevo_id(df)}])
                guardar_pacientes(pd.concat([df, nuevo], ignore_index=True))
                st.success(f"Perfil creado: {datos['nombre']}")
        st.caption("Guardar")

    with bcols[3]:
        if st.button("🗑️", use_container_width=True, help="Eliminar perfil seleccionado", type="secondary", key="btn_del_profile"):
            if id_sel:
                df = df[df["id"]!=id_sel].copy()
                guardar_pacientes(df)
                st.warning("Perfil eliminado.")
            else:
                st.info("Elige un perfil para eliminar.")
        st.caption("Eliminar")

    # Exportar / Importar
    st.divider()
    st.markdown("### 💾 Exportar/Importar (USB)")
    cexp, cimp = st.columns(2)
    with cexp:
        st.markdown("**Exportar a archivo (descarga)**")
        csv_bytes = cargar_pacientes().to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Descargar `pacientes.csv`",
            data=csv_bytes,
            file_name="pacientes.csv",
            mime="text/csv",
            use_container_width=True
        )
        st.caption("Guárdalo en tu **USB** o en **Mis documentos**. En otra PC podrás importarlo.")
    with cimp:
        st.markdown("**Importar desde archivo**")
        f = st.file_uploader("Selecciona un `pacientes.csv` desde USB o carpeta", type=["csv"], label_visibility="collapsed")
        modo_imp = st.radio("Modo de importación", ["Unir (merge)", "Reemplazar"], horizontal=True)
        if f and st.button("Importar CSV", use_container_width=True):
            try:
                up = pd.read_csv(f, dtype=str).fillna("")
                if "id" not in up.columns:
                    st.error("El CSV no tiene columna 'id'. No se puede importar.")
                else:
                    base = cargar_pacientes()
                    if modo_imp.startswith("Reemplazar"):
                        guardar_pacientes(up)
                        st.success("Archivo **reemplazado** correctamente.")
                    else:
                        mezcla = pd.concat([base[~base["id"].isin(up["id"])], up], ignore_index=True)
                        guardar_pacientes(mezcla)
                        st.success("Datos **unidos** correctamente.")
            except Exception as e:
                st.error(f"Error al ar: {e}")

def _nuevo_id(df: pd.DataFrame) -> str:
    if df.empty:
        return "1"
    try:
        mx = max(int(x) for x in df["id"] if str(x).isdigit())
    except ValueError:
        mx = 0
    return str(mx + 1)

# --- helper para leer del session_state sin .get() ---
def ss(key, default=None):
    return st.session_state[key] if key in st.session_state else default

# ================== Catálogo de fármacos (sin instituciones) ==================
CATALOGO = [
    # clase, nombre, inicio_sugerido, max_dosis, nota_titulacion
    ("Metformina", "Metformina", "500 mg c/12 h", "1000 mg c/12 h", "Subir cada 1–2 semanas si tolera GI; con comida."),
    ("SGLT2i", "Empagliflozina", "10 mg c/24 h", "25 mg c/24 h", "eGFR ≥20 para protección renal/CV; menor efecto glucémico <45."),
    ("SGLT2i", "Dapagliflozina", "10 mg c/24 h", "10 mg c/24 h", "eGFR ≥20 protección renal/CV; dosis única."),
    ("SGLT2i", "Canagliflozina", "100 mg c/24 h", "300 mg c/24 h", "Ajustar por eGFR; vigilar pie/óseo."),
    ("GLP-1 RA", "Semaglutida sc semanal", "0.25 mg/sem", "2.0 mg/sem (DM)", "Subir cada 4 semanas si tolera GI."),
    ("GLP-1 RA", "Dulaglutida sc semanal", "0.75 mg/sem", "1.5–4.5 mg/sem", "Aumentar gradual cada 4 semanas."),
    ("GLP-1 RA", "Liraglutida sc diaria", "0.6 mg c/24 h", "1.8 mg c/24 h", "Subir cada 1–2 semanas si tolera."),
    ("DPP-4", "Linagliptina", "5 mg c/24 h", "5 mg c/24 h", "Sin ajuste renal."),
    ("DPP-4", "Sitagliptina", "100 mg c/24 h", "100 mg c/24 h", "50 mg si eGFR 30–44; 25 mg si eGFR <30."),
    ("SU", "Glipizida", "2.5–5 mg c/24 h", "20 mg/día", "Preferir en CKD; menos hipo que gliburida."),
    ("TZD", "Pioglitazona", "15 mg c/24 h", "45 mg c/24 h", "Vigilar edema/IC."),
    ("Insulina basal", "NPH", "10 U/d", "—", "Titular +2 U cada 3 días hasta ayuno 80–130 mg/dL."),
    ("Insulina basal", "Glargina U100", "10 U/d", "—", "Titular +2 U cada 3 días; si >0.5 U/kg/d considerar bolo."),
    ("Insulina basal", "Degludec", "10 U/d", "—", "Similar a glargina; larga duración."),
    ("Insulina prandial", "Regular", "4 U/comida", "—", "Añadir si A1c alta con ayuno OK o basal >0.5 U/kg/d."),
    ("Insulina prandial", "Aspart/Lispro", "4 U/comida", "—", "Reglas 500/1800 o según CGM."),
]
CLASES = sorted(list({c for c,_,_,_,_ in CATALOGO}))

def alternativas_de_clase(clase, excluir=None):
    out = [d for d in CATALOGO if d[0] == clase]
    if excluir:
        out = [d for d in out if d[1] != excluir]
    return out

def sugerencia_para(farmaco):
    rows = [d for d in CATALOGO if d[1] == farmaco]
    if not rows:
        return None
    c, n, inicio, maxd, nota = rows[0]
    return f"Inicio sugerido: **{inicio}** · **Máxima:** {maxd}. {nota}"

# ================== Sidebar (datos del paciente) ==================
with st.sidebar:
    st.header("Paciente")
    unidad_gluc = st.selectbox("Unidades de glucosa", ["mg/dL", "mmol/L"], key="unidad_gluc")
    nombre = st.text_input("Nombre", "", key="nombre")
    edad = st.number_input("Edad (años)", 18, 100, 55, key="edad")
    sexo = st.selectbox("Sexo biológico", ["Femenino", "Masculino"], key="sexo")
    dx = st.selectbox("Diagnóstico", ["DM2", "DM1"], key="dx")
    peso = st.number_input("Peso (kg)", 25.0, 300.0, 80.0, step=0.5, key="peso")
    talla = st.number_input("Talla (cm)", 120, 230, 170, key="talla")
    imc_val = bmi(peso, talla)
    st.caption(f"IMC: **{imc_val if imc_val else 'ND'} kg/m²**")

    st.divider()
    ui_perfiles_pacientes()

    a1c = st.number_input("A1c (%)", 4.0, 15.0, 8.2, step=0.1, key="a1c")

    # Rango seguro por unidad (y keys por unidad para evitar crash)
    ay_min = 2.0 if unidad_gluc == "mmol/L" else 50.0
    ay_max = 33.3 if unidad_gluc == "mmol/L" else 600.0
    pp_min = 2.0 if unidad_gluc == "mmol/L" else 50.0
    pp_maxx = 33.3 if unidad_gluc == "mmol/L" else 600.0

    gluc_ayunos = st.number_input(
        f"Glucosa en ayunas ({unidad_gluc})", min_value=ay_min, max_value=ay_max,
        value=8.3 if unidad_gluc == "mmol/L" else 150.0,
        key=f"ay_{unidad_gluc}"
    )
    gluc_pp_in = st.number_input(
        f"Glucosa 120 min ({unidad_gluc})", min_value=pp_min, max_value=pp_maxx,
        value=10.5 if unidad_gluc == "mmol/L" else 190.0,
        key=f"pp_{unidad_gluc}"
    )
    gluc_ayunas = to_mgdl_val(gluc_ayunos, unidad_gluc)
    gluc_pp = to_mgdl_val(gluc_pp_in, unidad_gluc)

    scr = st.number_input("Creatinina sérica (mg/dL)", 0.2, 12.0, 1.0, step=0.1, key="scr")
    uacr = st.number_input("UACR (mg/g)", 0.0, 10000.0, 20.0, step=1.0, key="uacr")
    uacr_cat = uacr_categoria(uacr)
    ascvd = st.checkbox("ASCVD (IAM/angina/ictus/PAD)", key="ascvd")
    ic = st.checkbox("Insuficiencia cardiaca", key="ic")
    ckd_conocida = st.checkbox("CKD conocida", key="ckd_conocida")

# ================== Cálculos básicos ==================
egfr = egfr_ckdepi_2021(scr, int(edad), sexo)
modo_store, ruta_store = _storage_mode_and_path()
st.caption(f"🗂️ Almacenamiento: **{ 'LOCAL' if modo_store=='local' else 'REPO' }** → {ruta_store}")
if modo_store == "local":
    st.caption(f"👤 Firma: **{st.session_state.get('local_medico_firma','—')}**  ·  Equipo: {platform.node()}")

# ================== Metas con protección de keys ==================
def _clamp(v: float, lo: float, hi: float, ndigits: int = 1) -> float:
    """Asegura que v quede entre lo..hi y lo redondea para que number_input no truene."""
    try:
        v = float(v)
    except Exception:
        v = lo
    v = max(lo, min(hi, v))
    return round(v, ndigits)

st.subheader("Metas activas")
alc_meta = st.number_input(
    "A1c meta (%)",
    min_value=5.5, max_value=9.0,
    value=float(metas["A1c_max"]),
    step=0.1,
    key="a1c_meta",
)

# Límites por unidad (todos floats)
if unidad_gluc == "mmol/L":
    pre_min_lo, pre_min_hi = 3.5, 22.2
    pre_max_lo, pre_max_hi = 4.0, 22.2
    pp_max_lo,  pp_max_hi  = 5.5, 22.2

    pre_min_def = mgdl_to_mmoll(metas["pre_min"])
    pre_max_def = mgdl_to_mmoll(metas["pre_max"])
    pp_max_def  = mgdl_to_mmoll(metas["pp_max"])
else:
    pre_min_lo, pre_min_hi = 60.0, 400.0
    pre_max_lo, pre_max_hi = 70.0, 400.0
    pp_max_lo,  pp_max_hi  = 100.0, 400.0

    pre_min_def = float(metas["pre_min"])
    pre_max_def = float(metas["pre_max"])
    pp_max_def  = float(metas["pp_max"])

# Asegurar que los valores por defecto estén SIEMPRE dentro del rango
pre_min_def = _clamp(pre_min_def, pre_min_lo, pre_min_hi)
pre_max_def = _clamp(pre_max_def, pre_max_lo, pre_max_hi)
pp_max_def  = _clamp(pp_max_def,  pp_max_lo,  pp_max_hi)

c1, c2, c3 = st.columns(3)
with c1:
    pre_min = st.number_input(
        f"Preprandial mín ({unidad_gluc})",
        min_value=pre_min_lo, max_value=pre_min_hi,
        value=pre_min_def, step=0.1,
        key=f"pre_min:{unidad_gluc}"   # <- key único por unidad
    )
with c2:
    pre_max = st.number_input(
        f"Preprandial máx ({unidad_gluc})",
        min_value=pre_max_lo, max_value=pre_max_hi,
        value=pre_max_def, step=0.1,
        key=f"pre_max:{unidad_gluc}"
    )
with c3:
    pp_max = st.number_input(
        f"Posprandial máx 1–2 h ({unidad_gluc})",
        min_value=pp_max_lo, max_value=pp_max_hi,
        value=pp_max_def, step=0.1,
        key=f"pp_max:{unidad_gluc}"
    )

# ================== Motor de recomendaciones ==================
def recomendacion_farmacos(tipo_dm, a1c, gl_ay, gl_pp, egfr, ckd, ascvd, ic, imc):
    lines, just = [], []
    if tipo_dm == "DM1":
        lines.append("DM1 → necesario esquema con **insulina basal-bolo** o sistema AID; educación y conteo de carbohidratos.")
        if docente:
            just.append("DM1 depende de insulina exógena – los orales no cubren el déficit absoluto.")
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
            lines.append("**CKD** → agregar **SGLT2i** para protección renal/CV (eGFR ≥20).")
            if docente: just.append("Eficacia hipoglucemiante menor si eGFR <45, pero beneficio renal/CV persiste.")
        else:
            lines.append("**CKD avanzada** (eGFR <20) → preferir **GLP-1 RA** para control glucémico.")
        if "A2" in uacr_cat or "A3" in uacr_cat:
            lines.append("**Albuminuria A2/A3** → IECA/ARA2 si procede.")
    if egfr >= 45:
        lines.append("**Metformina** útil y segura (eGFR ≥45).")
    elif 30 <= egfr < 45:
        lines.append("Metformina si ya la usaba → **máx 1000 mg/d**; **evitar iniciar** en 30–44.")
    else:
        lines.append("**Metformina contraindicada** eGFR <30.")
    # Posprandial
    umbral_pp = pp_max if unidad_gluc == "mg/dL" else mmoll_to_mgdl(pp_max)
    if gl_pp and gl_pp > umbral_pp:
        lines.append("**Posprandial alta** → GLP-1 RA o añadir **bolo prandial**; revisar raciones/tiempos.")
    # Si bajo riesgo global
    if not (ic or ascvd or ckd or egfr < 60) and not ((a1c and a1c > a1c_meta) and (gl_ay and gl_ay > 130)):
        lines.append("**Metformina** + estilo de vida; valorar **GLP-1 RA** o **SGLT2i** si no se alcanza meta.")
    return lines, just

def basal_init_titration(dx, peso_kg, a1c, alto_riesgo_hipo=False):
    if dx == "DM1":
        tdd = round(0.5 * peso_kg, 1)
        basal = round(tdd * 0.5, 1)
        prandial = round(tdd * 0.5 / 3, 1)
        return (f"TDD≈{tdd} U/d. **Basal {basal} U/d**; **prandial {prandial} U** antes de cada comida.",
                ["Ajustar con SMBG/CGM y conteo CHO.", "Vigilar hipoglucemias nocturnas."])
    base = max(10, round(0.1 * peso_kg))
    if a1c and a1c >= 9 and not alto_riesgo_hipo:
        base = max(base, round(0.2 * peso_kg))
    reglas = [
        "Titular **+2 U cada 3 días** hasta ayuno **80–130 mg/dL**.",
        "Si hipo <70 mg/dL → bajar 10–20%.",
        "Si A1c alta con ayuno controlado **o** basal >0.5 U/kg/d → añadir **bolo**."
    ]
    return (f"Iniciar insulina basal en **{base} U/d** (0.1–0.2 U/kg/d).", reglas)

def intensificacion_prandial(basal_ud, peso_kg):
    umbral = round(0.5 * peso_kg, 1)
    inicio = max(4, int(round(basal_ud * 0.1)))
    return [
        f"Si basal > **{umbral} U/d** o A1c alta con ayuno OK → bolo en comida principal: **{inicio} U**.",
        "Luego 2 comidas; después 3 (**basal-bolo**).",
        "Alternativa: **GLP-1 RA** antes del bolo (peso/adhesión)."
    ]

def ajustes_por_egfr(egfr):
    out = []
    if egfr >= 45: out.append("Metformina: **dosis plena** si tolera.")
    elif 30 <= egfr < 45: out.append("Metformina: si ya estaba, **máx 1000 mg/d**; **evitar iniciar**.")
    else: out.append("Metformina: **contraindicada** (<30).")
    if egfr >= 20: out.append("SGLT2i: indicado en T2D+CKD con eGFR ≥20 (beneficio renal/CV).")
    else: out.append("SGLT2i: evitar iniciar con eGFR <20.")
    out += [
        "DPP-4: **linagliptina 5 mg** sin ajuste; **sitagliptina** 50 mg (eGFR 30–44) o 25 mg (<30).",
        "GLP-1 RA: sema/dula/lira sin ajuste; **evitar exenatida** si eGFR <30.",
        "SU: preferir **glipizida**; evitar gliburida (hipo).",
        "TZD: sin ajuste renal; vigilar **edema/IC**."
    ]
    return out

# ================== Tratamiento actual y titulación ==================
st.subheader("Tratamiento actual y titulación")
st.caption("Registra lo que usa el/la paciente para sugerir escalamiento, dosis máxima o cambio de clase.")

df_cols = ["clase", "fármaco", "dosis actual", "frecuencia"]
ejemplo = [
    {"clase":"Metformina", "fármaco":"Metformina", "dosis actual":"850 mg", "frecuencia":"c/12 h"},
    {"clase":"DPP-4", "fármaco":"Linagliptina", "dosis actual":"5 mg", "frecuencia":"c/24 h"},
]
key_data = "tabla_trat"
if key_data not in st.session_state:
    st.session_state[key_data] = pd.DataFrame(ejemplo, columns=df_cols)

edit_df = st.data_editor(
    st.session_state[key_data],
    num_rows="dynamic",
    columns={
        "clase": st.column_config.SelectboxColumn(options=CLASES, required=True),
        "fármaco": st.column_config.SelectboxColumn(options=[d[1] for d in CATALOGO], required=True),
        "dosis actual": st.column_config.TextColumn(help="Ej. 850 mg / 10 U"),
        "frecuencia": st.column_config.TextColumn(help="Ej. c/12 h, c/24 h, desayuno/cena")
    },
    use_container_width=True,
    hide_index=True
)
st.session_state[key_data] = edit_df

sug_txt = []
for _, row in edit_df.iterrows():
    tip = sugerencia_para(row["fármaco"])
    if tip:
        sug_txt.append(f"- {row['fármaco']}: {tip}")

if sug_txt:
    st.markdown("**Sugerencias de titulación:**")
    for t in sug_txt:
        st.markdown(t)

# ================== Tabs principales ==================
tab_res, tab_plan, tab_cat, tab_edu = st.tabs(["📊 Resumen", "🧭 Plan terapéutico", "💊 Catálogo", "📚 Educación"])

# --------- RESUMEN ----------
with tab_res:
    st.markdown("#### Panorama clínico")
    st.markdown(
        f"""
        <div class="card small">
        <b>eGFR:</b> {egfr} mL/min/1.73m² · <b>UACR:</b> {uacr} mg/g ({uacr_cat}) · 
        <b>A1c:</b> {a1c}% · <b>Ayuno:</b> {gluc_ayunos} {unidad_gluc} · 
        <b>120 min:</b> {gluc_pp_in} {unidad_gluc} · <b>IMC:</b> {imc_val if imc_val else 'ND'} kg/m²
        </div>
        """, unsafe_allow_html=True
    )

    recs, just = recomendacion_farmacos(dx, a1c, gluc_ayunas, gluc_pp, egfr, ckd_conocida, ascvd, ic, imc_val)
    st.markdown("#### Recomendación terapéutica (ADA – priorización por riesgo)")
    for r in recs:
        st.markdown(f"- {r}")
    if docente and just:
        st.markdown("**Justificación (docente):**")
        for j in just:
            st.markdown(f"• {j}")

    st.markdown("#### Insulina: dosis de inicio y titulación")
    intro_basal, reglas_basal = basal_init_titration(dx, peso, a1c, alto_riesgo_hipo=False)
    st.markdown(f"- {intro_basal}")
    for rr in reglas_basal:
        st.markdown(f"  - {rr}")

    if dx == "DM2":
        basal_ref = max(10, round(0.1 * peso))
        st.markdown("**Intensificación prandial (si A1c persiste alta):**")
        for p in intensificacion_prandial(basal_ud=basal_ref, peso_kg=peso):
            st.markdown(f"- {p}")

    st.markdown("#### Ajustes por función renal")
    for a in ajustes_por_egfr(egfr):
        st.markdown(f"- {a}")

    # --- PRO: Calculadora + guardar variables en session para PDF ---
    if modo == "PRO":
        st.markdown("---")
        st.markdown("### PRO · Calculadora (reglas 500/1800)")
        colc1, colc2, colc3 = st.columns(3)
        with colc1:
            tdd_man = st.number_input("TDD (U/d) si ya usa insulina", 0.0, 300.0, 0.0, step=1.0, key="tdd_man")
        tdd = tdd_man if tdd_man > 0 else round((0.5 if dx=="DM1" else 0.3) * peso, 1)
        with colc2:
            icr = st.number_input("ICR (g/U) – 0 para 500/TDD", 0.0, 250.0, 0.0, step=0.5, key="icr")
        with colc3:
            cf = st.number_input("CF (mg/dL/U) – 0 para 1800/TDD", 0.0, 600.0, 0.0, step=1.0, key="cf")
        if icr == 0:
            icr = round(500.0 / tdd, 1) if tdd > 0 else 0.0
        if cf == 0:
            cf = round(1800.0 / tdd, 0) if tdd > 0 else 0.0
        colp1, colp2, colp3 = st.columns(3)
        with colp1:
            carbs = st.number_input("Carbohidratos (g)", 0.0, 300.0, 45.0, step=1.0, key="carbs")
        with colp2:
            g_act = st.number_input(
                f"Glucosa actual ({unidad_gluc})",
                min_value=ay_min, max_value=ay_max,
                value=8.9 if unidad_gluc=="mmol/L" else 160.0,
                key=f"gact_{unidad_gluc}"
            )
        with colp3:
            g_obj = st.number_input(
                f"Glucosa objetivo ({unidad_gluc})",
                min_value=4.4 if unidad_gluc=="mmol/L" else 70.0,
                max_value=16.7 if unidad_gluc=="mmol/L" else 300.0,
                value=6.1 if unidad_gluc=="mmol/L" else 110.0,
                key=f"gobj_{unidad_gluc}"
            )
        g_act_mgdl = to_mgdl_val(g_act, unidad_gluc)
        g_obj_mgdl = to_mgdl_val(g_obj, unidad_gluc)
        if g_act_mgdl < 70:
            st.warning("Glucosa actual <70 mg/dL: tratar hipoglucemia antes de bolo.")
            dosis_bolo = 0.0
        else:
            dosis_bolo = max(
                0.0,
                carbs / (icr if icr > 0 else 1e9) + max(0.0, (g_act_mgdl - g_obj_mgdl) / (cf if cf > 0 else 1e9))
            )
            dosis_bolo = round(dosis_bolo * 2) / 2.0
        st.metric("Dosis de bolo sugerida", f"{dosis_bolo} U")
        if docente:
            st.caption("Docente: ICR≈500/TDD, CF≈1800/TDD; bolo = CHO/ICR + (Gact−Gobj)/CF. Ajustar con CGM/SMBG y actividad.")

        # Guardar para PDF
        st.session_state["pro_block"] = {
            "tdd": tdd, "icr": icr, "cf": cf,
            "carbs": carbs, "g_act": g_act, "g_obj": g_obj,
            "g_act_mgdl": g_act_mgdl, "g_obj_mgdl": g_obj_mgdl, "dosis_bolo": dosis_bolo,
            "unidad": unidad_gluc
        }
    else:
        st.session_state["pro_block"] = None

# --------- PLAN (PDFs) ----------
with tab_plan:
    st.markdown("#### Plan terapéutico imprimible")
    # Construcción de plan y listas
    recs, just = recomendacion_farmacos(dx, a1c, gluc_ayunas, gluc_pp, egfr, ckd_conocida, ascvd, ic, imc_val)
    texto_basal, reglas = basal_init_titration(dx, peso, a1c)
    plan = recs + [f"Inicio de insulina: {texto_basal}"] + reglas
    if dx == "DM2":
        plan += intensificacion_prandial(max(10, round(0.1*peso)), peso)
    plan += ajustes_por_egfr(egfr)

    # Tratamiento actual (líneas)
    tratamiento_actual_lines = []
    for _, row in st.session_state[key_data].iterrows():
        clase = str(row.get("clase", "")).strip() or "—"
        farm = str(row.get("fármaco", "")).strip() or "—"
        dosis = str(row.get("dosis actual", "")).strip() or "—"
        freq  = str(row.get("frecuencia", "")).strip() or "—"
        tratamiento_actual_lines.append(f"{clase} · {farm}: {dosis} {freq}")

    titulacion_sugerida_lines = []
    for _, row in st.session_state[key_data].iterrows():
        tip = sugerencia_para(row.get("fármaco",""))
        if tip: titulacion_sugerida_lines.append(f"- {row.get('fármaco','')}: {tip}")

    # Utilidades para PDF
    def wrap_lines(c, left, y, width, text, bullet="- "):
        for seg in [text[i:i+95] for i in range(0, len(text), 95)]:
            c.drawString(left, y, f"{bullet}{seg}")
            y -= 14
            if y < 72:
                c.showPage(); y = letter[1] - 72
        return y

    def pdf_plan(datos_paciente, tratamiento_actual, titulacion_sugerida, recomendaciones, justificacion, pro_block=None):
        buffer = BytesIO(); c = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter; left = 1 * inch; y = height - 1 * inch

        c.setFont("Helvetica-Bold", 12)
        c.drawString(left, y, "Plan terapéutico para Diabetes (ADA 2025)")
        y -= 20

        c.setFont("Helvetica", 10)
        for k, v in datos_paciente.items():
            y = wrap_lines(c, left, y, width, f"{k}: {v}", bullet="")
        y -= 8

        c.setFont("Helvetica-Bold", 11); c.drawString(left, y, "Tratamiento actual:"); y -= 16
        c.setFont("Helvetica", 10)
        if not tratamiento_actual:
            y = wrap_lines(c, left, y, width, "— Sin registros —", bullet="- ")
        else:
            for line in tratamiento_actual:
                y = wrap_lines(c, left, y, width, line, bullet="- ")

        y -= 6; c.setFont("Helvetica-Bold", 11); c.drawString(left, y, "Sugerencias de titulación:"); y -= 16
        c.setFont("Helvetica", 10)
        if not titulacion_sugerida:
            y = wrap_lines(c, left, y, width, "— No hay sugerencias —", bullet="• ")
        else:
            for line in titulacion_sugerida:
                y = wrap_lines(c, left, y, width, line, bullet="• ")

        y -= 6; c.setFont("Helvetica-Bold", 11); c.drawString(left, y, "Recomendaciones ADA:"); y -= 16
        c.setFont("Helvetica", 10)
        for line in recomendaciones:
            y = wrap_lines(c, left, y, width, line, bullet="- ")

        y -= 6; c.setFont("Helvetica-Bold", 11); c.drawString(left, y, "Justificación clínica:"); y -= 16
        c.setFont("Helvetica", 10)
        for line in justificacion:
            y = wrap_lines(c, left, y, width, line, bullet="• ")

        # PRO block (si existe)
        if pro_block:
            y -= 6; c.setFont("Helvetica-Bold", 11); c.drawString(left, y, "Cálculos PRO (500/1800):"); y -= 16
            c.setFont("Helvetica", 10)
            unidad = pro_block.get("unidad", "mg/dL")
            items = [
                f"TDD usada: {pro_block.get('tdd','—')} U/d",
                f"ICR: {pro_block.get('icr','—')} g/U",
                f"CF: {pro_block.get('cf','—')} mg/dL/U",
                f"Carbohidratos: {pro_block.get('carbs','—')} g",
                f"Glucosa actual: {pro_block.get('g_act','—')} {unidad}",
                f"Objetivo: {pro_block.get('g_obj','—')} {unidad}",
                f"Dosis de bolo sugerida: {pro_block.get('dosis_bolo','—')} U"
            ]
            for line in items:
                y = wrap_lines(c, left, y, width, line, bullet="• ")

        c.setFont("Helvetica-Oblique", 8); y -= 10
        c.drawString(left, y, "Basado en ADA Standards of Care 2025; esta hoja no sustituye el juicio clínico.")
        c.save(); buffer.seek(0); return buffer

    def pdf_registro(nombre, unidad):
        buffer = BytesIO(); c = canvas.Canvas(buffer, pagesize=letter)
        left = 0.7 * inch; top = letter[1] - 0.7 * inch
        c.setFont("Helvetica-Bold", 12); c.drawString(left, top, f"Registro de glucosa capilar (7 días) – Unidades: {unidad}")
        c.setFont("Helvetica", 10); c.drawString(left, top - 16, f"Paciente: {nombre}    Fecha inicio: {date.today().isoformat()}")
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
        left = 0.7 * inch; top = letter[1] - 0.7 * inch
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
        "A1c": f"{a1c} %",
        "Ayunas": f"{gluc_ayunos} {unidad_gluc}",
        "Posprandial 120 min": f"{gluc_pp_in} {unidad_gluc}",
        "Creatinina": f"{scr} mg/dL",
        "eGFR (CKD-EPI 2021)": f"{egfr} mL/min/1.73 m²",
        "UACR": f"{uacr} mg/g ({uacr_cat})",
        "Fecha": date.today().isoformat()
    }

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("Generar PDF del plan"):
            pdf_bytes = pdf_plan(
                datos_paciente=datos,
                tratamiento_actual=tratamiento_actual_lines,
                titulacion_sugerida=titulacion_sugerida_lines,
                recomendaciones=plan,
                justificacion=just,
                pro_block=st.session_state.get("pro_block")
            )
            st.download_button("Descargar plan.pdf", data=pdf_bytes, file_name="plan_tratamiento_diabetes.pdf", mime="application/pdf")
    with c2:
        if st.button("Generar PDF de registro"):
            pdf_reg = pdf_registro(nombre or "—", unidad_gluc)
            st.download_button("Descargar registro.pdf", data=pdf_reg, file_name="registro_glucosa_capilar.pdf", mime="application/pdf")
    with c3:
        if st.button("Generar PDF hoja de alta"):
            pdf_ha = pdf_alta(nombre or "—", unidad_gluc)
            st.download_button("Descargar alta.pdf", data=pdf_ha, file_name="hoja_alta_diabetes.pdf", mime="application/pdf")

# --------- CATÁLOGO ----------
with tab_cat:
    st.markdown("#### Medicamentos disponibles (ADA)")
    st.caption("Catálogo sin dependencias por institución. Elige **alternativas** si no hay disponibilidad o hay intolerancia.")
    f_clase = st.multiselect("Filtrar por clase", CLASES, default=CLASES)
    tabla = pd.DataFrame(
        [{"clase":c,"fármaco":n,"inicio":i,"máxima":m,"nota":nota} for c,n,i,m,nota in CATALOGO if c in f_clase]
    )
    st.dataframe(tabla, use_container_width=True, hide_index=True)

    st.markdown("#### Sugerir alternativa")
    g1, g2 = st.columns(2)
    with g1:
        clase_sel = st.selectbox("Clase objetivo", CLASES, index=0)
    with g2:
        farm_sel = st.selectbox("Si no disponible / intolerancia a", [d[1] for d in CATALOGO if d[0]==clase_sel])
    alts = alternativas_de_clase(clase_sel, excluir=farm_sel)
    if alts:
        st.markdown("**Alternativas en la misma clase:**")
        for c,n,i,m,nota in alts:
            st.markdown(f"- {n}: inicio **{i}**, máxima **{m}**. {nota}")
    else:
        st.info("No hay alternativas para la combinación elegida.")

# --------- EDUCACIÓN / DOCENTE ----------
with tab_edu:
    st.markdown("#### Glosario educativo: mitos y realidades")
    st.markdown("""
- **“Si empiezo insulina, ya no hay regreso.”** → Puede ser temporal o permanente; depende del control y evolución.
- **“El medicamento daña el riñón.”** → El mal control glucémico/HTA daña el riñón; SGLT2i **protegen**.
- **“Si me siento bien, puedo dejar el tratamiento.”** → Puede no haber síntomas; la adherencia evita complicaciones.
- **“Todas las sulfonilureas son iguales.”** → Diferencias de seguridad; en CKD se prefiere **glipizida**.
- **“La metformina siempre causa daño.”** → Segura en eGFR ≥45; 30–44 con dosis reducida; evitar si <30.
""")

    st.markdown("#### Glosario de términos (clínico)")
    st.markdown("""
- **TDD (Total Daily Dose)**: dosis total diaria de insulina (basal + prandial) expresada en unidades (U/día).
- **ICR (Insulin-to-Carb Ratio)**: cuántos gramos de carbohidratos cubre 1 unidad de insulina. Estimación inicial: **ICR ≈ 500 / TDD**.
- **CF (Correction Factor)** o sensibilidad a insulina: cuántos mg/dL baja 1 unidad de insulina. Estimación inicial: **CF ≈ 1800 / TDD**.
- **Conteo de carbohidratos (CHO)**: método para ajustar bolo prandial según los gramos de CHO que va a ingerir el/la paciente.
""")

    st.markdown("#### ¿Cómo calcular carbohidratos para un bolo?")
    st.markdown("""
1) **Estimar/medir CHO** del plato (leer etiquetas, equivalentes, apps; 1 ración = 15 g CHO).  
2) **Cálculo por ICR**: Bolo por comida = **CHO (g) / ICR (g/U)**.  
3) **Corrección** (si glucosa actual > objetivo): **(Gact − Gobj) / CF**.  
4) **Bolo total** = bolo CHO + corrección. Ajustar por actividad física, tendencia de CGM y riesgo de hipo.  
5) Redondear a incrementos prácticos (p. ej., 0.5–1 U) según dispositivo y experiencia clínica.
""")

    st.markdown("#### Advertencias clínicas importantes")
    st.markdown("""
- **Betabloqueadores** (p. ej., propranolol, metoprolol): pueden **enmascarar síntomas adrenérgicos** de hipoglucemia (temblor, taquicardia). Educar al/la paciente para medir glucosa ante síntomas atípicos (sudoración, confusión).  
- **Fluoroquinolonas** (p. ej., levofloxacino): riesgo de **hipo/hiperglucemia** → vigilar y ajustar.  
- **Corticosteroides sistémicos**: tienden a **elevar** glucosa (hiperglucemia posprandial) → puede requerir correcciones/ajustes temporales.  
- **SGLT2i**: riesgo de **cetoacidosis euglucémica** (especialmente en ayunos, enfermedad aguda, posquirúrgico); suspender en escenarios de alto riesgo y educar señales de alarma.  
- **Sulfonilureas**: mayor riesgo de **hipoglucemia** en adultos mayores y **CKD** → preferir **glipizida**, evitar **gliburida**.  
- **Insulina** + **GLP-1 RA**: combinación útil para bajar A1c y peso; puede requerir **reducir basal** al iniciar GLP-1 RA para evitar hipoglucemia.  
""")

    st.markdown("#### Modo docente · fórmulas clave")
    st.markdown("""
- **eGFR (CKD-EPI 2021)**: 142 × (min(Scr/K,1))^a × (max(Scr/K,1))^−1.2 × (0.9938)^edad × [×1.012 si mujer].  
- **Reglas empíricas**: ICR≈**500/TDD**; CF≈**1800/TDD**.  
- **Basal T2D**: 0.1–0.2 U/kg/d (escenarios seleccionados hasta 0.3–0.5). Titulación **+2 U cada 3 días** al objetivo.  
- **Cuándo añadir bolo**: A1c alta con ayuno controlado o basal >0.5 U/kg/d.
""")

    st.markdown("#### Bibliografía (enlace)")
    st.markdown("""
- ADA **Standards of Care in Diabetes 2025** – https://professional.diabetes.org/standards-of-care  
- ADA (español – diagnóstico/educación) – https://diabetes.org/espanol/diagnostico  
- KDIGO/ADA – Diabetes y enfermedad renal crónica – https://kdigo.org/guidelines/diabetes-ckd/  
- CKD-EPI 2021 calculadora/profesionales – https://www.kidney.org/professionals/kdoqi/gfr_calculator  
""")

st.caption("© 2025 Herramienta de apoyo clínico. Esta app no sustituye el juicio profesional ni las guías oficiales.")
