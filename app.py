# app.py — Diabetes ADA MX (PLUS/PRO + PDFs + Docente)
# © 2025. Herramienta de apoyo clínico (no sustituye juicio profesional ni guías oficiales).

import streamlit as st
import numpy as np
import pandas as pd
from datetime import date, datetime
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch

# ================== CONFIG & THEME ==================
st.set_page_config(page_title="Diabetes ADA MX", page_icon="🩺", layout="wide")
st.markdown("""
<style>
div.block-container { padding-top: 2.75rem; }
:root { --brand:#0b6cff; --ink:#0f172a; --muted:#475569; --soft:#f1f5f9; }
html, body, [class*="css"] { font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, "Helvetica Neue", Arial; }
h1,h2,h3 { letter-spacing:-.2px; }
section[data-testid="stSidebar"] { width:360px !important; }
.badge { background:var(--soft); color:var(--muted); padding:.18rem .5rem; border-radius:.5rem; font-size:.78rem; }
.kpi   { background:var(--soft); border:1px solid #e2e8f0; padding:12px 14px; border-radius:12px; }
hr { border:0; height:1px; background:#e2e8f0; }
</style>
""", unsafe_allow_html=True)

# ================== UTILIDADES MÉDICAS ==================
def egfr_ckdepi_2021(scr_mgdl: float, age: int, sex: str) -> float:
    """CKD-EPI 2021 (mg/dL), sin raza."""
    is_fem = sex.lower().startswith("f")
    K = 0.7 if is_fem else 0.9
    a = -0.241 if is_fem else -0.302
    egfr = 142 * (min(scr_mgdl / K, 1) ** a) * (max(scr_mgdl / K, 1) ** -1.200) * (0.9938 ** age)
    if is_fem: egfr *= 1.012
    return float(np.round(egfr, 1))

def metas_glicemicas_default(edad):
    if edad >= 65:  # meta menos estricta en adultos mayores típicamente
        return {"A1c_max": 7.5, "pre_min": 80, "pre_max": 130, "pp_max": 180}
    else:
        return {"A1c_max": 7.0, "pre_min": 80, "pre_max": 130, "pp_max": 180}

def mmoll_to_mgdl(v):  return None if v is None else round(float(v)*18.0, 1)
def mgdl_to_mmoll(v):  return None if v is None else round(float(v)/18.0, 1)

def bmi(kg, cm):
    try:
        m = cm/100
        return round(kg/(m*m), 1)
    except Exception:
        return None

# ================== CATÁLOGO ADA (resumen práctico) ==================
MEDS = [
    # BIGUANIDA
    dict(clase="Biguanida", nombre="Metformina", forma="tableta",
         inicio="500 mg c/12 h con alimentos",
         paso="↑ 500 mg cada 1–2 semanas según tolerancia GI.",
         max="2000 mg/d (en 2–3 tomas)",
         regla_renal="Iniciar/plena si eGFR ≥45; 30–44 máx 1000 mg/d; <30: contraindicada.",
         clave="metformina"),
    # SGLT2
    dict(clase="SGLT2", nombre="Empagliflozina", forma="tableta",
         inicio="10 mg c/24 h (↑ 25 mg si requiere)",
         paso="Evaluar respuesta a 4–12 sem.",
         max="25 mg/d",
         regla_renal="eGFR ≥20 para protección renal/CV (menor potencia glucémica si eGFR <45).",
         clave="empa"),
    dict(clase="SGLT2", nombre="Dapagliflozina", forma="tableta",
         inicio="10 mg c/24 h",
         paso="No se recomienda >10 mg/d.",
         max="10 mg/d",
         regla_renal="eGFR ≥20 para CKD/IC (potencia glucémica baja si eGFR <45).",
         clave="dapa"),
    dict(clase="SGLT2", nombre="Canagliflozina", forma="tableta",
         inicio="100 mg c/24 h (↑ 300 mg si eGFR lo permite)",
         paso="Titular si necesita más control (según eGFR).",
         max="300 mg/d",
         regla_renal="Dosis según eGFR; revisar guía específica.",
         clave="cana"),
    # DPP-4
    dict(clase="DPP-4", nombre="Linagliptina", forma="tableta",
         inicio="5 mg c/24 h",
         paso="Sin titulación.",
         max="5 mg/d",
         regla_renal="Sin ajuste por eGFR.",
         clave="lina"),
    dict(clase="DPP-4", nombre="Sitagliptina", forma="tableta",
         inicio="100 mg c/24 h",
         paso="eGFR 30–44 → 50 mg; eGFR <30 → 25 mg.",
         max="100 mg/d",
         regla_renal="Ajuste por eGFR como arriba.",
         clave="sita"),
    # GLP-1 RA
    dict(clase="GLP-1 RA", nombre="Semaglutida s.c.", forma="pluma semanal",
         inicio="0.25 mg/sem 4 sem → 0.5 mg/sem (→ 1 mg si requiere)",
         paso="↑ tras 4–8 semanas si no hay náusea/VO.",
         max="1 mg/sem (formulación estándar)",
         regla_renal="Sin ajuste por eGFR; evitar si AE GI severos.",
         clave="sema"),
    dict(clase="GLP-1 RA", nombre="Dulaglutida s.c.", forma="pluma semanal",
         inicio="0.75 mg/sem → 1.5 mg/sem",
         paso="↑ en 4–8 sem.",
         max="1.5 mg/sem",
         regla_renal="Sin ajuste por eGFR.",
         clave="dula"),
    dict(clase="GLP-1 RA", nombre="Liraglutida s.c.", forma="pluma diaria",
         inicio="0.6 mg c/24 h 1 sem → 1.2 mg (→ 1.8 mg si requiere)",
         paso="↑ semanal según tolerancia.",
         max="1.8 mg/d",
         regla_renal="Sin ajuste por eGFR.",
         clave="lira"),
    # SU
    dict(clase="SU", nombre="Glipizida", forma="tableta",
         inicio="2.5–5 mg c/24 h (o c/12 h)",
         paso="↑ 2.5–5 mg cada 1–2 sem según glucosas.",
         max="20 mg/d",
         regla_renal="Preferible en CKD; evitar gliburida.",
         clave="glip"),
    # TZD
    dict(clase="TZD", nombre="Pioglitazona", forma="tableta",
         inicio="15 mg c/24 h (→ 30–45 mg/d)",
         paso="↑ cada 4–8 sem según respuesta y edema.",
         max="45 mg/d",
         regla_renal="Sin ajuste por eGFR; vigilar IC/edema.",
         clave="pio"),
    # INSULINAS
    dict(clase="Insulina basal", nombre="NPH", forma="vial/pluma",
         inicio="DM2: 0.1–0.2 U/kg/d (o 10 U/d) de noche",
         paso="+2 U cada 3 días hasta ayuno 80–130 mg/dL",
         max="Si >0.5 U/kg y A1c alta → añadir prandial",
         regla_renal="Vigilar hipoglucemia; ajustar si CKD.",
         clave="nph"),
    dict(clase="Insulina basal", nombre="Glargina U100", forma="pluma",
         inicio="0.1–0.2 U/kg/d (o 10 U/d)",
         paso="+2 U cada 3 días hasta ayuno meta",
         max=">0.5 U/kg: considerar prandial",
         regla_renal="Ajuste por hipoglucemias/CKD.",
         clave="glarg"),
    dict(clase="Insulina basal", nombre="Degludec", forma="pluma",
         inicio="0.1–0.2 U/kg/d",
         paso="Titulación lenta +2 U cada 3–4 días",
         max=">0.5 U/kg → prandial",
         regla_renal="Menor variabilidad; vigilar hipo.",
         clave="deglu"),
    dict(clase="Insulina prandial", nombre="Regular", forma="vial/pluma",
         inicio="4 U en comida principal o 10% de basal",
         paso="↑ 1–2 U cada 2–3 días según posprandial 2 h",
         max="Depende de glucosas/CHO",
         regla_renal="Ajustar si hipoglucemia.",
         clave="reg"),
    dict(clase="Insulina prandial", nombre="Aspart/Lispro", forma="pluma",
         inicio="4 U comida principal (o conteo CHO/ICR)",
         paso="↑ 1–2 U cada 2–3 días",
         max="Depende de glucosas/CHO",
         regla_renal="Acción rápida; ajustar por hipo.",
         clave="ra"),
]
CAT = pd.DataFrame(MEDS)

def lista_por_clase(clase):
    return CAT.loc[CAT["clase"]==clase, "nombre"].tolist()

# ================== SIDEBAR: PACIENTE ==================
with st.sidebar:
    st.header("Paciente")
    unidad_gluc = st.selectbox("Unidades de glucosa", ["mg/dL","mmol/L"])
    nombre = st.text_input("Nombre", "")
    edad = st.number_input("Edad (años)", 18, 100, 55)
    sexo = st.selectbox("Sexo biológico", ["Femenino","Masculino"])
    dx = st.selectbox("Diagnóstico", ["DM2","DM1"])
    peso = st.number_input("Peso (kg)", 30.0, 250.0, 80.0, step=0.5)
    talla = st.number_input("Talla (cm)", 120, 220, 170)
    imc = bmi(peso, talla)
    st.caption(f"IMC: {imc if imc is not None else 'ND'} kg/m²")
    a1c = st.number_input("A1c (%)", 4.0, 15.0, 8.2, step=0.1)

    ga_in = st.number_input(f"Glucosa en ayunas ({unidad_gluc})",
                             2.0 if unidad_gluc=="mmol/L" else 40.0,
                             33.3 if unidad_gluc=="mmol/L" else 600.0,
                             8.3 if unidad_gluc=="mmol/L" else 150.0)
    pp_in = st.number_input(f"Glucosa 120 min ({unidad_gluc})",
                             2.0 if unidad_gluc=="mmol/L" else 40.0,
                             33.3 if unidad_gluc=="mmol/L" else 600.0,
                             10.5 if unidad_gluc=="mmol/L" else 180.0)
    gluc_ay = mmoll_to_mgdl(ga_in) if unidad_gluc=="mmol/L" else ga_in
    gluc_pp = mmoll_to_mgdl(pp_in) if unidad_gluc=="mmol/L" else pp_in

    scr = st.number_input("Creatinina sérica (mg/dL)", 0.2, 12.0, 1.1, step=0.1)
    egfr = egfr_ckdepi_2021(scr, int(edad), sexo)
    st.markdown(f'<div class="kpi">eGFR (CKD-EPI 2021): <b>{egfr}</b> mL/min/1.73 m²</div>', unsafe_allow_html=True)

    tiene_ckd = st.checkbox("Enfermedad renal crónica (CKD)")
    ascvd = st.checkbox("Enfermedad cardiovascular (IAM/angina/ictus/PAD)")
    ic = st.checkbox("Insuficiencia cardiaca (IC)")

    metas = metas_glicemicas_default(edad)
    st.subheader("Metas ADA (ajustables)")
    a1c_meta = st.number_input("A1c meta (%)", 5.5, 9.0, metas["A1c_max"], 0.1)
    pre_min = st.number_input(f"Preprandial mín ({unidad_gluc})",
                              3.9 if unidad_gluc=="mmol/L" else 70.0,
                              22.2 if unidad_gluc=="mmol/L" else 400.0,
                              mgdl_to_mmoll(metas["pre_min"]) if unidad_gluc=="mmol/L" else metas["pre_min"])
    pre_max = st.number_input(f"Preprandial máx ({unidad_gluc})",
                              5.6 if unidad_gluc=="mmol/L" else 100.0,
                              22.2 if unidad_gluc=="mmol/L" else 400.0,
                              mgdl_to_mmoll(metas["pre_max"]) if unidad_gluc=="mmol/L" else metas["pre_max"])
    pp_max = st.number_input(f"Posprandial máx 1–2 h ({unidad_gluc})",
                              6.7 if unidad_gluc=="mmol/L" else 120.0,
                              22.2 if unidad_gluc=="mmol/L" else 400.0,
                              mgdl_to_mmoll(metas["pp_max"]) if unidad_gluc=="mmol/L" else metas["pp_max"])

# ================== TOP BAR: PLUS/PRO + Docente ==================
if "modo" not in st.session_state: st.session_state["modo"] = "PLUS"
if "docente" not in st.session_state: st.session_state["docente"] = False

top_l, top_r = st.columns([4,2])
with top_l:
    st.session_state["modo"] = st.radio("Modo", ["PLUS","PRO"], horizontal=True,
                                        index=0 if st.session_state["modo"]=="PLUS" else 1,
                                        help="PLUS: guía simplificada | PRO: calculadora 500/1800, etc.")
with top_r:
    st.session_state["docente"] = st.toggle("🧪 Modo docente", value=st.session_state["docente"],
                                            help="Explica por qué y cómo se hacen los cálculos (con fórmulas y bibliografía).")

modo = st.session_state["modo"]
modo_docente = st.session_state["docente"]

st.title("Diabetes ADA MX")
st.caption("eGFR CKD-EPI 2021 · Motor de decisiones ADA · Inicio y titulación de fármacos · Calculadora PRO · PDFs")

# ================== MOTOR DE RECOMENDACIÓN ==================
def plan_terapeutico(dx, a1c, ga, gpp, egfr, ckd, ascvd, ic):
    rec, just = [], []
    if dx == "DM1":
        rec += ["Insulina basal-bolo o sistemas AID; educación y conteo de carbohidratos.",
                "Ajustar correcciones si posprandiales > meta."]
        just += ["DM1 requiere insulina; orales/incretinas no sustituyen insulina."]
        return rec, just

    if (a1c is not None and a1c >= 10) or (ga is not None and ga >= 300):
        rec.append("**Iniciar/optimizar insulina** (basal ± prandial) desde el inicio.")
        just.append("A1c ≥10% o ayunas ≥300 mg/dL o síntomas catabólicos.")
        return rec, just

    if ic:
        rec.append("Priorizar **SGLT2** (empagliflozina/dapagliflozina) por beneficio en IC.")
    if ascvd:
        rec.append("Preferir **GLP-1 RA** (semaglutida/dulaglutida/liraglutida) con beneficio CV.")
    if ckd or egfr < 60:
        if egfr >= 20:
            rec.append("**SGLT2** para protección renal/CV (eGFR ≥20); combinar GLP-1 RA si requiere control.")
        else:
            rec.append("CKD avanzada (eGFR <20): preferir **GLP-1 RA** para control glucémico.")
    if a1c is not None:
        if a1c >= 9:
            rec.append("Terapia dual: **Metformina + (GLP-1 RA o SGLT2)**; valorar basal si síntomas.")
        elif a1c >= 7.5:
            rec.append("Metformina + (GLP-1 RA o SGLT2)** como adición temprana si no a meta.")
        else:
            rec.append("**Monoterapia con Metformina** y hábitos; escalar si no alcanza meta.")
    if gpp is not None and gpp > (pp_max if unidad_gluc=="mg/dL" else mmoll_to_mgdl(pp_max)):
        rec.append("Posprandiales elevadas: considerar **GLP-1 RA** o **bolo prandial**.")
    if egfr >= 45:
        rec.append("Metformina: plena si tolera (eGFR ≥45).")
    elif 30 <= egfr < 45:
        rec.append("Metformina: si ya la usaba, máx 1000 mg/d; evitar iniciar.")
    else:
        rec.append("Metformina **contraindicada** si eGFR <30.")
    return rec, just

st.subheader("Plan terapéutico (ADA) — priorización por riesgo")
recs, justs = plan_terapeutico(dx, a1c, gluc_ay, gluc_pp, egfr, tiene_ckd, ascvd, ic)
c1, c2 = st.columns(2)
with c1:
    for r in recs: st.markdown(f"- {r}")
with c2:
    if justs:
        st.markdown("**Justificación (resumen):**")
        for j in justs: st.markdown(f"• {j}")

# ================== MEDICAMENTOS ACTUALES Y TITULACIÓN ==================
st.subheader("Medicamentos actuales y titulación")
st.caption("Indica lo que usa el paciente para sugerir incremento, dosis máxima o adición de otro agente.")
nombres = CAT["nombre"].tolist()
seleccion = st.multiselect("Medicamentos que usa actualmente", nombres, default=[])

def tip_titulacion(row, egfr, a1c, ga, gpp):
    n, c = row["nombre"], row["clase"]
    out = []
    if row["clave"] == "metformina":
        if egfr < 30:
            out.append("Suspender/evitar: eGFR <30.")
        elif 30 <= egfr < 45:
            out.append("Máx **1000 mg/d** (si ya la usaba).")
        else:
            out.append("Aumentar hasta **2000 mg/d** si tolera GI (en 2–3 tomas).")
        if a1c and a1c > a1c_meta: out.append("Añadir **GLP-1 RA** o **SGLT2** si no a meta.")
    elif row["clave"] in ["empa","dapa","cana"]:
        if egfr >= 20:
            out.append(f"Iniciar/continuar: {row['inicio']} (máx {row['max']}).")
            if egfr < 45: out.append("Potencia glucémica menor con eGFR <45; beneficio renal/CV persiste.")
            if a1c and a1c > a1c_meta: out.append("Combinar con **GLP-1 RA** si requiere más control.")
        else:
            out.append("eGFR <20: priorizar **GLP-1 RA**.")
    elif row["clave"] == "lina":
        out.append("**5 mg c/24 h** (sin ajuste por eGFR).")
    elif row["clave"] == "sita":
        if egfr >= 45: out.append("**100 mg c/24 h**.")
        elif 30 <= egfr < 45: out.append("**50 mg c/24 h**.")
        else: out.append("**25 mg c/24 h**.")
    elif row["clave"] in ["sema","dula","lira"]:
        out.append(f"Escalonar: {row['inicio']} (máx {row['max']}). Vigilar náusea/VO.")
        if gpp and gpp > (pp_max if unidad_gluc=='mg/dL' else mmoll_to_mgdl(pp_max)):
            out.append("Si PP alta pese a GLP-1 RA → considerar **bolo prandial**.")
    elif row["clave"] == "glip":
        out.append("Titular 2.5–5 mg cada 1–2 sem; **máx 20 mg/d**. Vigilar hipoglucemia.")
    elif row["clave"] == "pio":
        out.append("↑ a **30–45 mg/d** si requiere (vigilar edema/IC).")
    elif row["clave"] in ["nph","glarg","deglu"]:
        base = max(10, round(0.1 * peso))
        out += [f"Basal sugerida: **{base} U/d** (0.1–0.2 U/kg).",
                "Titulación: **+2 U cada 3 días** hasta ayuno 80–130 mg/dL.",
                "Si basal >0.5 U/kg y A1c alta → añadir **prandial**."]
    elif row["clave"] in ["reg","ra"]:
        out += ["Inicio: **4 U** en comida principal (o 10% de basal).",
                "↑ 1–2 U cada 2–3 días según PP 2 h."]
    else:
        out.append("Consultar ficha técnica para titulación detallada.")
    return " ".join(out)

if seleccion:
    cA, cB = st.columns([1.2, 1.4])
    with cA:
        st.markdown("**Titulación sugerida por medicamento**")
        for nom in seleccion:
            row = CAT[CAT["nombre"]==nom].iloc[0]
            st.markdown(f"- **{row['nombre']}** ({row['clase']}): {tip_titulacion(row, egfr, a1c, gluc_ay, gluc_pp)}  \n"
                        f"  _Notas_: {row['regla_renal']}")
    with cB:
        st.markdown("**Alternativas por clase (si no disponible/intolerancia)**")
        clases = CAT.loc[CAT["nombre"].isin(seleccion),"clase"].unique().tolist()
        for cl in clases:
            opciones = lista_por_clase(cl)
            alt = st.selectbox(f"Alternativa en **{cl}**", opciones, key=f"alt_{cl}")
            r = CAT[CAT["nombre"]==alt].iloc[0]
            st.caption(f"Sugerencia: {r['inicio']} — Máx {r['max']}. {r['regla_renal']}")
else:
    st.info("Selecciona medicamentos actuales para ver **titulación** y **alternativas**.")

# ================== PRO: CALCULADORA 500/1800 ==================
st.subheader("Modo PRO — Calculadora de bolo (reglas 500/1800)")
st.caption("ICR ≈ 500/TDD (g/U) · CF ≈ 1800/TDD (mg/dL por 1 U). Úsalo como aproximación inicial y ajusta por SMBG/CGM.")
c1, c2, c3 = st.columns(3)
with c1:
    tdd_manual = st.number_input("TDD (U/d) si ya usa insulina (opcional)", 0.0, 300.0, 0.0, step=1.0)
with c2:
    tdd = tdd_manual if tdd_manual>0 else round((0.5 if dx=="DM1" else 0.3) * peso, 1)
    st.write(f"**TDD estimada**: {tdd} U/d")
with c3:
    st.write("")

icr_auto = round(500.0/tdd,1) if tdd>0 else 0.0
cf_auto  = round(1800.0/tdd,0) if tdd>0 else 0.0

colc1, colc2, colc3 = st.columns(3)
with colc1:
    icr = st.number_input("ICR (g/U) — deja 0 para usar 500/TDD", 0.0, 200.0, 0.0, step=0.5)
    if icr==0: icr = icr_auto; st.caption(f"ICR usado: **{icr} g/U**")
with colc2:
    cf = st.number_input("CF (mg/dL por 1 U) — deja 0 para usar 1800/TDD", 0.0, 500.0, 0.0, step=1.0)
    if cf==0: cf = cf_auto; st.caption(f"CF usado: **{cf} mg/dL/U**")
with colc3:
    objetivo = st.number_input(f"Glucosa objetivo ({unidad_gluc})",
                               4.4 if unidad_gluc=="mmol/L" else 80.0,
                               11.1 if unidad_gluc=="mmol/L" else 200.0,
                               6.1 if unidad_gluc=="mmol/L" else 110.0)

cola, colb, colc = st.columns(3)
with cola:
    carbs = st.number_input("Carbohidratos de la comida (g)", 0.0, 300.0, 45.0, step=1.0)
with colb:
    g_actual_in = st.number_input(f"Glucosa actual ({unidad_gluc})",
                                  2.0 if unidad_gluc=='mmol/L' else 40.0,
                                  33.3 if unidad_gluc=='mmol/L' else 600.0,
                                  8.9 if unidad_gluc=='mmol/L' else 160.0)
    g_actual = mmoll_to_mgdl(g_actual_in) if unidad_gluc=="mmol/L" else g_actual_in
with colc:
    g_obj = mmoll_to_mgdl(objetivo) if unidad_gluc=="mmol/L" else objetivo

def dosis_bolo(carbs_g, g_act_mgdl, g_obj_mgdl, icr, cf):
    if g_act_mgdl is not None and g_act_mgdl < 70:
        return 0.0, "Glucosa <70 mg/dL: tratar hipoglucemia primero; no aplicar bolo ahora."
    carbo = (carbs_g / icr) if icr > 0 else 0.0
    corr = ((g_act_mgdl - g_obj_mgdl) / cf) if (g_act_mgdl and cf > 0) else 0.0
    u = max(0.0, carbo + max(0.0, corr))
    u = round(u * 2) / 2.0
    nota = "Bolo = carbohidratos/ICR + corrección (reglas 500/1800). Ajustar por actividad física y tendencia CGM."
    return u, nota

u, nota_bolo = dosis_bolo(carbs, g_actual, g_obj, icr, cf)
st.metric("Dosis de bolo sugerida", f"{u} U")
st.caption(nota_bolo)

# ================== PDFs ==================
def _wraplines(c, left, y, width, text, bullet="- "):
    for seg in [text[i:i+95] for i in range(0, len(text), 95)]:
        c.drawString(left, y, f"{bullet}{seg}"); y -= 14
        if y < 72: c.showPage(); y = letter[1] - 72
    return y

def pdf_plan(datos_paciente, recomendaciones, justificacion, titulaciones):
    buffer = BytesIO(); c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter; L = 1*inch; y = height - 1*inch
    c.setFont("Helvetica-Bold", 12); c.drawString(L, y, "Plan terapéutico para Diabetes (ADA)"); y -= 22
    c.setFont("Helvetica", 10)
    for k, v in datos_paciente.items():
        y = _wraplines(c, L, y, width, f"{k}: {v}", bullet="")
    y -= 6; c.setFont("Helvetica-Bold", 11); c.drawString(L, y, "Recomendaciones:"); y -= 16; c.setFont("Helvetica", 10)
    for line in recomendaciones: y = _wraplines(c, L, y, width, line, bullet="- ")
    y -= 6; c.setFont("Helvetica-Bold", 11); c.drawString(L, y, "Justificación:"); y -= 16; c.setFont("Helvetica", 10)
    for line in justificacion: y = _wraplines(c, L, y, width, line, bullet="• ")
    y -= 6; c.setFont("Helvetica-Bold", 11); c.drawString(L, y, "Titulación y alternativas:"); y -= 16; c.setFont("Helvetica", 10)
    for line in titulaciones: y = _wraplines(c, L, y, width, line, bullet="• ")
    c.setFont("Helvetica-Oblique", 8); y -= 10
    c.drawString(L, y, "Esta hoja no sustituye el juicio clínico. Basado en ADA Standards of Care.")
    c.save(); buffer.seek(0); return buffer

def pdf_registro_glucosa(nombre, unidad):
    buffer = BytesIO(); c = canvas.Canvas(buffer, pagesize=letter)
    L = 0.7*inch; top = letter[1] - 0.7*inch
    c.setFont("Helvetica-Bold", 12); c.drawString(L, top, f"Registro de glucosa capilar (7 días) – Unidades: {unidad}")
    c.setFont("Helvetica", 10); c.drawString(L, top-16, f"Paciente: {nombre or '—'}    Fecha inicio: {date.today().isoformat()}")
    cols = ["Día","Ayunas","Des","Comida","Cena","2h Des","2h Com","2h Cena"]; col_w=[0.8,0.8,0.8,0.8,0.8,0.9,0.9,0.9]
    y = top - 40; c.setFont("Helvetica-Bold", 9)
    for i,h in enumerate(cols): c.drawString(L + sum(col_w[:i])*inch, y, h)
    c.setLineWidth(0.5); y -= 4; c.line(L, y, L + sum(col_w)*inch, y)
    c.setFont("Helvetica", 9)
    for d in range(1,8):
        y -= 18; c.drawString(L, y, f"D{d}")
        for i in range(1,len(cols)): c.drawString(L + sum(col_w[:i])*inch + 4, y, "____")
        c.line(L, y-4, L + sum(col_w)*inch, y-4)
    c.save(); buffer.seek(0); return buffer

def pdf_hoja_alta(nombre, unidad):
    buffer = BytesIO(); c = canvas.Canvas(buffer, pagesize=letter)
    L = 0.7*inch; top = letter[1]-0.7*inch
    c.setFont("Helvetica-Bold", 12); c.drawString(L, top, "Hoja de alta y señales de alarma")
    c.setFont("Helvetica", 10); y = top - 16
    c.drawString(L, y, f"Paciente: {nombre or '—'}    Fecha: {date.today().isoformat()}    Unidades de glucosa: {unidad}"); y -= 16
    secc = [
        ("Cuidados generales", [
            "Tomar los medicamentos según indicación y no suspender sin consultar.",
            "Monitorear glucosa con la frecuencia indicada; registrar valores.",
            "Mantener hidratación, alimentación balanceada y actividad física segura."
        ]),
        ("Señales de alarma – acudir a urgencias", [
            f"Hipoglucemia severa (<70 {unidad} con síntomas o pérdida de conciencia).",
            f"Hiperglucemia persistente: >300 {unidad} repetida o síntomas de cetoacidosis.",
            "Fiebre alta con foco, dificultad respiratoria o dolor torácico.",
            "Déficit neurológico súbito (debilidad, dificultad para hablar).",
            "Vómito persistente, deshidratación marcada."
        ]),
        ("Contacto y seguimiento", [
            "Acudir a su próxima cita de control en la fecha indicada.",
            "Si hay dudas con el medicamento o efectos adversos, contactar a su unidad de salud."
        ])
    ]
    for t, items in secc:
        y -= 10; c.setFont("Helvetica-Bold", 11); c.drawString(L, y, t); y -= 14; c.setFont("Helvetica", 10)
        for it in items:
            for seg in [it[i:i+95] for i in range(0,len(it),95)]:
                c.drawString(L, y, f"• {seg}"); y -= 14
                if y < 72: c.showPage(); y = letter[1] - 72
    c.save(); buffer.seek(0); return buffer

st.subheader("Exportables (PDF)")
colA, colB, colC = st.columns(3)
with colA:
    st.markdown("**Plan terapéutico**")
    # Construimos texto de titulaciones/alternativas si el clínico seleccionó algo
    tit_lines = []
    if seleccion:
        for nom in seleccion:
            row = CAT[CAT["nombre"]==nom].iloc[0]
            tit_lines.append(f"{row['nombre']}: {tip_titulacion(row, egfr, a1c, gluc_ay, gluc_pp)}")
    datos = {
        "Nombre": nombre or "—",
        "Edad/Sexo": f"{edad} · {sexo}",
        "Dx": dx,
        "Peso/Talla/IMC": f"{peso} kg / {talla} cm / {imc if imc is not None else 'ND'} kg/m²",
        "A1c": f"{a1c} %",
        "Ayunas": f"{ga_in} {unidad_gluc}",
        "Posprandial 120 min": f"{pp_in} {unidad_gluc}",
        "Creatinina": f"{scr} mg/dL",
        "eGFR (CKD-EPI 2021)": f"{egfr} mL/min/1.73 m²",
        "ASCVD/IC/CKD": f"{'Sí' if ascvd else 'No'} / {'Sí' if ic else 'No'} / {'Sí' if tiene_ckd else 'No'}",
        "Modo": st.session_state["modo"],
        "Fecha": date.today().isoformat()
    }
    if st.button("Generar PDF plan"):
        pdf = pdf_plan(datos, recs, justs, tit_lines)
        st.download_button("Descargar plan.pdf", data=pdf, file_name="plan_tratamiento_diabetes.pdf", mime="application/pdf")
with colB:
    st.markdown("**Registro de glucosa (7 días)**")
    if st.button("Generar PDF registro"):
        pdf = pdf_registro_glucosa(nombre or "—", unidad_gluc)
        st.download_button("Descargar registro.pdf", data=pdf, file_name="registro_glucosa_capilar.pdf", mime="application/pdf")
with colC:
    st.markdown("**Hoja de alta**")
    if st.button("Generar PDF de alta"):
        pdf = pdf_hoja_alta(nombre or "—", unidad_gluc)
        st.download_button("Descargar alta.pdf", data=pdf, file_name="hoja_alta_diabetes.pdf", mime="application/pdf")

# ================== DOCENTE ==================
if modo_docente:
    st.divider()
    st.header("🧪 Modo Docente")
    st.markdown("""
**¿Por qué estas recomendaciones?**  
Se siguen principios del **ADA Standards of Care** (control individualizado, priorización por riesgo CV/renal, seguridad e hipoglucemia).  
- **CKD-EPI 2021** sin raza para eGFR.  
- **Metas** típicas: A1c <7% (o <7.5% si mayor fragilidad); preprandial 80–130 mg/dL; posprandial 1–2 h <180 mg/dL.  
- **SGLT2** con **beneficio renal/IC** y **GLP-1 RA** con **beneficio CV** son preferentes según comorbilidad.  
- **Insulina basal** cuando A1c ≥10%, glucosa en ayunas ≥300 mg/dL o síntomas catabólicos; o como intensificación.

**Fórmulas y reglas:**
- **CKD-EPI 2021 (mg/dL)**  
  \\[
  eGFR = 142\\cdot \\min(SCr/K,1)^a \\cdot \\max(SCr/K,1)^{-1.200} \\cdot 0.9938^{\\text{edad}} \\cdot (1.012\\,\\text{si mujer})
  \\]  
  con \\(K=0.7\\) mujer, \\(K=0.9\\) hombre; \\(a=-0.241\\) mujer, \\(a=-0.302\\) hombre.
- **Regla 500/1800 (PRO)**  
  - **ICR** (gramos carbohidrato por 1 U): \\(ICR \\approx 500/TDD\\).  
  - **CF** (mg/dL por 1 U): \\(CF \\approx 1800/TDD\\).  
  - **Bolo** = \\(\\frac{\\text{CHO}}{ICR} + \\frac{(G_{act}-G_{obj})}{CF}\\).  
  Ajustar con SMBG/CGM, actividad física y sensibilidad individual.

**Criterios de ajuste:**
- **Basal**: +2 U cada 3 días hasta ayuno 80–130 mg/dL; si >0.5 U/kg/d y A1c alta → añadir prandial.  
- **Prandial**: 4 U en comida principal (o 10% basal), ↑ 1–2 U cada 2–3 días según PP.  
- **Metformina**: plena si eGFR ≥45; 30–44 máx 1000 mg/d; <30 evitar.  
- **DPP-4**: linagliptina sin ajuste; sitagliptina 100/50/25 mg/d según eGFR.  
- **SGLT2**: iniciar si eGFR ≥20 (beneficio renal/CV), potencia glucémica menor si eGFR <45.  
- **GLP-1 RA**: escalonar lento por tolerancia GI; favorecen pérdida de peso.

**Bibliografía (enlaces):**
- ADA. *Standards of Care in Diabetes—2025* (profesionales): https://professional.diabetes.org/standards-of-care  
- ADA en español (diagnóstico y educación): https://diabetes.org/espanol/diagnostico  
- KDIGO & ADA 2022: manejo de diabetes y CKD: https://kdigo.org/guidelines/diabetes-ckd/  
- CKD-EPI 2021 creatinina only: https://www.kidney.org/professionals/kdoqi/gfr_calculator  
- Insulin therapy principles (ADA insulin intensification): busca “ADA insulin intensification basal bolus 2025”.
""")

# ================== EDUCACIÓN (PACIENTE) ==================
st.divider()
st.header("📚 Educación para el paciente")
st.markdown("""
**Objetivos del tratamiento**  
- Mantener glucosas dentro de metas para prevenir **complicaciones** (riñón, corazón, ojos, nervios).  
- Combinar **alimentación saludable**, **actividad física**, **medicación** y **monitoreo**.

**Monitoreo**  
- Si usa **insulina**: medir antes de las comidas y a veces 2 h después; revisar hipoglucemias (<70 mg/dL).  
- Usar **CGM** si está disponible (facilita ajustes y seguridad).  

**Alimentación y actividad**  
- Porciones adecuadas de carbohidratos; preferir fibra, vegetales, granos integrales.  
- Actividad aeróbica moderada ≥150 min/semana y entrenamiento de fuerza ≥2 días/semana (salvo indicación médica).

**Medicamentos: puntos clave**  
- **Metformina** puede causar malestar GI; tomar con comida y titular lentamente.  
- **SGLT2**: hidratación adecuada, avisar si hay infección genital o síntomas de cetosis.  
- **GLP-1 RA**: náusea al inicio es común; suele mejorar en 1–2 semanas.  
- **Insulina**: rotar sitios, reconocer hipoglucemia (temblor, sudor, confusión) y tratar de inmediato.

**Enlaces confiables**  
- ADA para pacientes (español): https://diabetes.org/es  
- Etiqueta de alimentos y carbohidratos: https://www.cdc.gov/diabetes/managing/healthy-eating.html  
""")

# ================== TABLA DEL CATÁLOGO ==================
st.divider()
st.subheader("Catálogo completo (consulta rápida)")
tabla = CAT[["clase","nombre","forma","inicio","max","regla_renal"]].rename(columns={
    "clase":"Clase","nombre":"Medicamento","forma":"Forma","inicio":"Inicio sugerido","max":"Dosis máxima","regla_renal":"Notas clave"
})
st.dataframe(tabla, use_container_width=True, hide_index=True)

# ================== DISCLAIMER ==================
st.markdown("""
<br>
<div class="badge">© 2025 – Herramienta de apoyo clínico.</div>
Esta app **no sustituye** el juicio profesional ni las guías oficiales. Personalice metas, combinaciones y titulación según el paciente.
""", unsafe_allow_html=True)
