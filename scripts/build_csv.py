# scripts/build_csv.py
import os
import pandas as pd

os.makedirs("data", exist_ok=True)
csv_path = "data/cuadro.csv"

cols = ["clase","nombre","costo","disp","renal","notas","institucion"]

# Si no existe, crea uno mínimo
if not os.path.exists(csv_path):
    df = pd.DataFrame([{
        "clase":"Metformina","nombre":"Metformina","costo":"$","disp":"alta","renal":"ajuste",
        "notas":"Plena >=45; 30-44 máx 1000 mg/d; <30 contraindicada.","institucion":"TODAS"
    }], columns=cols)
    df.to_csv(csv_path, index=False)
    print("Creado data/cuadro.csv con semilla (1 registro).")
else:
    # Lee y reescribe para normalizar; aquí en futuro puedes actualizar desde fuentes externas
    try:
        df = pd.read_csv(csv_path)
        # Garantiza columnas
        for c in cols:
            if c not in df.columns: df[c] = ""
        df = df[cols]
        df.to_csv(csv_path, index=False)
        print(f"Archivo normalizado. Registros: {len(df)}")
    except Exception as e:
        # Nunca fallar el workflow: deja un CSV mínimo
        df = pd.DataFrame([{
            "clase":"Metformina","nombre":"Metformina","costo":"$","disp":"alta","renal":"ajuste",
            "notas":"Plena >=45; 30-44 máx 1000 mg/d; <30 contraindicada.","institucion":"TODAS"
        }], columns=cols)
        df.to_csv(csv_path, index=False)
        print("Fallback generado por error:", e)

print("OK")
