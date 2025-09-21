import streamlit as st
import numpy as np
import pandas as pd
from io import BytesIO
from datetime import date, datetime
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch

st.set_page_config(page_title="Diabetes ADA MX (PLUS/PRO + Cuadro Básico Auto)", page_icon="🩺", layout="wide")

# ===================== Aviso y consentimiento =====================
if "acepta" not in st.session_state:
    st.session_state["acepta"] = False

with st.container():
    if not st.session_state["acepta"]:
        st.title("🩺 Manejo de Diabetes – Herramienta de Apoyo Clínico")
        st.subheader("Aviso de privacidad y descargo de responsabilidad")
        st.markdown("""
**Uso clínico responsable (descargo de responsabilidad):**  
Esta aplicación es una **herramienta de apoyo** basada en resúmenes de guías (ADA/CKD-EPI) y buenas prácticas.
**No sustituye** el juicio clínico, la valoración presencial ni las guías/lineamientos oficiales (federales o institucionales).
La dosificación y selección terapéutica deben personalizarse, verificarse y supervisarse por un profesional de la salud.
En caso de emergencia o signos de alarma, acudir a **urgencias**.

**Privacidad:**  
No almacenamos datos identificables permanentemente en esta demostración. Si imprime/descarga PDFs, verifique que
cumplen las políticas de confidencialidad aplicables (p. ej., NOM de expediente clínico y normativas locales).
""")
        acepto = st.checkbox("He leído y acepto el Aviso de Privacidad y el Descargo de Responsabilidad.")
        if st.button("Ingresar", disabled=not acepto, use_container_width=True):
            st.session_state["acepta"] = True
        st.stop()

# ===================== Modo e interfaz principal =====================
if "modo" not in st.session_state:
    st.session_state["modo"] = "PLUS"

def switch_mode():
    st.session_state["modo"] = "PRO" if st.session_state["modo"] == "PLUS" else "PLUS"

col_mode1, col_mode2, col_mode3 = st.columns([2,1,1])
with col_mode1:
    st.title("🩺 Diabetes ADA MX (PLUS/PRO) con Cuadro Básico **auto-actualizable**")
    st.caption("eGFR CKD-EPI 2021, priorización por comorbilidades, dosificación/bolos, PDFs; cuadro básico por institución actualizado desde este mismo repositorio.")
with col_mode2:
    if st.session_state["modo"] == "PLUS":
        st.button("🔓 Abrir Modo PRO (avanzado)", on_click=switch_mode, use_container_width=True)
    else:
        st.button("⬅️ Volver a Modo PLUS", on_click=switch_mode, use_container_width=True)
with col_mode3:
    modo_basico = st.toggle("🧰 Modo farmacológico básico (Cuadro básico)", value=False, help="Prioriza fármacos de alta disponibilidad/costo bajo y simplifica selectores.")

st.info(f"Modo actual: **{st.session_state['modo']}** | {'🧰 Cuadro básico activo' if modo_basico else 'Cuadro básico inactivo'}")

# ===================== Utilidades =====================
def egfr_ckdepi_2021(scr_mgdl: float, age: int, sex: str) -> float:
    is_female = (sex.lower().startswith("f") or sex.lower().startswith("muj"))
    K = 0.7 if is_female else 0.9
    a = -0.241 if is_female else -0.302
    egfr = 142 * (min(scr_mgdl / K, 1) ** a) * (max(scr_mgdl / K, 1) ** -1.200) * (0.9938 ** age)
    if is_female: egfr *= 1.012
    return float(np.round(egfr, 1))

def metas_glicemicas_default(edad):
    if edad >= 65:
        return {"A1c_max": 7.5, "pre_min": 80, "pre_max": 130, "pp_max": 180}
    else:
        return {"A1c_max": 7.0, "pre_min": 80, "pre_max": 130, "pp_max": 180}

def bmi(kg, cm):
    try:
        m = cm/100.0
        if m <= 0: return None
        return round(kg/(m*m), 1)
    except Exception:
        return None

def uacr_categoria(uacr_mgg):
    try:
        v = float(uacr_mgg)
    except:
        return "ND"
    if v < 30: return "A1 (<30 mg/g)"
    if v < 300: return "A2 (30-299 mg/g)"
    return "A3 (>=300 mg/g)"

# Conversión de unidades
def to_mgdl(value, unidad):
    if value is None: return None
    return float(value) * 18.0 if unidad == "mmol/L" else float(value)

def to_unit(value_mgdl, unidad):
    if value_mgdl is None: return None
    return round(float(value_mgdl)/18.0, 1) if unidad == "mmol/L" else float(value_mgdl)

# ===================== Carga de cuadro básico del MISMO REPO =====================
# El workflow actualiza data/cuadro.csv cada semana (o cuando pulses "Actualizar ahora" en GitHub Actions).
@st.cache_data(ttl=86400)  # 24h
def cargar_cuadro_local():
    try:
        df = pd.read_csv("data/cuadro.csv")
        registros = df.fillna("").to_dict(orient="records")
        meta = {"fuente":"repo_local", "ruta":"data/cuadro.csv", "timestamp": datetime.utcnow().isoformat()+"Z"}
        return registros, meta
    except Exception as e:
        # Fallback mínimo
        registros = [
            {"clase":"Metformina","nombre":"Metformina","costo":"$","disp":"alta","renal":"ajuste","notas":"Plena >=45; 30-44 máx 1000 mg/d; <30 contraindicada.","institucion":"TODAS"}
        ]
        meta = {"fuente":"fallback_embebido","ruta":"(memoria)","error":str(e),"timestamp": datetime.utcnow().isoformat()+"Z"}
        return registros, meta

def filtrar_por_institucion(registros, institucion):
    if institucion == "GENERAL": return registros
    out = [r for r in registros if str(r.get("institucion","")).upper() in [institucion, "TODAS"]]
    return out

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

def sugerir_alternativas(clase_objetivo, lista_filtrada):
    return [f for f in lista_filtrada if f.get("clase","") == clase_objetivo]

# ===================== Reglas terapéuticas y dosificación =====================
def recomendacion_farmacos(tipo_dm, a1c, gluc_ayunas_mgdl, gluc_pp_mgdl, egfr, tiene_ckd, ascvd, ic, imc, uacr_cat):
    lines, just = [], []
    if tipo_dm == "DM1":
        lines.append("DM1: Insulina basal-bolo o sistemas AID; educación y conteo de carbohidratos.")
        if gluc_pp_mgdl is not None and gluc_pp_mgdl > 180:
            lines.append("Ajustar bolo/correcciones para picos posprandiales.")
        just.append("DM1 requiere insulina; no sustituible por orales/incretinas.")
        return lines, just
    if (a1c is not None and a1c > 10) or (gluc_ayunas_mgdl is not None and gluc_ayunas_mgdl >= 300):
        lines.append("Considerar iniciar/optimizar insulina (basal +/- prandial) desde el inicio.")
        just.append("A1c >10% o glucosa >=300 mg/dL o síntomas catabólicos.")
    if ic:
        lines.append("Insuficiencia cardiaca: priorizar SGLT2i.")
        just.append("SGLT2i reduce hospitalizaciones por IC.")
    if ascvd:
        lines.append("ASCVD: preferir GLP-1 RA con beneficio CV o SGLT2i.")
        just.append("Beneficio CV demostrado.")
    if imc is not None and imc >= 30:
        lines.append("Obesidad: preferir GLP-1 RA por efecto en peso.")
        just.append("GLP-1 RA promueve pérdida de peso.")
    if (tiene_ckd or (egfr is not None and egfr < 60)) and egfr is not None:
        if egfr >= 20:
            lines.append("CKD: agregar SGLT2i para protección renal y CV (eGFR >=20).")
            if egfr < 45: just.append("Eficacia glucémica menor <45; combinar GLP-1 RA si requiere control.")
        else:
            lines.append("CKD avanzada: preferir GLP-1 RA si eGFR <20.")
        if uacr_cat in ["A2 (30-299 mg/g)", "A3 (>=300 mg/g)"]:
            lines.append("Albuminuria A2/A3: refuerza uso de SGLT2i; añadir IECA/ARA2 si procede.")
    else:
        if a1c is not None and a1c >= 7.5:
            lines.append("Si no a meta: GLP-1 RA o SGLT2i como adición temprana.")
        else:
            lines.append("Monoterapia (metformina) y hábitos; escalar si no alcanza metas.")
    if egfr is not None:
        if egfr >= 45: lines.append("Metformina: útil y segura con eGFR >=45.")
        elif 30 <= egfr < 45: lines.append("Metformina: si ya la usaba, máx 1000 mg/d; evitar iniciar entre 30-44.")
        else: lines.append("Metformina: CONTRAINDICADA si eGFR <30.")
    if gluc_pp_mgdl is not None and gluc_pp_mgdl > 180:
        lines.append("Foco en posprandial: GLP-1 RA o bolo prandial; ajustar raciones/tiempos.")
    return lines, just

def basal_insulina_inicio(dx, peso_kg, a1c, riesgo_hipo=False):
    if dx == "DM1":
        tdd = round(0.5 * peso_kg, 1)
        basal = round(tdd * 0.5, 1)
        prandial = round(tdd * 0.5 / 3, 1)
        texto = f"TDD ~ {tdd} U/d. Basal ~ {basal} U/d; prandial ~ {prandial} U antes de cada comida."
        reglas = ["Ajustar con SMBG/CGM y conteo de carbohidratos.", "Vigilar hipoglucemias nocturnas."]
        return texto, reglas
    base = max(10, round(0.1 * peso_kg))
    if a1c is not None and a1c >= 9 and not riesgo_hipo:
        base = max(base, round(0.2 * peso_kg))
    texto = f"Iniciar insulina basal en {base} U/d (0.1-0.2 U/kg/d)."
    reglas = [
        "Titular +2 U cada 3 días hasta ayuno 80-130 mg/dL.",
        "Si hipo (<70 mg/dL) bajar 10-20%.",
        "Si A1c alta con ayuno ok o basal >0.5 U/kg/d -> añadir bolo."
    ]
    return texto, reglas

def intensificacion_prandial(basal_ud, peso_kg):
    umbral = round(0.5 * peso_kg, 1)
    inicio = max(4, int(round(basal_ud * 0.1)))
    return [
        f"Si basal > {umbral} U/d o A1c alta con ayuno controlado -> bolo en comida principal: {inicio} U.",
        "Luego 2 comidas; después 3 (basal-bolo).",
        "Alternativa: GLP-1 RA antes del bolo si conviene (peso/adhesión)."
    ]

def ajustes_orales_por_egfr(egfr):
    out = []
    if egfr >= 45: out.append("Metformina: dosis plena si tolera.")
    elif 30 <= egfr < 45: out.append("Metformina: si ya estaba, máx 1000 mg/d; evitar iniciar.")
    else: out.append("Metformina: CONTRAINDICADA (<30).")
    if egfr >= 20: out.append("SGLT2i: indicado en T2D+CKD con eGFR >=20 (beneficio renal/CV). Menor potencia <45.")
    else: out.append("SGLT2i: no iniciar con eGFR <20.")
    if egfr >= 45: out.append("DPP-4: sitagliptina 100 mg/d; linagliptina sin ajuste.")
    elif 30 <= egfr < 45: out.append("DPP-4: sitagliptina 50 mg/d; linagliptina sin ajuste.")
    else: out.append("DPP-4: sitagliptina 25 mg/d; linagliptina sin ajuste.")
    out.append("GLP-1 RA: semaglutida/dulaglutida/liraglutida sin ajuste; evitar exenatida eGFR <30.")
    out.append("SU: preferir glipizida; evitar gliburida (hipoglucemia).")
    out.append("Pioglitazona: sin ajuste renal; vigilar edema/IC.")
    return out

# PRO: Bolos (500/1800)
def estimar_tdd(dx, peso_kg, tdd_manual):
    if tdd_manual and tdd_manual > 0: return float(tdd_manual)
    return round((0.5 if dx == "DM1" else 0.3) * peso_kg, 1)

def icr_por_500_rule(tdd): return round(500.0 / tdd, 1) if tdd > 0 else 0.0
def cf_por_1800_rule(tdd): return round(1800.0 / tdd, 0) if tdd > 0 else 0.0

def dosis_bolo(carbs_g, gluc_actual_mgdl, gluc_objetivo_mgdl, icr, cf):
    if gluc_actual_mgdl is not None and gluc_actual_mgdl < 70:
        return 0.0, "Glucosa <70 mg/dL: tratar hipoglucemia primero; no aplicar bolo ahora."
    carbo = (carbs_g / icr) if icr > 0 else 0.0
    corr = ((gluc_actual_mgdl - gluc_objetivo_mgdl) / cf) if (gluc_actual_mgdl and cf > 0) else 0.0
    u = max(0.0, carbo + max(0.0, corr))
    u = round(u * 2) / 2.0
    nota = "Bolo = carbohidratos/ICR + corrección. Ajustar por actividad física y tendencia de CGM."
    return u, nota

# ===================== Sidebar: unidades, institución =====================
with st.sidebar:
    st.header("Paciente")
    unidad_gluc = st.selectbox("Unidades de glucosa", ["mg/dL","mmol/L"])
    institucion = st.selectbox("Institución para cuadro básico", ["GENERAL","IMSS","ISSSTE","IMSS-BIENESTAR"])
    nombre = st.text_input("Nombre", "")
    edad = st.number_input("Edad (años)", 18, 100, 55)
    sexo = st.selectbox("Sexo biológico", ["Femenino", "Masculino"])
    dx = st.selectbox("Diagnóstico", ["DM1","DM2"])
    peso = st.number_input("Peso (kg)", 30.0, 250.0, 80.0, step=0.5)
    talla = st.number_input("Talla (cm)", 120, 220, 170)
    imc_val = bmi(peso, talla); st.write(f"**IMC:** {imc_val if imc_val is not None else 'ND'} kg/m²")
    a1c = st.number_input("A1c (%)", min_value=4.0, max_value=15.0, value=8.2, step=0.1)
    gluc_ayunas_in = st.number_input(f"Glucosa en ayunas ({unidad_gluc})", 2.0 if unidad_gluc=='mmol/L' else 50.0, 33.3 if unidad_gluc=='mmol/L' else 600.0, 8.3 if unidad_gluc=='mmol/L' else 150.0)
    gluc_pp_in = st.number_input(f"Glucosa 120 min ({unidad_gluc})", 2.0 if unidad_gluc=='mmol/L' else 50.0, 33.3 if unidad_gluc=='mmol/L' else 600.0, 10.5 if unidad_gluc=='mmol/L' else 190.0)
    gluc_ayunas = to_mgdl(gluc_ayunas_in, unidad_gluc); gluc_pp = to_mgdl(gluc_pp_in, unidad_gluc)
    scr = st.number_input("Creatinina sérica (mg/dL)", 0.2, 12.0, 1.2, step=0.1)
    tiene_ckd = st.checkbox("CKD conocida")
    uacr = st.number_input("UACR (mg/g)", 0.0, 5000.0, 20.0, step=1.0)
    uacr_cat = uacr_categoria(uacr); st.write(f"**Categoría UACR:** {uacr_cat}")
    ascvd = st.checkbox("ASCVD (IAM/angina/ictus/PAD)")
    ic = st.checkbox("Insuficiencia cardiaca")
    riesgo_ipo = st.checkbox("Riesgo elevado de hipoglucemia")
    metas = metas_glicemicas_default(edad)
    st.markdown("### Metas (ajustables) – valores ADA típicos")
    a1c_meta = st.number_input("Meta A1c máx (%)", 5.5, 9.0, metas["A1c_max"], 0.1)
    pre_min = st.number_input(f"Preprandial mín ({unidad_gluc})", 3.9 if unidad_gluc=="mmol/L" else 70.0, 11.1 if unidad_gluc=="mmol/L" else 200.0, to_unit(metas["pre_min"], unidad_gluc))
    pre_max = st.number_input(f"Preprandial máx ({unidad_gluc})", 5.6 if unidad_gluc=="mmol/L" else 100.0, 16.7 if unidad_gluc=="mmol/L" else 300.0, to_unit(metas["pre_max"], unidad_gluc))
    pp_max = st.number_input(f"Posprandial máx 1–2h ({unidad_gluc})", 6.7 if unidad_gluc=="mmol/L" else 120.0, 16.7 if unidad_gluc=="mmol/L" else 300.0, to_unit(metas["pp_max"], unidad_gluc))

# ===================== Cargar cuadro básico del repo =====================
registros, meta_fuente = cargar_cuadro_local()
registros = filtrar_por_institucion(registros, institucion)
st.caption(f"Cuadro básico: **{meta_fuente['fuente']}** · {meta_fuente.get('ruta','')} · Última lectura: {meta_fuente.get('timestamp','')}")

# ===================== Filtros de disponibilidad/costo =====================
st.divider()
st.subheader("4) Cuadro básico, disponibilidad y costo")
disp_sel = st.multiselect("Niveles de disponibilidad aceptados", ["alta","media","baja"], default=(["alta","media"] if modo_basico else ["alta","media","baja"]))
costo_sel = st.multiselect("Rango de costo aceptado", ["$","$$","$$$"], default=(["$"] if modo_basico else ["$","$$","$$$"]))

# ===================== Secciones clínicas =====================
col1, col2 = st.columns([1,1])
with col1:
    st.subheader("1) Evaluación renal (CKD-EPI 2021)")
    egfr = egfr_ckdepi_2021(scr, int(edad), sexo)
    st.metric("eGFR estimada", f"{egfr} mL/min/1.73 m²")
    st.info("CKD-EPI 2021 sin raza.")
with col2:
    st.subheader("2) Recomendación terapéutica (ADA – priorización por riesgo)")
    recs, justs = recomendacion_farmacos(dx, a1c, gluc_ayunas, gluc_pp, egfr, tiene_ckd, ascvd, ic, imc_val, uacr_cat)
    for r in recs: st.markdown(f"- {r}")
    st.markdown("**Justificación (resumen):**")
    for j in justs: st.markdown(f"• {j}")

# Insulina
st.subheader("2b) Insulina: dosis de inicio y titulación")
texto_basal, reglas_basal = basal_insulina_inicio(dx, peso, a1c, riesgo_ipo)
st.markdown(f"**Inicio sugerido:** {texto_basal}")
st.markdown("**Titulación:**")
for r in reglas_basal: st.markdown(f"- {r}")

col_basal, col_prand = st.columns(2)
with col_basal:
    basal_analog = st.selectbox("Basal preferida", ["NPH","Glargina U100","Degludec"] if modo_basico else ["NPH","Glargina U100","Glargina U300","Detemir","Degludec"])
with col_prand:
    prand_analog = st.selectbox("Prandial preferida", ["Regular","Aspart","Lispro"] if modo_basico else ["Regular","Aspart","Lispro","Glulisina"])

if dx == "DM2":
    basal_ref = max(10, round(0.1*peso))
    pasos_prandial = intensificacion_prandial(basal_ud=basal_ref, peso_kg=peso)
    st.markdown("**Intensificación prandial (si A1c persiste alta):**")
    for p in pasos_prandial: st.markdown(f"- {p}")

st.subheader("2c) Ajustes por función renal")
for linea in ajustes_orales_por_egfr(egfr): st.markdown(f"- {linea}")

# ===================== Catálogo filtrado y sustituciones =====================
st.divider()
st.subheader("5) Opciones disponibles y sustituciones")
catalogo = filtros_disponibilidad_costos(registros, disp_sel, costo_sel, egfr)
clases = sorted(set([f.get("clase","") for f in catalogo]))
for clase in clases:
    st.markdown(f"**{clase}**")
    subset = [f for f in catalogo if f.get("clase","") == clase]
    for f in subset:
        st.markdown(f"- {f.get('nombre','?')} ({f.get('costo','?')}, disp: {f.get('disp','?')}) — {f.get('notas','')}")

st.markdown("**Alternativas sugeridas por clase objetivo:**")
sustituciones_txt = []
for clave in ["Metformina","SGLT2i","GLP-1 RA","DPP-4","SU","Insulina basal","Insulina prandial","TZD"]:
    opciones = sugerir_alternativas(clave, catalogo)
    if opciones:
        listado = ", ".join([o.get('nombre','?') for o in opciones])
        st.write(f"- {clave}: " + listado)
        sustituciones_txt.append(f"{clave}: {listado}")

# ===================== PRO: Calculadora (opcional) =====================
if st.session_state["modo"] == "PRO":
    st.divider()
    st.subheader("2d) Calculadora de bolo (reglas 500/1800)")
    tdd_manual = st.number_input("TDD (unidades/día) si ya usa insulina (opcional)", 0.0, 300.0, 0.0, step=1.0)
    tdd = estimar_tdd(dx, peso, tdd_manual); st.caption(f"TDD usada: {tdd} U/d (para reglas 500/1800).")
    icr = st.number_input("ICR (g/U) - deja 0 para calcular con 500/TDD", 0.0, 200.0, 0.0, step=0.5)
    cf = st.number_input("CF (mg/dL por 1U) - deja 0 para calcular con 1800/TDD", 0.0, 500.0, 0.0, step=1.0)
    if icr == 0: icr = icr_por_500_rule(tdd)
    if cf == 0: cf = cf_por_1800_rule(tdd)
    colc1, colc2, colc3 = st.columns(3)
    with colc1:
        carbs_g = st.number_input("Carbohidratos de la comida (g)", 0.0, 300.0, 45.0, step=1.0)
    with colc2:
        gluc_actual_in = st.number_input(f"Glucosa actual ({unidad_gluc})", 2.0 if unidad_gluc=='mmol/L' else 40.0, 33.3 if unidad_gluc=='mmol/L' else 600.0, 8.9 if unidad_gluc=='mmol/L' else 160.0)
    with colc3:
        gluc_obj_in = st.number_input(f"Glucosa objetivo ({unidad_gluc})", 4.4 if unidad_gluc=='mmol/L' else 80.0, 7.8 if unidad_gluc=='mmol/L' else 140.0, 6.1 if unidad_gluc=='mmol/L' else 110.0)
    u, nota_bolo = dosis_bolo(carbs_g, to_mgdl(gluc_actual_in, unidad_gluc), to_mgdl(gluc_obj_in, unidad_gluc), icr, cf)
    st.metric("Dosis de bolo sugerida", f"{u} U")
    st.caption(nota_bolo)

# ===================== PDF helpers =====================
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
    c.drawString(left, y, "Basado en ADA Standards of Care 2025; cuadro básico actualizado desde este repositorio; esta hoja no sustituye el juicio clínico.")
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
    c.drawString(left, y, f"Paciente: {nombre}    Fecha: {date.today().isoformat()}    Unidades de glucosa: {unidad}"); y -= 16
    secciones = [
        ("Cuidados generales", [
            "Tomar los medicamentos según indicación y no suspender sin consultar.",
            "Monitorear glucosa con la frecuencia indicada; registrar valores.",
            "Mantener hidratación, alimentación balanceada y actividad física segura."
        ]),
        ("Señales de alarma – acudir a urgencias", [
            f"Hipoglucemia severa: glucosa <70 {unidad} con síntomas o pérdida de conciencia.",
            f"Hiperglucemia persistente: >300 {unidad} repetida o síntomas de cetoacidosis (náusea, vómito, dolor abdominal, respiración rápida, aliento afrutado).",
            "Signos de infección grave: fiebre alta, dolor localizado, enrojecimiento importante, dificultad para respirar.",
            "Dolor torácico, dificultad súbita para hablar o mover una extremidad, alteración del estado de alerta.",
            "Deshidratación marcada, vómito persistente, imposibilidad para ingerir líquidos/alimentos."
        ]),
        ("Contacto y seguimiento", [
            "Acudir a su próxima cita de control en la fecha indicada.",
            "Si hay dudas con el medicamento o efectos adversos, contactar a su unidad de salud."
        ])
    ]
    for titulo, items in secciones:
        y -= 10; c.setFont("Helvetica-Bold", 11); c.drawString(left, y, titulo); y -= 14; c.setFont("Helvetica", 10)
        for it in items:
            for seg in [it[i:i+95] for i in range(0, len(it), 95)]:
                c.drawString(left, y, f"• {seg}"); y -= 14
                if y < 72: c.showPage(); y = letter[1] - 72
    c.save(); buffer.seek(0); return buffer

# ===================== PDFs UI =====================
st.divider(); st.subheader("6) Exportables en PDF")
colA, colB, colC = st.columns(3)
with colA:
    st.markdown("**Plan terapéutico imprimible**")
    if st.session_state["modo"] == "PRO":
        try: tdd_manual; icr; cf; carbs_g; gluc_actual_in; gluc_obj_in; u
        except NameError: tdd_manual=icr=cf=carbs_g=gluc_actual_in=gluc_obj_in=u=0.0
    else:
        tdd_manual=icr=cf=carbs_g=gluc_actual_in=gluc_obj_in=u=0.0
    datos = {
        "Nombre": nombre or "—",
        "Edad": f"{edad} años",
        "Sexo": sexo,
        "Diagnóstico": dx,
        "Institución": institucion,
        "Fuente cuadro": f"{meta_fuente.get('fuente')} ({meta_fuente.get('ruta','')})",
        "Peso/Talla/IMC": f"{peso} kg / {talla} cm / {imc_val if imc_val is not None else 'ND'} kg/m²",
        "A1c": f"{a1c} %",
        "Ayunas": f"{gluc_ayunas_in} {unidad_gluc}",
        "Posprandial 120 min": f"{gluc_pp_in} {unidad_gluc}",
        "Creatinina": f"{scr} mg/dL",
        "eGFR (CKD-EPI 2021)": f"{egfr} mL/min/1.73 m²",
        "UACR": f"{uacr} mg/g ({uacr_cat})",
        "ASCVD": "Sí" if ascvd else "No",
        "IC": "Sí" if ic else "No",
        "Basal": basal_analog,
        "Prandial": prand_analog,
        "Modo": f"{st.session_state['modo']} | {'Cuadro básico' if modo_basico else 'Completo'}",
        "Filtros": f"Disp: {', '.join(disp_sel)} | Costo: {', '.join(costo_sel)}",
        "PRO": f"TDD {tdd_manual} U/d | ICR {icr} g/U | CF {cf} mg/dL/U | Obj {gluc_obj_in} {unidad_gluc} | Bolo {u} U" if st.session_state['modo']=='PRO' else "—",
        "Fecha": date.today().isoformat()
    }
    if st.button("Generar PDF de tratamiento"):
        recs_pdf = recs + [f"Inicio de insulina: {texto_basal}"] + reglas_basal
        if dx == "DM2": recs_pdf += pasos_prandial
        recs_pdf = [f"{x}" for x in recs_pdf] + [f"Análogos elegidos: basal {basal_analog}, prandial {prand_analog}."]
        if st.session_state["modo"] == "PRO":
            recs_pdf += [f"Calculadora PRO: ICR {icr} g/U, CF {cf} mg/dL/U, objetivo {gluc_obj_in} {unidad_gluc}, bolo {u} U."]
        pdf_bytes = construir_pdf_tratamiento(datos, recs_pdf, justs + ajustes_orales_por_egfr(egfr), sustituciones_txt)
        st.download_button("Descargar PDF tratamiento", data=pdf_bytes, file_name="plan_tratamiento_diabetes.pdf", mime="application/pdf")
with colB:
    st.markdown("**Registro de glucosa capilar (7 días)**")
    if st.button("Generar PDF de registro"):
        pdf_reg = construir_pdf_registro_glucosa(nombre or "—", unidad_gluc)
        st.download_button("Descargar PDF registro", data=pdf_reg, file_name="registro_glucosa_capilar.pdf", mime="application/pdf")
with colC:
    st.markdown("**Hoja de alta y señales de alarma**")
    if st.button("Generar PDF de hoja de alta"):
        pdf_ha = construir_pdf_hoja_alta(nombre or "—", unidad_gluc)
        st.download_button("Descargar PDF hoja de alta", data=pdf_ha, file_name="hoja_alta_diabetes.pdf", mime="application/pdf")

# ===================== Glosario educativo =====================
with st.expander("📚 Glosario educativo: mitos y realidades"):
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

st.caption("© 2025 Herramienta de apoyo clínico. Esta app no sustituye el juicio profesional ni las guías oficiales.")
