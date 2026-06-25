import os
import json

# Carpetas y archivos
carpeta_origen = "biblioteca_steam"
archivo_salida = "JuegosSteam.json"

juegos_fusionados = []

print(f"Buscando archivos .json en la carpeta '{carpeta_origen}'...")

# Recorremos la carpeta buscando los JSON
if not os.path.exists(carpeta_origen):
    print(f"Error: No existe la carpeta {carpeta_origen}.")
else:
    for nombre_archivo in os.listdir(carpeta_origen):
        if nombre_archivo.endswith(".json"):
            ruta_completa = os.path.join(carpeta_origen, nombre_archivo)
            try:
                # Abrimos cada archivo y lo agregamos a nuestra lista maestra
                with open(ruta_completa, "r", encoding="utf-8") as f:
                    juego = json.load(f)
                    juegos_fusionados.append(juego)
            except Exception as e:
                print(f"Error al leer {nombre_archivo}: {e}")

    # Guardamos la lista completa en un solo archivo
    with open(archivo_salida, "w", encoding="utf-8") as f:
        json.dump(juegos_fusionados, f, ensure_ascii=False, indent=4)

    print(f"\n¡Éxito! Se fusionaron {len(juegos_fusionados)} juegos en el archivo '{archivo_salida}'.")