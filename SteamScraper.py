import requests
import json
import time
import os

# =================================================================
# CONFIGURACIÓN
# =================================================================
API_KEY = "8E0DBBA1231BF9B7BD67A31274FDB03F"
STEAM_ID = "76561199175566163"
LIMITE_JUEGOS = 100
CARPETA_SALIDA = "biblioteca_steam"
# =================================================================

def obtener_mis_appids():
    print("-> Obteniendo lista de juegos de tu cuenta...")
    url = f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?key={API_KEY}&steamid={STEAM_ID}&format=json&include_appinfo=true"
    
    try:
        res = requests.get(url).json()
        if "response" in res and "games" in res["response"]:
            return [juego["appid"] for juego in res["response"]["games"]]
        return []
    except Exception as e:
        print(f"Error al conectar con Steam: {e}")
        return []

def get_game_details(app_id):
    store_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&l=spanish&cc=MX"
    spy_url = f"https://steamspy.com/api.php?request=appdetails&appid={app_id}"
    
    try:
        s_res = requests.get(store_url).json()
        spy_res = requests.get(spy_url).json()
        
        if not s_res or str(app_id) not in s_res or not s_res[str(app_id)]['success']:
            return None

        data = s_res[str(app_id)]['data']
        
        requisitos = data.get("pc_requirements", {}).get("minimum", "")
        peso = "No especificado"
        if "GB" in requisitos:
            partes = requisitos.split("GB")
            peso = partes[0].split()[-1] + " GB"

        juego_info = {
            "id": app_id,
            "nombre": data.get("name"),
            "estudio": data.get("developers", []),
            "publisher": data.get("publishers", []),
            "valoracion": f"{spy_res.get('positive', 0)} pos / {spy_res.get('negative', 0)} neg",
            "generos": [g['description'] for g in data.get("genres", [])],
            "tags": list(spy_res.get("tags", {}).keys())[:10],
            "fecha_lanzamiento": data.get("release_date", {}).get("date"),
            "precio": data.get("price_overview", {}).get("final_formatted", "Gratis/N/A"),
            "requerimientos": {
                "minimos": requisitos,
                "recomendados": data.get("pc_requirements", {}).get("recommended", "N/A")
            },
            "peso_estimado": peso,
            "dlcs": []
        }

        if "dlc" in data:
            for dlc_id in data["dlc"][:3]:
                d_url = f"https://store.steampowered.com/api/appdetails?appids={dlc_id}&cc=MX"
                d_res = requests.get(d_url).json()
                if d_res and str(dlc_id) in d_res and d_res[str(dlc_id)]['success']:
                    dd = d_res[str(dlc_id)]['data']
                    juego_info["dlcs"].append({
                        "nombre": dd.get("name"),
                        "fecha": dd.get("release_date", {}).get("date"),
                        "precio": dd.get("price_overview", {}).get("final_formatted", "N/A")
                    })
                time.sleep(1)

        return juego_info
    except:
        return None

def sanitizar_nombre(nombre):
    """Limpia el nombre del juego para usarlo como nombre de archivo."""
    if not nombre:
        return "sin_nombre"
    caracteres_invalidos = r'\/:*?"<>|'
    for c in caracteres_invalidos:
        nombre = nombre.replace(c, "")
    return nombre.strip()[:80]  # Máximo 80 caracteres

def guardar_juego(juego_info, carpeta):
    """Guarda un juego en su propio archivo JSON."""
    nombre_archivo = f"{juego_info['id']}_{sanitizar_nombre(juego_info['nombre'])}.json"
    ruta = os.path.join(carpeta, nombre_archivo)
    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump(juego_info, f, ensure_ascii=False, indent=4)
    return nombre_archivo

def main():
    # Crear carpeta de salida si no existe
    os.makedirs(CARPETA_SALIDA, exist_ok=True)
    print(f"-> Archivos individuales se guardarán en: {os.path.abspath(CARPETA_SALIDA)}/")

    ids = obtener_mis_appids()
    if not ids:
        print("No se pudieron obtener IDs. Revisa tu API Key y que tu perfil sea Público.")
        return

    total_a_procesar = ids[:LIMITE_JUEGOS]
    guardados = 0
    saltados = 0

    print(f"-> Iniciando extracción de {len(total_a_procesar)} juegos...\n")
    
    for i, app_id in enumerate(total_a_procesar):
        print(f"[{i+1}/{len(total_a_procesar)}] Procesando ID: {app_id}...", end=" ", flush=True)
        
        detalle = get_game_details(app_id)
        if detalle:
            nombre_guardado = guardar_juego(detalle, CARPETA_SALIDA)
            print(f"OK -> {nombre_guardado}")
            guardados += 1
        else:
            print("SALTADO")
            saltados += 1
        
        time.sleep(1.5)

    print(f"\n¡LISTO!")
    print(f"  Guardados : {guardados} archivos")
    print(f"  Saltados  : {saltados} juegos")
    print(f"  Carpeta   : {os.path.abspath(CARPETA_SALIDA)}/")

if __name__ == "__main__":
    main()