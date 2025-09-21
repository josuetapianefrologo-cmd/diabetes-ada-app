import pandas as pd

# Aquí en el futuro puedes leer fuentes externas y actualizar el CSV.
# Por ahora solo asegura que el archivo existe y queda limpio.
df = pd.read_csv("data/cuadro.csv")
df.to_csv("data/cuadro.csv", index=False)
print("CSV listo. Registros:", len(df))
