# app.py — Diabetes ADA MX (PLUS/PRO) con perfiles locales, receta y PDFs
# © 2025. Herramienta de apoyo clínico (no sustituye el juicio profesional).

import os, json
from io import BytesIO
from datetime import date, datetime

import numpy as np
import pandas as pd
import streamlit as st

# PDFs (ligeros)
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch

# ================== Apariencia ==================
st.set_page_config(page_title="Diabetes ADA MX – PLUS/PRO", page_icon="🩺", layout="wide")
st.markdown("""
<style>
:root{--accent:#2563eb;--muted:#64748b;--bg:#f8fafc;--card:#fff;--good:#16a34a;--warn:#f59e0b;--bad:#dc2626}
.block-container{padding-top:2.2rem}
.card{background:var(--card);border:1px solid #e5e7eb;border-radius:.8rem;padding:1rem}
.badge{display:inline-block;padding:.20rem .55rem;border-radius:999px;font-size:.75rem;
       background:rgba(37,99,235,.08);color:#1d4ed8;border:1px solid rgba(37,99,235,.18)}
.small{font-size:.9rem} .muted{color:var(--muted)}
</style>
""", unsafe_allow_html=True)

# ================== Utilidades ==================
def mgdl_to_mmoll(v): 
    try: return round(float(v)/18.0,1)
    except: return None

def mmoll_to_mgdl(v): 
    try: return round(float(v)*18.0,0)
    except: return None

def to_mgdl_val(val, unidad): 
    return mmoll_to_mgdl(val) if unidad=="mmol/L" else float(val)

def bmi(kg, cm):
    try:
        m = float(cm)/100.0
        return round(float(kg)/(m*m),1) if m>0 else None
    except: return None

def egfr_ckdepi_2021(scr_mgdl: float, age: int, sex: str) -> float:
    is_female = str(sex).lower().startswith(("f", "muj"))
    K = 0.7 if is_female else 0.9
    a = -0.241 if is_female else -0.302
    egfr = 142 * (min(scr_mgdl/K,1)**a) * (max(scr_mgdl/K,1)**-1.2) * (0.9938**age)
    if is_female: egfr *= 1.012
    return float(np.round(egfr,1))

def uacr_categoria(uacr_mgg):
    try: v = float(uacr_mgg)
    except: return "ND"
    if v<30: return "A1 (<30 mg/g)"
    if v<300: return "A2 (30–299 mg/g)"
    return "A3 (≥300 mg/g)"

# ================== Almacenamiento local (perfiles) ==================
LOCAL_DIR_DEFAULT = os.path.join(os.path.expanduser("~"), "DiabetesADA")
REPO_PACIENTES_CSV = "data/pacientes.csv"  # respaldo mínimo en repo
LOCAL_PACIENTES_CSV = os.path.join(LOCAL_DIR_DEFAULT, "pacientes.csv")

PACIENTES_COLUMNS = [
    "id","nombre","edad","sexo","dx","peso_kg","talla_cm","a1c_pct",
    "unidad_gluc","gluc_ayunas","gluc_pp",
    "creatinina_mgdl","uacr_mgg","ascvd","ic","ckd",
    "meds_json","notas","fecha_ultima_actualizacion"
]

def _ensure_repo_csv():
    os.makedirs(os.path.dirname(REPO_PACIENTES_CSV), exist_ok=True)
    if not os.path.exists(REPO_PACIENTES_CSV):
        pd.DataFrame(columns=PACIENTES_COLUMNS).to_csv(REPO_PACIENTES_CSV, index=False)

def _ensure_local_csv(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        pd.DataFrame(columns=PACIENTES_COLUMNS).to_csv(path, index=False)

def _load_any_csv(path) -> pd.DataFrame:
    try:
        return pd.read_csv(path, dtype=str).fillna("")
    except Exception:
        return pd.DataFrame(columns=PACIENTES_COLUMNS)

def _next_id(df: pd.DataFrame) -> str:
    if df.empty: return "1"
    try: mx = max(int(x) for x in df["id"] if str(x).isdigit())
    except: mx = 0
    return str(mx+1)

def _defaults_dict():
    return dict(
        nombre="", edad=55, sexo="Masculino", dx="DM2", peso=80.0, talla=170,
        a1c=8.2, unidad_gluc="mg/dL", gluc_ayunos_in=150.0, gluc_pp_in=190.0,
        scr=1.0, uacr=20.0, ascvd=False, ic=False, ckd=False, notas_paciente="",
    )

def _safe_set(k, v):
    # evita errores de Streamlit al sobrescribir keys de widgets en momentos “sensibles”
    try: st.session_state[k] = v
    except Exception: pass

def _collect_from_state() -> dict:
    return {
        "nombre": st.session_state.get("nombre",""),
        "edad": str(st.session_state.get("edad","")),
        "sexo": st.session_state.get("sexo", st.session_state.get("Sexo biológico","")),
        "dx": st.session_state.get("dx", st.session_state.get("Diagnóstico","DM2")),
        "peso_kg": str(st.session_state.get("peso","")),
        "talla_cm": str(st.session_state.get("talla","")),
        "a1c_pct": str(st.session_state.get("a1c","")),
        "unidad_gluc": st.session_state.get("unidad_gluc","mg/dL"),
        "gluc_ayunas": str(st.session_state.get("gluc_ayunos_in","")),
        "gluc_pp": str(st.session_state.get("gluc_pp_in","")),
        "creatinina_mgdl": str(st.session_state.get("scr","")),
        "uacr_mgg": str(st.session_state.get("uacr","")),
        "ascvd": "Sí" if st.session_state.get("ascvd",False) else "No",
        "ic":    "Sí" if st.session_state.get("ic",False) else "No",
        "ckd":   "Sí" if st.session_state.get("ckd",False) else "No",
        "meds_json": json.dumps(st.session_state.get("plan_meds",{}), ensure_ascii=False),
        "notas": st.session_state.get("notas_paciente",""),
        "fecha_ultima_actualizacion": datetime.utcnow().strftime("%Y-%m-%d %H:%MZ"),
    }

def _apply_to_widgets(p: dict):
    # Setea SOLO donde no rompe (envolvemos en _safe_set)
    _safe_set("nombre", p.get("nombre",""))
    _safe_set("edad", int(float(p["edad"])) if str(p.get("edad","")).strip() else 0)
    _safe_set("sexo", p.get("sexo","Masculino"))
    _safe_set("dx", p.get("dx","DM2"))
    _safe_set("peso", float(p["peso_kg"]) if p.get("peso_kg","") else 0.0)
    _safe_set("talla", int(float(p["talla_cm"])) if p.get("talla_cm","") else 0)
    _safe_set("a1c", float(p["a1c_pct"]) if p.get("a1c_pct","") else 0.0)
    _safe_set("unidad_gluc", p.get("unidad_gluc","mg/dL"))
    _safe_set("gluc_ayunos_in", float(p["gluc_ayunas"]) if p.get("gluc_ayunas","") else 0.0)
    _safe_set("gluc_pp_in", float(p["gluc_pp"]) if p.get("gluc_pp","") else 0.0)
    _safe_set("scr", float(p["creatinina_mgdl"]) if p.get("creatinina_mgdl","") else 0.0)
    _safe_set("uacr", float(p["uacr_mgg"]) if p.get("uacr_mgg","") else 0.0)
    _safe_set("ascvd", p.get("ascvd","No")=="Sí")
    _safe_set("ic", p.get("ic","No")=="Sí")
    _safe_set("ckd", p.get("ckd","No")=="Sí")
    try: _safe_set("plan_meds", json.loads(p.get("meds_json","{}")))
    except: _safe_set("plan_meds", {})
    _safe_set("notas_paciente", p.get("notas",""))

def ui_perfiles_pacientes():
    st.markdown("#### 👤 Perfiles de pacientes (guardar, nuevo, cargar, exportar/importar)")
    with st.expander("Perfiles de pacientes", expanded=True):
        col_top = st.columns([1.4,1,1,1])
        # Local consent + carpeta
        with col_top[0]:
            st.caption("**Estado:**")
            st.toggle("Acepto guardar **SOLO EN ESTA PC**", key="local_guardado_aceptado", value=st.session_state.get("local_guardado_aceptado", False))
            st.text_input("Carpeta local donde se guardarán los datos:", value=st.session_state.get("local_dir", LOCAL_DIR_DEFAULT), key="local_dir")
            st.caption("Almacenamiento mínimo de respaldo (solo CSV): `data/pacientes.csv`")

        # Selector
        _ensure_repo_csv()
        local_csv = os.path.join(st.session_state.get("local_dir", LOCAL_DIR_DEFAULT), "pacientes.csv")
        _ensure_local_csv(local_csv)
        df_local = _load_any_csv(local_csv)
        listado = (df_local["id"] + " — " + df_local["nombre"]).tolist() if not df_local.empty else []
        sel = st.selectbox("Perfiles guardados", listado, index=0 if listado else None, key="perfil_sel")

        with col_top[1]:
            if st.button("📂 Cargar", use_container_width=True, disabled=not sel):
                pid = sel.split(" — ")[0]
                p = df_local[df_local["id"]==pid].iloc[0].to_dict()
                _apply_to_widgets(p)
                st.success(f"Perfil cargado: {p.get('nombre','')}")

        with col_top[2]:
            if st.button("➕ Nuevo", use_container_width=True):
                for k,v in _defaults_dict().items(): _safe_set(k, v)
                st.info("Formulario limpio. Ingresa datos y pulsa **Guardar**.")

        with col_top[3]:
            if st.button("💾 Guardar/Actualizar", use_container_width=True):
                if not st.session_state.get("local_guardado_aceptado", False):
                    st.error("Debes aceptar el guardado local.")
                else:
                    datos = _collect_from_state()
                    if sel:
                        pid = sel.split(" — ")[0]
                        idx = df_local.index[df_local["id"]==pid]
                        if len(idx):
                            datos["id"]=pid
                            for k,v in datos.items(): df_local.loc[idx, k] = str(v)
                        else:
                            datos["id"]=_next_id(df_local); df_local = pd.concat([df_local, pd.DataFrame([datos])], ignore_index=True)
                    else:
                        datos["id"]=_next_id(df_local); df_local = pd.concat([df_local, pd.DataFrame([datos])], ignore_index=True)
                    df_local.to_csv(local_csv, index=False)
                    st.success("Guardado en la carpeta local.")

        # Export / Import (USB)
        st.markdown("---")
        c1,c2 = st.columns(2)
        with c1:
            buf = BytesIO(); _load_any_csv(local_csv).to_csv(buf, index=False); buf.seek(0)
            st.download_button("⬇️ Descargar `pacientes.csv`", data=buf, file_name="pacientes.csv", mime="text/csv", use_container_width=True)
        with c2:
            f = st.file_uploader("Subir CSV para unir o reemplazar", type=["csv"])
            modo = st.radio("Modo de carga", ["Unir (merge)", "Reemplazar"], horizontal=True)
            if f and st.button("Procesar CSV"):
                up = pd.read_csv(f, dtype=str).fillna("")
                if "id" not in up.columns:
                    st.error("El CSV subido debe tener columna 'id'.")
                else:
                    if modo.startswith("Reemplazar"):
                        up.to_csv(local_csv, index=False); st.success("Archivo reemplazado.")
                    else:
                        base = _load_any_csv(local_csv)
                        mezcla = pd.concat([base[~base["id"].isin(up["id"])], up], ignore_index=True)
                        mezcla.to_csv(local_csv, index=False); st.success("Perfiles unidos.")

# ================== Catálogo (simplificado, sin instituciones) ==================
# clase, fármaco, inicio, maxima, nota, tipo (insulina?/no)
CATALOGO = [
    ("Metformina", "Metformina", "500 mg c/12 h", "3000 mg/d", "Subir cada 1–2 semanas si tolera GI; con comida.", False),
    ("SGLT2i", "Empagliflozina", "10 mg c/24 h", "25 mg c/24 h", "eGFR ≥20: protección renal/CV (efecto glucémico menor si eGFR <45).", False),
    ("SGLT2i", "Dapagliflozina", "10 mg c/24 h", "10 mg c/24 h", "eGFR ≥20: protección renal/CV; dosis única.", False),
    ("DPP-4", "Linagliptina", "5 mg c/24 h", "5 mg c/24 h", "Sin ajuste renal.", False),
    ("DPP-4", "Sitagliptina", "100 mg c/24 h", "100 mg c/24 h", "50 mg si eGFR 30–44; 25 mg si <30.", False),
    ("GLP-1 RA", "Semaglutida sc semanal", "0.25 mg/sem", "2.0 mg/sem", "Subir cada 4 semanas; útil en pérdida de peso.", False),
    ("GLP-1 RA", "Dulaglutida sc semanal", "0.75 mg/sem", "4.5 mg/sem", "Aumentos cada 4 semanas.", False),
    ("SU", "Glipizida", "2.5–5 mg c/24 h", "20 mg/d", "Preferible a gliburida; riesgo hipo.", False),
    ("TZD", "Pioglitazona", "15 mg c/24 h", "45 mg c/24 h", "Vigilar edema/IC.", False),
    # Insulinas:
    ("Insulina basal", "Glargina U100", "10 U/d (nocturna)", "—", "Titulación +2 U cada 3 d a ayuno 80–130 mg/dL.", True),
    ("Insulina basal", "Degludec", "10 U/d (nocturna)", "—", "Muy larga duración, 1× día.", True),
    ("Insulina basal", "NPH", "10 U pre-cena (o nocturna)", "—", "Coste menor; mayor riesgo hipo nocturna.", True),
    ("Insulina prandial", "Aspart/Lispro", "4–6 U antes de comida", "—", "Añadir si A1c alta con ayuno OK o basal >0.5 U/kg/d.", True),
    ("Insulina prandial", "Regular", "4–6 U antes de comida", "—", "Alternativa; inicio más lento.", True),
]
CLASES = sorted(list({c for c,_,_,_,_,_ in CATALOGO}))
CAT_FARM = [d[1] for d in CATALOGO]
INS_HORARIOS = [
    "No aplica",
    "Basal nocturna",
    "Pre-desayuno",
    "Pre-comida",
    "Pre-cena",
    "Comida principal",
]

def sug_titulacion(farm):
    r = [d for d in CATALOGO if d[1]==farm]
    if not r: return None
    c,n,i,m,nota,_ = r[0]
    return f"Inicio sugerido: **{i}** · **Máxima:** {m}. {nota}"

def alternativas_de_clase(clase, excluir=None):
    out = [d for d in CATALOGO if d[0]==clase]
    if excluir: out = [d for d in out if d[1]!=excluir]
    return out

# ================== Encabezado simple ==================
topL, topR = st.columns([1,1])
with topL:
    st.markdown("### 🩺 Diabetes ADA MX")
    modo = st.radio("Modo de trabajo", ["PLUS","PRO"], horizontal=True, index=0,
                    help="PRO añade calculadora 500/1800 para bolo y exporta al PDF.")
with topR:
    docente = st.toggle("🎓 Modo docente", value=False)

# ================== Sidebar: datos de paciente ==================
with st.sidebar:
    st.header("Paciente")
    unidad_gluc = st.selectbox("Unidades de glucosa", ["mg/dL","mmol/L"], key="unidad_gluc")
    nombre = st.text_input("Nombre", key="nombre")
    edad = st.number_input("Edad (años)", 18, 100, _defaults_dict()["edad"], key="edad")
    sexo = st.selectbox("Sexo biológico", ["Femenino","Masculino"], key="sexo")
    dx = st.selectbox("Diagnóstico", ["DM2","DM1"], key="dx")
    peso = st.number_input("Peso (kg)", 25.0, 300.0, _defaults_dict()["peso"], step=0.5, key="peso")
    talla = st.number_input("Talla (cm)", 120, 230, _defaults_dict()["talla"], key="talla")
    imc_val = bmi(peso, talla)
    st.caption(f"IMC: **{imc_val if imc_val else 'ND'} kg/m²**")

    st.divider()
    ui_perfiles_pacientes()

    st.header("Bioquímicos")
    a1c = st.number_input("A1c (%)", 4.0, 15.0, _defaults_dict()["a1c"], step=0.1, key="a1c")
    # Rango seguros por unidad
    lo_ay, hi_ay = (2.0, 33.3) if unidad_gluc=="mmol/L" else (50.0, 600.0)
    lo_pp, hi_pp = (2.0, 33.3) if unidad_gluc=="mmol/L" else (50.0, 600.0)
    gluc_ayunos_in = st.number_input(f"Glucosa en ayunas ({unidad_gluc})", lo_ay, hi_ay, _defaults_dict()["gluc_ayunos_in"], key="gluc_ayunos_in")
    gluc_pp_in     = st.number_input(f"Glucosa 120 min ({unidad_gluc})", lo_pp, hi_pp, _defaults_dict()["gluc_pp_in"], key="gluc_pp_in")
    gluc_ayunos = to_mgdl_val(gluc_ayunos_in, unidad_gluc)
    gluc_pp = to_mgdl_val(gluc_pp_in, unidad_gluc)

    st.header("Renal/Cardio")
    scr = st.number_input("Creatinina (mg/dL)", 0.2, 12.0, _defaults_dict()["scr"], step=0.1, key="scr")
    uacr = st.number_input("UACR (mg/g)", 0.0, 10000.0, _defaults_dict()["uacr"], step=1.0, key="uacr")
    ascvd = st.checkbox("ASCVD (IAM/ictus/PAD)", key="ascvd")
    ic = st.checkbox("Insuficiencia cardiaca (IC)", key="ic")
    ckd = st.checkbox("CKD conocida", key="ckd")
    notas = st.text_area("Notas clínicas", key="notas_paciente")

# ================== Cálculos básicos y metas ==================
egfr = egfr_ckdepi_2021(scr, int(edad), sexo)
uacr_cat = uacr_categoria(uacr)

def metas_base(edad):
    return {"A1c_max":7.5,"pre_min":80,"pre_max":130,"pp_max":180} if edad>=65 else {"A1c_max":7.0,"pre_min":80,"pre_max":130,"pp_max":180}
metas = metas_base(edad)

# clamp helper
def _clamp(v, lo, hi, ndigits=1):
    try: v=float(v)
    except: v=lo
    return round(max(lo, min(hi, v)), ndigits)

st.subheader("Metas activas")
a1c_meta = st.number_input("A1c meta (%)", min_value=5.5, max_value=9.0, value=float(metas["A1c_max"]), step=0.1, key="a1c_meta")

if unidad_gluc=="mmol/L":
    pre_min_lo, pre_min_hi = 3.5, 22.2
    pre_max_lo, pre_max_hi = 4.0, 22.2
    pp_max_lo,  pp_max_hi  = 5.5, 22.2
    pre_min_def = _clamp(mgdl_to_mmoll(metas["pre_min"]), pre_min_lo, pre_min_hi)
    pre_max_def = _clamp(mgdl_to_mmoll(metas["pre_max"]), pre_max_lo, pre_max_hi)
    pp_max_def  = _clamp(mgdl_to_mmoll(metas["pp_max"]),  pp_max_lo,  pp_max_hi)
else:
    pre_min_lo, pre_min_hi = 60.0, 400.0
    pre_max_lo, pre_max_hi = 70.0, 400.0
    pp_max_lo,  pp_max_hi  = 100.0, 400.0
    pre_min_def = _clamp(metas["pre_min"], pre_min_lo, pre_min_hi)
    pre_max_def = _clamp(metas["pre_max"], pre_max_lo, pre_max_hi)
    pp_max_def  = _clamp(metas["pp_max"],  pp_max_lo,  pp_max_hi)

cA, cB, cC = st.columns(3)
with cA:
    pre_min = st.number_input(f"Preprandial mín ({unidad_gluc})", min_value=pre_min_lo, max_value=pre_min_hi, value=pre_min_def, step=0.1, key=f"pre_min_{unidad_gluc}")
with cB:
    pre_max = st.number_input(f"Preprandial máx ({unidad_gluc})", min_value=pre_max_lo, max_value=pre_max_hi, value=pre_max_def, step=0.1, key=f"pre_max_{unidad_gluc}")
with cC:
    pp_max  = st.number_input(f"Posprandial máx 1–2 h ({unidad_gluc})", min_value=pp_max_lo,  max_value=pp_max_hi,  value=pp_max_def,  step=0.1, key=f"pp_max_{unidad_gluc}")

st.caption(f"eGFR CKD-EPI 2021: **{egfr} mL/min/1.73m²** · UACR: **{uacr} mg/g** ({uacr_cat})")

# ================== Motor de recomendaciones ==================
def recomendaciones_ada(tipo_dm, a1c, gl_ay, gl_pp, egfr, ckd, ascvd, ic, imc, a1c_target):
    rec, just = [], []
    if tipo_dm=="DM1":
        rec.append("DM1 → tratamiento con **insulina basal-bolo** o sistemas AID; contar carbohidratos.")
        return rec, just

    # 1) ¿Insulina desde inicio?
    if (a1c is not None and a1c>=10) or (gl_ay is not None and gl_ay>=300):
        rec.append("**Iniciar insulina** (basal ± prandial) desde el inicio.")
        just.append("A1c ≥10% o glucosa ≥300 mg/dL / síntomas catabólicos → ADA sugiere insulina temprana.")
    # 2) Riesgo CV/renal
    if ic: 
        rec.append("**IC** → priorizar **SGLT2i** (beneficio en IC).")
        just.append("SGLT2i reducen hospitalización por IC.")
    if ascvd:
        rec.append("**ASCVD** → **GLP-1 RA** con beneficio CV o **SGLT2i**.")
    if (ckd or egfr<60):
        if egfr>=20: rec.append("**CKD** → añadir **SGLT2i** (eGFR ≥20) por protección renal/CV.")
        else: rec.append("**CKD avanzada** (eGFR <20) → preferir **GLP-1 RA**.")
    # 3) Metformina por función renal
    if egfr>=45: rec.append("**Metformina** util y segura (eGFR ≥45).")
    elif 30<=egfr<45: rec.append("Metformina si ya usaba → **máx 2000–3000 mg/d**; **evitar iniciar** en 30–44.")
    else: rec.append("**Metformina contraindicada** (eGFR <30).")
    # 4) PP alta
    umbral_pp = pp_max if unidad_gluc=="mg/dL" else mmoll_to_mgdl(pp_max)
    if gl_pp and gl_pp>umbral_pp:
        rec.append("**Posprandial elevada** → **GLP-1 RA** o añadir **bolo prandial**; revisar raciones/tiempos.")
    # 5) Si bajo riesgo y A1c cerca de meta
    if not (ic or ascvd or ckd or egfr<60):
        if a1c is not None and a1c<=a1c_target and gl_ay is not None and gl_ay<=130:
            rec.append("**Mantener** plan actual + estilo de vida; monitorizar.")
        else:
            rec.append("**Metformina** + estilo de vida; considerar **GLP-1 RA** o **SGLT2i** si no alcanza meta.")
    # 6) ¿Qué insulina basal?
    if any("Iniciar insulina" in x for x in rec) or (a1c and a1c>a1c_target and gl_ay and gl_ay>pre_max):
        rec.append("**Basal preferida**: glargina/degludec (menor hipo); si costo es limitante → **NPH**.")
    return rec, just

def basal_inicio_titulacion(dx, peso_kg, a1c):
    if dx=="DM1":
        tdd = round(0.5*peso_kg,1); basal = round(tdd*0.5,1); prand = round(tdd*0.5/3,1)
        return f"TDD≈{tdd} U/d → **Basal {basal} U/d** y **Prandial {prand} U** antes de cada comida.", [
            "Ajustar con CGM/SMBG y conteo de carbohidratos.", "Vigilar hipoglucemias nocturnas."
        ]
    base = max(10, round(0.1*peso_kg))
    if a1c and a1c>=9: base = max(base, round(0.2*peso_kg))
    reglas = [
        "Titular **+2 U cada 3 días** hasta ayuno **80–130 mg/dL**.",
        "Si hipo <70 mg/dL → bajar 10–20%.",
        "Si A1c alta con ayuno controlado o basal >0.5 U/kg/d → añadir **bolo prandial**."
    ]
    return f"Iniciar **insulina basal** en **{base} U/d** (0.1–0.2 U/kg/d).", reglas

def prandial_si_necesaria(basal_ud, peso_kg):
    inicio = max(4, int(round(basal_ud*0.1)))
    return [
        f"Si basal > **{round(0.5*peso_kg,1)} U/d** o A1c persiste alta con ayuno OK → bolo en comida principal: **{inicio} U**.",
        "Progresar a 2 comidas, luego 3 (basal-bolo).",
        "Alternativa: **GLP-1 RA** antes de añadir bolo (peso/adhesión)."
    ]

def ajustes_por_egfr(egfr):
    out=[]
    if egfr>=45: out.append("Metformina: **dosis plena** si tolera.")
    elif 30<=egfr<45: out.append("Metformina: si ya estaba, **máx 2000–3000 mg/d**; evitar iniciar.")
    else: out.append("Metformina: **contraindicada** (<30).")
    out+=["SGLT2i: indicado en T2D+CKD con eGFR ≥20 (beneficio renal/CV).",
          "DPP-4: linagliptina 5 mg sin ajuste; sitagliptina 50 mg (eGFR 30–44) o 25 mg (<30).",
          "GLP-1 RA: sema/dula/lira sin ajuste; evitar exenatida si eGFR <30.",
          "SU: preferir glipizida; evitar gliburida (hipo).",
          "TZD: sin ajuste renal; vigilar edema/IC."]
    return out

# ================== Tratamiento actual (editor) ==================
st.subheader("Tratamiento actual y titulación")
df_cols = ["clase","fármaco","dosis","vía/horario","frecuencia"]
ejemplo = pd.DataFrame([
    {"clase":"Metformina","fármaco":"Metformina","dosis":"850 mg","vía/horario":"No aplica","frecuencia":"c/12 h"},
    {"clase":"DPP-4","fármaco":"Linagliptina","dosis":"5 mg","vía/horario":"No aplica","frecuencia":"c/24 h"},
    {"clase":"SGLT2i","fármaco":"Dapagliflozina","dosis":"10 mg","vía/horario":"No aplica","frecuencia":"c/24 h"},
    {"clase":"Insulina basal","fármaco":"NPH","dosis":"10 U","vía/horario":"Pre-cena","frecuencia":"—"},
], columns=df_cols)

if "tabla_trat" not in st.session_state:
    st.session_state["tabla_trat"] = ejemplo

edit_df = st.data_editor(
    st.session_state["tabla_trat"],
    num_rows="dynamic",
    use_container_width=True, hide_index=True,
    columns={
        "clase": st.column_config.SelectboxColumn(options=CLASES, required=True),
        "fármaco": st.column_config.SelectboxColumn(options=CAT_FARM, required=True),
        "dosis": st.column_config.TextColumn(help="Ej. 850 mg / 10 U"),
        "vía/horario": st.column_config.SelectboxColumn(options=INS_HORARIOS),
        "frecuencia": st.column_config.TextColumn(help="c/12 h, nocturna, etc.")
    }
)
st.session_state["tabla_trat"] = edit_df

sugs = []
for _,r in edit_df.iterrows():
    tip = sug_titulacion(r["fármaco"])
    if tip: sugs.append(f"- **{r['fármaco']}**: {tip}")
if sugs:
    st.markdown("**Sugerencias de titulación:**"); st.markdown("\n".join(sugs))

# ================== Tabs ==================
tab_res, tab_plan, tab_cat, tab_edu = st.tabs(["📊 Resumen","🧭 Plan terapéutico","💊 Catálogo","📚 Educación"])

with tab_res:
    st.markdown("#### Panorama clínico")
    st.markdown(
        f'<div class="card small"><b>eGFR:</b> {egfr} mL/min/1.73m² · <b>UACR:</b> {uacr} mg/g ({uacr_cat}) · '
        f'<b>A1c:</b> {a1c}% · <b>Ayuno:</b> {gluc_ayunos_in} {unidad_gluc} · '
        f'<b>120 min:</b> {gluc_pp_in} {unidad_gluc} · <b>IMC:</b> {imc_val if imc_val else "ND"} kg/m²</div>',
        unsafe_allow_html=True
    )
    recs, just = recomendaciones_ada(dx, a1c, gluc_ayunos, gluc_pp, egfr, ckd, ascvd, ic, imc_val, a1c_meta)
    st.markdown("#### Recomendación terapéutica (ADA – priorización por riesgo)")
    for r in recs: st.markdown(f"- {r}")
    if docente and just:
        st.markdown("**Justificación (docente):**")
        for j in just: st.markdown(f"• {j}")

    st.markdown("#### Insulina: dosis de inicio y titulación")
    intro, reglas = basal_inicio_titulacion(dx, peso, a1c)
    st.markdown(f"- {intro}")
    for rr in reglas: st.markdown(f"  - {rr}")
    if dx=="DM2":
        basal_ref = max(10, round(0.1*peso))
        for ptxt in prandial_si_necesaria(basal_ref, peso):
            st.markdown(f"- {ptxt}")

    st.markdown("#### Ajustes por función renal")
    for a in ajustes_por_egfr(egfr): st.markdown(f"- {a}")

    if modo=="PRO":
        st.markdown("---"); st.markdown("### PRO · Calculadora 500/1800")
        c1,c2,c3 = st.columns(3)
        with c1: tdd_man = st.number_input("TDD (U/d) si ya usa insulina", 0.0, 300.0, 0.0, step=1.0, key="tdd_man")
        tdd = tdd_man if tdd_man>0 else round((0.5 if dx=="DM1" else 0.3)*peso,1)
        with c2: icr = st.number_input("ICR (g/U) – 0 para 500/TDD", 0.0, 250.0, 0.0, step=0.5)
        with c3: cf  = st.number_input("CF (mg/dL/U) – 0 para 1800/TDD", 0.0, 600.0, 0.0, step=1.0)
        icr = round(500.0/tdd,1) if (icr==0 and tdd>0) else icr
        cf  = round(1800.0/tdd,0) if (cf==0 and tdd>0) else cf
        d1,d2,d3 = st.columns(3)
        with d1: carbs = st.number_input("Carbohidratos (g)", 0.0, 300.0, 45.0, step=1.0)
        with d2: g_act = st.number_input(f"Glucosa actual ({unidad_gluc})", lo_ay, hi_ay, 160.0 if unidad_gluc=="mg/dL" else 8.9)
        with d3: g_obj = st.number_input(f"Glucosa objetivo ({unidad_gluc})", 70.0 if unidad_gluc=="mg/dL" else 4.4, 300.0 if unidad_gluc=="mg/dL" else 16.7, 110.0 if unidad_gluc=="mg/dL" else 6.1)
        g_act_mgdl = to_mgdl_val(g_act, unidad_gluc); g_obj_mgdl = to_mgdl_val(g_obj, unidad_gluc)
        if g_act_mgdl<70: dosis_bolo = 0.0; st.warning("Glucosa <70 mg/dL: tratar hipoglucemia antes de bolo.")
        else:
            dosis_bolo = max(0.0, carbs/(icr if icr>0 else 1e9) + max(0.0,(g_act_mgdl-g_obj_mgdl)/(cf if cf>0 else 1e9)))
            dosis_bolo = round(dosis_bolo*2)/2.0
        st.metric("Dosis de bolo sugerida", f"{dosis_bolo} U")
        if docente: st.caption("ICR≈500/TDD, CF≈1800/TDD; bolo = CHO/ICR + (Gact−Gobj)/CF.")

with tab_plan:
    st.markdown("#### Plan terapéutico (tipo receta)")
    # “Receta” a partir del editor:
    receta_lines=[]
    for _,r in edit_df.iterrows():
        parte_hor = f" · {r['vía/horario']}" if r["vía/horario"]!="No aplica" else ""
        frec = f" · {r['frecuencia']}" if str(r["frecuencia"]).strip() else ""
        receta_lines.append(f"{r['fármaco']}: {r['dosis']}{parte_hor}{frec}")
    st.write("\n".join([f"• {x}" for x in receta_lines]) if receta_lines else "— sin items —")

    st.markdown("---")
    # PDF plan
    def _wrap(c, left, y, text, bullet="• "):
        for seg in [text[i:i+95] for i in range(0,len(text),95)]:
            c.drawString(left, y, f"{bullet}{seg}"); y -= 14
            if y < 72: c.showPage(); y = letter[1]-72
        return y

    def pdf_plan():
        buf = BytesIO(); c = canvas.Canvas(buf, pagesize=letter)
        w,h = letter; left = 1*inch; y = h-1*inch
        c.setFont("Helvetica-Bold", 12); c.drawString(left, y, "Plan terapéutico / Receta — Diabetes (ADA)"); y -= 20
        c.setFont("Helvetica",10)
        info = [
            f"Paciente: {nombre or '—'}    Fecha: {date.today().isoformat()}",
            f"DX: {dx}   Edad: {edad}   Sexo: {sexo}   Unidades: {unidad_gluc}",
            f"eGFR: {egfr} mL/min/1.73m²  · UACR: {uacr} mg/g ({uacr_cat})  · A1c: {a1c}%",
        ]
        for it in info: y = _wrap(c, left, y, it, bullet="")
        y -= 6; c.setFont("Helvetica-Bold", 11); c.drawString(left, y, "Receta:"); y -= 16; c.setFont("Helvetica",10)
        for line in receta_lines: y = _wrap(c, left, y, line)
        y -= 6; c.setFont("Helvetica-Bold", 11); c.drawString(left, y, "Notas / Recomendaciones:"); y -= 16; c.setFont("Helvetica",10)
        for line in recomendaciones_ada(dx, a1c, gluc_ayunos, gluc_pp, egfr, ckd, ascvd, ic, imc_val, a1c_meta)[0]:
            y = _wrap(c, left, y, line)
        c.setFont("Helvetica-Oblique", 8); y -= 10
        c.drawString(left, y, "Basado en ADA Standards of Care; no sustituye el juicio clínico.")
        c.save(); buf.seek(0); return buf

    colp = st.columns(3)
    with colp[0]:
        if st.button("Generar PDF del plan"): 
            st.download_button("Descargar plan.pdf", data=pdf_plan(), file_name="plan_tratamiento.pdf", mime="application/pdf")

with tab_cat:
    st.markdown("#### Catálogo (selección ADA)")
    fcl = st.multiselect("Filtrar por clase", CLASES, default=CLASES)
    tabla = pd.DataFrame([{"clase":c,"fármaco":n,"inicio":i,"máxima":m,"nota":nota}
                          for c,n,i,m,nota,_ in CATALOGO if c in fcl])
    st.dataframe(tabla, use_container_width=True, hide_index=True)
    st.markdown("#### Alternativas dentro de la clase")
    cc1,cc2 = st.columns(2)
    with cc1: clase_sel = st.selectbox("Clase", CLASES)
    with cc2: farm_sel = st.selectbox("Si no disponible/intolerancia a", [d[1] for d in CATALOGO if d[0]==clase_sel])
    alts = alternativas_de_clase(clase_sel, excluir=farm_sel)
    if alts:
        for c,n,i,m,nota,_ in alts: st.markdown(f"- {n}: inicio **{i}**, máxima **{m}**. {nota}")
    else:
        st.info("Sin alternativas para esa combinación.")

with tab_edu:
    st.markdown("#### Glosario rápido")
    st.markdown("""
- **TDD**: dosis total diaria de insulina.  
- **ICR** (Insulin-to-Carb Ratio): g de CHO cubiertos por 1 U. **≈ 500/TDD**.  
- **CF** (Correction Factor): mg/dL que baja 1 U. **≈ 1800/TDD**.  
- **Conteo de carbohidratos**: bolo CHO = CHO/ICR; corrección = (Gact–Gobj)/CF.
""")
    st.markdown("#### Advertencias")
    st.markdown("""
- **Betabloqueadores**: pueden enmascarar síntomas de hipoglucemia.  
- **Fluoroquinolonas**: hipo/hiperglucemia.  
- **Corticosteroides**: hiperglucemia posprandial.  
- **SGLT2i**: riesgo de **cetoacidosis euglucémica** en ayuno/enfermedad; educación de alarma.  
""")
