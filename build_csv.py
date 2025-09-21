import pandas as pd

df = pd.read_csv("data/cuadro.csv")
print("Cuadro básico actualizado, total de registros:", len(df))
df.to_csv("data/cuadro.csv", index=False)
