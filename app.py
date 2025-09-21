# app.py – Diabetes ADA MX (Premium, PLUS/PRO + Cuadro Básico Auto)

import streamlit as st
import numpy as np
import pandas as pd
from io import BytesIO
from datetime import date, datetime
from pathlib import Path

# PDF
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch

# ================== CONFIGURACIÓN PÁGINA & ESTILO ==================
st.set_page_config(
    page_title="Diabetes ADA MX",
    page_icon="🩺",
    layout="wide"
)

# Encabezado con logo (assets/logo.png)
logo_path = Path("assets/logo.png")
if logo_path.exists():
    col_logo, col_title = st.columns([1, 5])
    with col_logo:
        st.image(str(logo_path), use_column_width=True)
    with col_title:
        st.title("🩺 Diabetes ADA MX")
        st.caption("Motor ADA · eGFR CKD-EPI 2021 · PRO 500/1800 · PDFs · Cuadro básico auto-actualizable")
else:
    st.title("🩺 Diabetes ADA MX")
    st.caption("Motor ADA · eGFR CKD-EPI 2021 · PRO 500/1800 · PDFs · Cuadro básico auto-actualizable")

# CSS premium (suave)
st.markdown("""
<style>
section.main .block-container { max-width: 1200px; }
.stButton > button {
  border-radius: 12px; padding: 0.6rem 1rem; font-weight: 600;
}
.stTextInput > div > div > input,
.stNumberInput > div > div > input,
.stSelectbox > div > div { border-radius: 10px !important; }
[data-testid="stMetricValue"] { font-weight: 700; }
</style>
""", unsafe_allow_html=True)

# ================== CONSENTIMIENTO ==================
if "acepta" not in st.session_state:
    st.session_state["acepta"] = False

if not st.session_state["acepta"]:
    st.subheader("Aviso de privacidad y descargo de responsabilidad")
    st.markdown("""
**Uso clínico responsable:** Esta app resume guías (ADA, CKD-EPI) y buenas prácticas. **No sustituye** el juicio clínico ni lineamientos oficiales.  
**Privacidad:** Evita datos identificables en exportables; cumple la normativa local aplicable.
""")
    acepto = st.checkbox("He leído y acepto el Aviso de Privacidad y el Descargo de Responsabilidad.")
    st.button("Ingresar", disabled=not acepto, on_click=lambda: st.session_state.update({"acepta": True}))
    st.stop()

# ================== MODO PLUS/PRO ==================
if "modo" not in st.session_state:
    st.session_state["modo"] = "PLUS"

def switch_mode():
    st.session_state["modo"] = "PRO" if st.session_state["modo"] == "PLUS" else "PLUS"

col_head1, col_head2 = st.columns([5,2])
with col_head1:
    st.caption("Versión premium · interfaz limpia y profesional")
with col_head2:
    if st.session_state["modo"] == "PLUS":
        st.button("🔓 Abrir Modo PRO", on_click=switch_mode)
    else:
        st.button("⬅️ Volver a Modo PLUS", on_click=switch_mode)

# ================== UTILIDADES CLÍNICAS ==================
def egfr_ckdepi_2021(scr_mgdl: float, age: int, sex: str) -> float:
    is_fem = sex.lower().startswith("f")
    K = 0.7 if is_fem else 0.9
    a = -0.241 if is_fem else -0.302
    egfr = 142 * (min(scr_mgdl / K, 1) ** a) * (max(scr_mgdl / K, 1) ** -1.200) * (0.9938 ** age)
    if is_fem:
        egfr *= 1.012
    return float(np.round(egfr, 1))

def metas_glicemicas_default(edad):
    if edad >= 65:
        return {"A1c_max": 7.5, "pre_min": 80, "pre_max": 130, "pp_max": 180}
    else:
        return {"A1c_max": 7.0, "pre_min": 80, "pre_max": 130, "pp_max": 180}

def bmi(kg, cm):
    try:
        m = cm / 100.0
        if m <= 0: return None
        return round(kg / (m*m), 1)
    except Exception:
        return None

def uacr_categoria(uacr_mgg):
    try:
        v = float(uacr_mgg)
    except:
        return "ND"
    if v < 30: return "A1 (<30 mg/g)"
    if v < 300: return "A2 (30–299 mg/g)"
    return "A3 (≥300 mg/g)"

def to_mgdl(value, unidad):
    if value is None: return None
    return float(value) * 18.0 if unidad == "mmol/L" else float(value)

def to_unit(value_mgdl, unidad):
    if value_mgdl is None: return None
    return round(float(value_mgdl)/18.0, 1) if unidad == "mmol/L" else float(value_mgdl)

# ================== CARGA DE CUADRO BÁSICO (DEL REPO) ==================
@st.cache_data(ttl=86400)
def cargar_cuadro_local():
    try:
        df = pd.read_csv("data/cuadro.csv")
        registros = df.fillna("").to_dict(orient="records")
        meta = {"fuente":"repo_local","ruta":"data/cuadro.csv","timestamp": datetime.utcnow().isoformat()+"Z"}
        return registros, meta
    except Exception as e:
        registros = [
            {"clase":"Metformina","nombre":"Metformina","costo":"$","disp":"alta","renal":"ajuste",
             "notas":"Plena ≥45; 30–44 máx 1000 mg/d; <30 CI.","institucion":"TODAS"}
        ]
        meta = {"fuente":"fallback","ruta":"(mem)","error":str(e)}
        return registros, meta

def filtrar_por_institucion(registros, institucion):
    if institucion == "GENERAL": return registros
    return [r for r in registros if str(r.get("institucion","")).upper() in [institucion, "TODAS"]]

def filtros_disponibilidad_costos(farmacos, disp_ok, costos_ok, egfr):
    res = []
    for f in farmacos:
        if f.get("disp","") not in disp_ok: 
            continue
        if f.get("costo","") not in costos_ok:
            continue
        rcat = f.get("renal","")
        if rcat == "contra" and egfr is not None and egfr < 60: continue
        if rcat == "contra30" and egfr is not None and egfr < 30: continue
        if rcat == "umbral20" and egfr is not None and egfr < 20: continue
        res.append(f)
    return res

# ================== MOTOR DE DECISIONES ADA ==================
FARMACOS = {
    "Metformina": {
        "clase": "Biguanida", "inicio": "500 mg c/12 h con comida", "max": "2000 mg/d",
        "titulacion": "↑ 500 mg cada 1–2 sem según tolerancia",
        "egfr": "≥45 plena; 30–44 máx 1000 mg/d; <30 CI", "renal_min": 30
    },
    "Empagliflozina (SGLT2i)": {
        "clase": "SGLT2i", "inicio": "10 mg/d", "max": "25 mg/d",
        "titulacion": "↑ a 25 mg si tolera y requiere mayor efecto",
        "egfr": "Beneficio renal/CV ≥20; potencia menor <45", "renal_min": 20
    },
    "Dapagliflozina (SGLT2i)": {
        "clase": "SGLT2i", "inicio": "10 mg/d", "max": "10 mg/d",
        "titulacion": "Dosis única; evaluar respuesta",
        "egfr": "Beneficio renal/CV ≥20; potencia menor <45", "renal_min": 20
    },
    "Semaglutida s/c (GLP-1 RA)": {
        "clase": "GLP-1 RA", "inicio": "0.25 mg/sem ×4 sem, luego 0.5 mg/sem",
        "max": "2.0 mg/sem", "titulacion": "↑ cada ≥4 sem según respuesta/tolerancia",
        "egfr": "Sin ajuste; evitar exenatida si eGFR <30", "renal_min": 0
    },
    "Dulaglutida (GLP-1 RA)": {
        "clase": "GLP-1 RA", "inicio": "0.75 mg/sem", "max": "4.5 mg/sem",
        "titulacion": "↑ cada ≥4 sem", "egfr": "Sin ajuste", "renal_min": 0
    },
    "Liraglutida (GLP-1 RA)": {
        "clase": "GLP-1 RA", "inicio": "0.6 mg/d ×1 sem, luego 1.2 mg/d",
        "max": "1.8 mg/d", "titulacion": "↑ cada 1–2 sem", "egfr": "Sin ajuste", "renal_min": 0
    },
    "Linagliptina (DPP-4)": {
        "clase": "DPP-4", "inicio": "5 mg/d", "max": "5 mg/d", "titulacion": "Dosis única",
        "egfr": "Sin ajuste renal", "renal_min": 0
    },
    "Sitagliptina (DPP-4)": {
        "clase": "DPP-4", "inicio": "100 mg/d (eGFR ≥45)", "max": "100 mg/d",
        "titulacion": "50 mg/d si eGFR 30–44; 25 mg/d si <30", "egfr": "Ajuste por eGFR", "renal_min": 0
    },
    "Glipizida (SU)": {
        "clase": "Sulfonilurea", "inicio": "2.5–5 mg/d", "max": "20 mg/d",
        "titulacion": "↑ 2.5–5 mg cada 1–2 sem según glucosa e hipo",
        "egfr": "Preferir en CKD frente a gliburida", "renal_min": 0
    },
    "Pioglitazona (TZD)": {
        "clase": "TZD", "inicio": "15–30 mg/d", "max": "45 mg/d",
        "titulacion": "↑ cada ≥4 sem", "egfr": "Sin ajuste; vigilar edema/IC", "renal_min": 0
    },
    "Glargina U100 (basal)": {
        "clase": "Insulina basal",
        "inicio": "0.1–0.2 U/kg/d o 10 U/d", "max": "— (cuidado >0.5 U/kg/d)",
        "titulacion": "+2 U cada 3 días hasta ayuno 80–130 mg/dL", "renal_min": 0
    },
    "NPH (basal)": {
        "clase": "Insulina basal (NPH)",
        "inicio": "0.2 U/kg/d; 2/3 AM, 1/3 PM", "max": "—",
        "titulacion": "Ajustar según SMBG; vigilar hipo nocturna", "renal_min": 0
    },
    "Aspart/Lispro (prandial)": {
        "clase": "Insulina prandial",
        "inicio": "Bolo 1 comida: 4 U (o 10% basal)", "max": "Escalar a 2 y luego 3 comidas",
        "titulacion": "↑ 1–2 U según PPG o usar ICR/CF (reglas 500/1800)", "renal_min": 0
    },
}

def severidad_por_glicemia(a1c, fpg_mgdl, ppg_mgdl):
    if a1c is None: a1c = 0
    if a1c >= 10: banda = "muy_alta"
    elif a1c >= 9: banda = "alta"
    elif a1c >= 7.5: banda = "moderada"
    else: banda = "leve"
    predominio = "mixto"
    if fpg_mgdl is not None and ppg_mgdl is not None:
        if fpg_mgdl >= 130 and ppg_mgdl <= 180: predominio = "ayuno"
        elif fpg_mgdl < 130 and ppg_mgdl > 180: predominio = "posprandial"
    return banda, predominio

def sugerencias_iniciales(dm, a1c, fpg, ppg, egfr, ascvd, ic, ckd, sintomas_catabolicos, imc):
    banda, predominio = severidad_por_glicemia(a1c, fpg, ppg)
    plan = []; notas = []
    if dm == "DM1":
        return ["Glargina U100 (basal)", "Aspart/Lispro (prandial)"], ["DM1: basal-bolo; educación y conteo de carbohidratos."]
    if sintomas_catabolicos or (fpg is not None and fpg >= 300) or a1c >= 10:
        plan = ["Glargina U100 (basal)"]
        if predominio == "posprandial" or a1c >= 10:
            plan.append("Aspart/Lispro (prandial)")
        notas.append("A1c ≥10% o FPG ≥300 o síntomas catabólicos → iniciar insulina.")
        return plan, notas
    if ic or ckd or ascvd:
        if egfr is None or egfr >= 45:
            plan.append("Metformina")
        if egfr is not None and egfr >= 20:
            plan.append("Empagliflozina (SGLT2i)")
        if ascvd or (imc is not None and imc >= 30):
            plan.append("Semaglutida s/c (GLP-1 RA)")
        return sorted(set(plan), key=plan.index), ["Comorbilidades priorizan SGLT2i/GLP-1 RA; metformina si eGFR lo permite."]
    if banda == "leve":
        plan = ["Metformina"] if egfr is None or egfr >= 45 else []
        if predominio == "posprandial":
            plan += ["Semaglutida s/c (GLP-1 RA)"]
    elif banda == "moderada":
        base = ["Metformina"] if egfr is None or egfr >= 45 else []
        add = ["Semaglutida s/c (GLP-1 RA)"] if (imc is not None and imc >= 30) else ["Empagliflozina (SGLT2i)"]
        plan = base + add
    elif banda == "alta":
        plan = ["Metformina"] if egfr is None or egfr >= 45 else []
        plan += ["Empagliflozina (SGLT2i)"] if predominio == "ayuno" else ["Semaglutida s/c (GLP-1 RA)"]
        plan += ["Linagliptina (DPP-4)"]
    else:
        plan = ["Glargina U100 (basal)"]
    return sorted(set(plan), key=plan.index), [f"Severidad {banda.replace('_',' ')}, patrón {predominio}."]

def texto_dosis_y_titulacion(item, peso_kg):
    info = FARMACOS.get(item, {})
    textos = []
    if "inicio" in info:
        if "U/kg" in str(info["inicio"]):
            textos.append(f"Inicio: {info['inicio']} (≈ {max(10,int(round(0.1*peso_kg)))} U/d).")
        else:
            textos.append(f"Inicio: {info['inicio']}.")
    if "titulacion" in info: textos.append(f"Titulación: {info['titulacion']}.")
    if "max" in info: textos.append(f"Máxima: {info['max']}.")
    if "egfr" in info: textos.append(f"Ajuste renal: {info['egfr']}.")
    return " ".join(textos)

def siguiente_paso(current_meds, a1c_meta, a1c_actual, predominio, egfr, imc):
    current = set(current_meds or [])
    pasos = []
    if "Metformina" in current:
        pasos.append("Si dosis <2000 mg/d y tolera → titular metformina a máxima.")
    if a1c_actual > a1c_meta:
        if "Glargina U100 (basal)" in current:
            if predominio == "posprandial":
                pasos.append("Añadir prandial en 1 comida (4 U) y escalar a 2–3 comidas según PPG/A1c.")
            else:
                pasos.append("Titulación basal: +2 U cada 3 días; si >0.5 U/kg y sin control → prandial o GLP-1 RA.")
        else:
            if predominio == "ayuno":
                pasos.append("Considerar iniciar basal (glargina 0.1–0.2 U/kg/d).")
            else:
                if imc is not None and imc >= 30 and "Semaglutida s/c (GLP-1 RA)" not in current:
                    pasos.append("Añadir GLP-1 RA (semaglutida/dulaglutida) por control PPG y peso.")
                elif "Empagliflozina (SGLT2i)" not in current and (egfr is None or egfr >= 20):
                    pasos.append("Añadir SGLT2i por beneficio CV/renal y glucémico.")
    if not pasos:
        pasos = ["Reforzar adherencia, educación y estilo de vida; reevaluar en 8–12 semanas."]
    return pasos

# PRO – bolos 500/1800
def estimar_tdd(dx, peso_kg, tdd_manual):
    if tdd_manual and tdd_manual > 0: return float(tdd_manual)
    return round((0.5 if dx == "DM1" else 0.3) * peso_kg, 1)

def icr_por_500_rule(tdd): return round(500.0 / tdd, 1) if tdd > 0 else 0.0
def cf_por_1800_rule(tdd): return round(1800.0 / tdd, 0) if tdd > 0 else 0.0

def dosis_bolo(carbs_g, gluc_actual_mgdl, gluc_objetivo_mgdl, icr, cf):
    if gluc_actual_mgdl is not None and gluc_actual_mgdl < 70:
        return 0.0, "Glucosa <70 mg/dL: tratar hipoglucemia y posponer bolo."
    carbo = (carbs_g / icr) if icr > 0 else 0.0
    corr = ((gluc_actual_mgdl - gluc_objetivo_mgdl) / cf) if (gluc_actual_mgdl and cf > 0) else 0.0
    u = max(0.0, carbo + max(0.0, corr))
    u = round(u * 2) / 2.0
    return u, "Bolo = carbo/ICR + corrección; ajustar por actividad física y tendencia de CGM."

# ================== SIDEBAR – Datos del paciente ==================
with st.sidebar:
    st.header("Paciente")
    unidad_gluc = st.selectbox("Unidades de glucosa", ["mg/dL","mmol/L"])
    institucion = st.selectbox("Institución (cuadro básico)", ["GENERAL","IMSS","ISSSTE","IMSS-BIENESTAR","ABC"])
    nombre = st.text_input("Nombre", "")
    edad = st.number_input("Edad (años)", 18, 100, 55)
    sexo = st.selectbox("Sexo biológico", ["Femenino","Masculino"])
    dx = st.selectbox("Diagnóstico", ["DM1","DM2"])
    peso = st.number_input("Peso (kg)", 30.0, 250.0, 80.0, step=0.5)
    talla = st.number_input("Talla (cm)", 120, 220, 170)
    imc_val = bmi(peso, talla); st.write(f"**IMC:** {imc_val if imc_val is not None else 'ND'} kg/m²")
    a1c = st.number_input("A1c (%)", 4.0, 15.0, 8.2, step=0.1)
    gluc_ayunas_in = st.number_input(f"Glucosa en ayunas ({unidad_gluc})",
                                     2.0 if unidad_gluc=='mmol/L' else 50.0,
                                     33.3 if unidad_gluc=='mmol/L' else 600.0,
                                     8.3 if unidad_gluc=='mmol/L' else 150.0)
    gluc_pp_in = st.number_input(f"Glucosa 120 min ({unidad_gluc})",
                                 2.0 if unidad_gluc=='mmol/L' else 50.0,
                                 33.3 if unidad_gluc=='mmol/L' else 600.0,
                                 10.5 if unidad_gluc=='mmol/L' else 190.0)
    gluc_ayunas = to_mgdl(gluc_ayunas_in, unidad_gluc); gluc_pp = to_mgdl(gluc_pp_in, unidad_gluc)
    scr = st.number_input("Creatinina sérica (mg/dL)", 0.2, 12.0, 1.2, step=0.1)
    tiene_ckd = st.checkbox("CKD conocida")
    uacr = st.number_input("UACR (mg/g)", 0.0, 5000.0, 20.0, step=1.0)
    uacr_cat = uacr_categoria(uacr); st.write(f"**Categoría UACR:** {uacr_cat}")
    ascvd = st.checkbox("ASCVD (IAM/angina/ictus/PAD)")
    ic = st.checkbox("Insuficiencia cardiaca")
    sintomas = st.checkbox("Síntomas catabólicos (poliuria, polidipsia, pérdida de peso)")
    riesgo_ipo = st.checkbox("Riesgo elevado de hipoglucemia")
    metas = metas_glicemicas_default(edad)
    st.markdown("### Metas (ajustables)")
    a1c_meta = st.number_input("Meta A1c máx (%)", 5.5, 9.0, metas["A1c_max"], 0.1)
    pre_min = st.number_input(f"Preprandial mín ({unidad_gluc})",
                              3.9 if unidad_gluc=="mmol/L" else 70.0,
                              11.1 if unidad_gluc=="mmol/L" else 200.0,
                              to_unit(metas["pre_min"], unidad_gluc))
    pre_max = st.number_input(f"Preprandial máx ({unidad_gluc})",
                              5.6 if unidad_gluc=="mmol/L" else 100.0,
                              16.7 if unidad_gluc=="mmol/L" else 300.0,
                              to_unit(metas["pre_max"], unidad_gluc))
    pp_max = st.number_input(f"Posprandial máx 1–2h ({unidad_gluc})",
                             6.7 if unidad_gluc=="mmol/L" else 120.0,
                             16.7 if unidad_gluc=="mmol/L" else 300.0,
                             to_unit(metas["pp_max"], unidad_gluc))

# ================== CÁLCULOS INICIALES ==================
egfr = egfr_ckdepi_2021(scr, int(edad), sexo)
registros, meta_fuente = cargar_cuadro_local()
registros = filtrar_por_institucion(registros, institucion)

# ================== TABS PRINCIPALES ==================
tab_over, tab_plan, tab_cat, tab_exports, tab_edu = st.tabs(
    ["🏥 Resumen", "🧪 Plan terapéutico", "💊 Cuadro básico", "🧾 Exportables", "📚 Educación"]
)

# ================== TAB RESUMEN ==================
with tab_over:
    colA, colB, colC = st.columns([1,1,1])
    with colA:
        st.subheader("CKD-EPI 2021")
        st.metric("eGFR estimada", f"{egfr} mL/min/1.73 m²")
        st.caption("Sin raza. Usar tendencia y contexto clínico.")
    with colB:
        st.subheader("Glicemias")
        st.metric("Ayunas", f"{gluc_ayunas_in} {unidad_gluc}")
        st.metric("Posprandial 120 min", f"{gluc_pp_in} {unidad_gluc}")
    with colC:
        st.subheader("Metas activas")
        st.write(f"**A1c** ≤ {a1c_meta}%  ·  **Pre** {pre_min}-{pre_max} {unidad_gluc} · **PP** ≤ {pp_max} {unidad_gluc}")
    st.divider()
    st.write("**Notas rápidas:**")
    st.write("- Ajustar terapia según comorbilidades (ASCVD/IC/CKD), riesgo de hipo, preferencia y disponibilidad.")
    st.write("- Reevaluar control y tolerancia en 8–12 semanas o antes si es necesario.")

# ================== TAB PLAN TERAPÉUTICO ==================
with tab_plan:
    col1, col2 = st.columns([1,1])
    with col1:
        st.subheader("1) Evaluación renal")
        st.metric("eGFR estimada", f"{egfr} mL/min/1.73 m²")
        if egfr < 30:
            st.error("eGFR <30: evitar metformina; considerar GLP-1 RA; SGLT2i sin beneficio glucémico, sí renal/CV.")
        elif egfr < 45:
            st.warning("eGFR 30–44: metformina solo si ya la usaba (máx 1000 mg/d).")
        st.caption("Considerar ACR y nefroprotección.")
    with col2:
        st.subheader("2) Recomendación (ADA – por A1c/FPG/PPG)")
        banda, predominio = severidad_por_glicemia(a1c, gluc_ayunas, gluc_pp)
        plan_inicial, notas_ini = sugerencias_iniciales(dx, a1c, gluc_ayunas, gluc_pp,
                                                        egfr, ascvd, ic, tiene_ckd, sintomas, imc_val or 0)
        st.markdown(f"**Severidad:** {banda.replace('_',' ')} · **Patrón:** {predominio}")
        st.markdown("**Iniciar/optimizar hoy:**")
        for p in plan_inicial:
            st.markdown(f"- **{p}** — {texto_dosis_y_titulacion(p, peso)}")
        if notas_ini:
            st.markdown("**Justificación:**")
            for n in notas_ini: st.markdown(f"• {n}")

    # Insulina (PLUS/PRO)
    st.subheader("2b) Insulina: dosis de inicio y titulación")
    st.write("- Basal: 0.1–0.2 U/kg/d (o 10 U). Titular +2 U cada 3 días hasta ayuno 80–130 mg/dL.")
    st.write("- Si A1c alta con ayuno controlado o basal >0.5 U/kg/d → añadir prandial.")
    if st.session_state["modo"] == "PRO":
        st.markdown("**PRO: Calculadora de bolo (reglas 500/1800)**")
        tdd_manual = st.number_input("TDD si ya usa insulina (opcional) [U/d]", 0.0, 300.0, 0.0, step=1.0)
        tdd = estimar_tdd(dx, peso, tdd_manual); st.caption(f"TDD usada: {tdd} U/d")
        icr = st.number_input("ICR (g/U) – 0 para calcular con 500/TDD", 0.0, 200.0, 0.0, step=0.5)
        cf = st.number_input("CF (mg/dL por 1U) – 0 para 1800/TDD", 0.0, 500.0, 0.0, step=1.0)
        if icr == 0: icr = icr_por_500_rule(tdd)
        if cf == 0: cf = cf_por_1800_rule(tdd)
        colp1, colp2, colp3 = st.columns(3)
        with colp1:
            carbs_g = st.number_input("Carbohidratos (g)", 0.0, 300.0, 45.0, step=1.0)
        with colp2:
            gluc_actual_in = st.number_input(f"Glucosa actual ({unidad_gluc})",
                                             2.0 if unidad_gluc=='mmol/L' else 40.0,
                                             33.3 if unidad_gluc=='mmol/L' else 600.0,
                                             8.9 if unidad_gluc=='mmol/L' else 160.0)
        with colp3:
            gluc_obj_in = st.number_input(f"Glucosa objetivo ({unidad_gluc})",
                                          4.4 if unidad_gluc=='mmol/L' else 80.0,
                                          7.8 if unidad_gluc=='mmol/L' else 140.0,
                                          6.1 if unidad_gluc=='mmol/L' else 110.0)
        u, nota_bolo = dosis_bolo(carbs_g, to_mgdl(gluc_actual_in, unidad_gluc),
                                  to_mgdl(gluc_obj_in, unidad_gluc), icr, cf)
        st.metric("Dosis de bolo sugerida", f"{u} U")
        st.caption(nota_bolo)

    # Asistente de escalamiento
    st.divider()
    st.subheader("3) Escalamiento (según tratamiento actual)")
    opciones_actuales = list(FARMACOS.keys())
    actual_sel = st.multiselect("Medicamentos actuales", opciones_actuales,
                                help="Selecciona lo que el paciente ya usa")
    predominio = severidad_por_glicemia(a1c, gluc_ayunas, gluc_pp)[1]
    pasos = siguiente_paso(actual_sel, a1c_meta, a1c, predominio, egfr, imc_val or 0)
    st.markdown("**Si no alcanza la meta en 8–12 semanas →**")
    for s in pasos: st.markdown(f"- {s}")

# ================== TAB CUADRO BÁSICO ==================
with tab_cat:
    st.caption(f"Fuente: **{meta_fuente['fuente']}** · {meta_fuente.get('ruta','')} · Última lectura: {meta_fuente.get('timestamp','')}")
    st.subheader("Filtrar por disponibilidad y costo")
    disp_sel = st.multiselect("Disponibilidad", ["alta","media","baja"],
                              default=["alta","media","baja"])
    costo_sel = st.multiselect("Costo", ["$","$$","$$$"],
                               default=["$","$$","$$$"])
    catalogo = filtros_disponibilidad_costos(registros, disp_sel, costo_sel, egfr)
    if not catalogo:
        st.warning("No hay fármacos que cumplan los filtros actuales.")
    else:
        df_view = pd.DataFrame(catalogo)[["clase","nombre","costo","disp","notas"]]
        st.dataframe(df_view, use_column_width=True, hide_index=True)

# ================== PDF HELPERS ==================
def _wraplines(c, left, y, width, text, bullet="- "):
    for seg in [text[i:i+95] for i in range(0, len(text), 95)]:
        c.drawString(left, y, f"{bullet}{seg}")
        y -= 14
        if y < 72:
            c.showPage(); y = letter[1] - 72
    return y

def construir_pdf_tratamiento(datos_paciente, recomendaciones, justificacion, sustituciones):
    buffer = BytesIO(); c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter; left = 1 * inch; y = height - 1 * inch
    c.setFont("Helvetica-Bold", 12); c.drawString(left, y, "Plan terapéutico para Diabetes (ADA 2025)"); y -= 20
    c.setFont("Helvetica", 10)
    for k, v in datos_paciente.items():
        y = _wraplines(c, left, y, width, f"{k}: {v}", bullet="")
    y -= 6; c.setFont("Helvetica-Bold", 11); c.drawString(left, y, "Tratamiento indicado:"); y -= 16; c.setFont("Helvetica", 10)
    for line in recomendaciones: y = _wraplines(c, left, y, width, line, bullet="- ")
    y -= 6; c.setFont("Helvetica-Bold", 11); c.drawString(left, y, "Justificación clínica:"); y -= 16; c.setFont("Helvetica", 10)
    for line in justificacion: y = _wraplines(c, left, y, width, line, bullet="• ")
    y -= 6; c.setFont("Helvetica-Bold", 11); c.drawString(left, y, "Alternativas por disponibilidad/costo:"); y -= 16; c.setFont("Helvetica", 10)
    for line in sustituciones: y = _wraplines(c, left, y, width, line, bullet="• ")
    c.setFont("Helvetica-Oblique", 8); y -= 10
    c.drawString(left, y, "Basado en ADA Standards of Care 2025; esta hoja no sustituye el juicio clínico.")
    c.save(); buffer.seek(0); return buffer

def construir_pdf_registro_glucosa(nombre, unidad):
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

def construir_pdf_hoja_alta(nombre, unidad):
    buffer = BytesIO(); c = canvas.Canvas(buffer, pagesize=letter)
    left = 0.7 * inch; top = letter[1] - 0.7 * inch
    c.setFont("Helvetica-Bold", 12); c.drawString(left, top, "Hoja de alta y señales de alarma")
    c.setFont("Helvetica", 10); y = top - 16
    c.drawString(left, y, f"Paciente: {nombre}    Fecha: {date.today().isoformat()}    Unidades: {unidad}"); y -= 16
    secciones = [
        ("Cuidados generales", [
            "Tomar los medicamentos según indicación; no suspender sin consultar.",
            "Monitorear glucosa con la frecuencia indicada; registrar valores.",
            "Mantener hidratación, alimentación balanceada y actividad física segura."
        ]),
        ("Señales de alarma – acudir a urgencias", [
            f"Hipoglucemia severa: glucosa <70 {unidad} con síntomas.",
            f"Hiperglucemia persistente: >300 {unidad} repetida o síntomas de cetoacidosis.",
            "Signos de infección grave, dolor torácico, déficit neurológico, deshidratación marcada."
        ]),
        ("Seguimiento", [
            "Acudir a la próxima cita de control.",
            "Si hay dudas o efectos adversos, contactar a su unidad de salud."
        ])
    ]
    for titulo, items in secciones:
        y -= 10; c.setFont("Helvetica-Bold", 11); c.drawString(left, y, titulo); y -= 14; c.setFont("Helvetica", 10)
        for it in items:
            for seg in [it[i:i+95] for i in range(0, len(it), 95)]:
                c.drawString(left, y, f"• {seg}"); y -= 14
                if y < 72: c.showPage(); y = letter[1] - 72
    c.save(); buffer.seek(0); return buffer

# ================== TAB EXPORTABLES ==================
with tab_exports:
    st.subheader("Exportables en PDF")
    # Construir contenido del plan
    banda, predominio = severidad_por_glicemia(a1c, gluc_ayunas, gluc_pp)
    plan_inicial, notas_ini = sugerencias_iniciales(dx, a1c, gluc_ayunas, gluc_pp,
                                                    egfr, ascvd, ic, tiene_ckd, sintomas, imc_val or 0)
    recs_pdf = [f"{p}: {texto_dosis_y_titulacion(p, peso)}" for p in plan_inicial]
    recs_pdf += ["Insulina basal: 0.1–0.2 U/kg/d; titular +2 U cada 3 días hasta ayuno objetivo."]
    datos = {
        "Nombre": nombre or "—",
        "Edad": f"{edad} años",
        "Sexo": sexo,
        "Diagnóstico": dx,
        "Institución": institucion,
        "Peso/Talla/IMC": f"{peso} kg / {talla} cm / {imc_val if imc_val is not None else 'ND'} kg/m²",
        "A1c": f"{a1c} %",
        "Ayunas": f"{gluc_ayunas_in} {unidad_gluc}",
        "Posprandial 120 min": f"{gluc_pp_in} {unidad_gluc}",
        "Creatinina": f"{scr} mg/dL",
        "eGFR (CKD-EPI 2021)": f"{egfr} mL/min/1.73 m²",
        "UACR": f"{uacr} mg/g ({uacr_cat})",
        "ASCVD/IC": f"{'Sí' if (ascvd or ic) else 'No'}",
        "Modo": st.session_state["modo"],
        "Fecha": date.today().isoformat()
    }
    colE1, colE2, colE3 = st.columns(3)
    with colE1:
        if st.button("🧾 Descargar Plan terapéutico"):
            pdf_bytes = construir_pdf_tratamiento(datos, recs_pdf, notas_ini, [])
            st.download_button("Descargar PDF plan", data=pdf_bytes,
                               file_name="plan_tratamiento_diabetes.pdf", mime="application/pdf")
    with colE2:
        if st.button("📋 Descargar registro de glucosa (7 días)"):
            pdf_reg = construir_pdf_registro_glucosa(nombre or "—", unidad_gluc)
            st.download_button("Descargar registro", data=pdf_reg,
                               file_name="registro_glucosa_capilar.pdf", mime="application/pdf")
    with colE3:
        if st.button("🏥 Descargar hoja de alta"):
            pdf_ha = construir_pdf_hoja_alta(nombre or "—", unidad_gluc)
            st.download_button("Descargar hoja de alta", data=pdf_ha,
                               file_name="hoja_alta_diabetes.pdf", mime="application/pdf")

# ================== TAB EDUCACIÓN ==================
with tab_edu:
    with st.expander("📚 Glosario: mitos y realidades"):
        st.markdown("""
**Mito:** “Si empiezo insulina, ya no hay regreso.”  
**Realidad:** Puede ser temporal o permanente según control y evolución.

**Mito:** “El medicamento daña el riñón.”  
**Realidad:** El mal control glucémico/HTA daña el riñón; algunos fármacos **protegen** (SGLT2i).

**Mito:** “Si me siento bien, puedo dejar el tratamiento.”  
**Realidad:** Puede no haber síntomas hasta complicaciones; la adherencia evita daño.

**Mito:** “El jugo natural no sube la glucosa.”  
**Realidad:** Azúcares libres elevan glucosa; importa porción/frecuencia.

**Mito:** “Todas las sulfonilureas son iguales.”  
**Realidad:** Diferencias de seguridad; en CKD se prefiere **glipizida** sobre gliburida.

**Mito:** “La metformina siempre causa daño.”  
**Realidad:** Segura en eGFR ≥45; 30–44 con dosis reducida; **evitar** si eGFR <30.
""")

st.caption("© 2025 – Herramienta de apoyo clínico. No sustituye el juicio profesional ni las guías oficiales.")
