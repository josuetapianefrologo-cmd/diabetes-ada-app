
# Diabetes ADA MX (PLUS/PRO + Cuadro Básico Auto, en el mismo repo)
- App de Streamlit con consentimiento, PLUS/PRO (bolos 500/1800), eGFR CKD-EPI 2021, PDFs (plan/registro/alta), cuadro básico por institución y sustituciones.
- **Auto-actualización** del cuadro básico **dentro del mismo repositorio**:
  - Un workflow de GitHub Actions ejecuta `scripts/build_csv.py` y escribe `data/cuadro.csv`.
  - La app **lee** `data/cuadro.csv` (cacheado 24 h). Al hacer push del workflow, Streamlit redepliega y los usuarios ven los cambios.

## Estructura
```
.
├─ app.py
├─ requirements.txt
├─ data/
│  └─ cuadro.csv              # CSV generado/actualizado por Actions (seeds incluido)
├─ scripts/
│  └─ build_csv.py            # Descarga de fuentes oficiales y genera data/cuadro.csv
└─ .github/workflows/
   └─ cuadro.yml              # Programa la actualización (semanal) y commitea los cambios
```

## Cómo usar
1. Sube este repo a GitHub (público o privado).  
2. Activa **Actions** en tu repo (pestaña "Actions").  
3. (Opcional) Edita `scripts/build_csv.py` para añadir/ajustar fuentes.  
4. La app leerá **data/cuadro.csv**. Si el workflow actualiza el archivo, al hacer push se redepliega Streamlit Cloud.

## Notas
- El script incluye una **semilla** mínima por si fallan las fuentes.  
- Puedes forzar el workflow desde la pestaña **Actions → Run workflow**.
- Streamlit Cloud se redepliega cuando hay un nuevo commit en la rama configurada (main).

