"""
Menú interactivo para el buscador de juegos Steam.
Usa sentence-transformers local (sin API key).
Eduardo de Jesús Mancillas García
"""

import json
import os
import sys

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
import chromadb
from sentence_transformers import SentenceTransformer

# CONFIGURACIÓN
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

MONGO_HOST        = "localhost"
MONGO_PORT        = 27017
MONGO_URI         = f"mongodb://{MONGO_HOST}:{MONGO_PORT}/"
DB_NAME           = os.getenv("MONGODB_DATABASE", "steam")
COLLECTION_NAME   = "juegos"
CHROMA_HOST       = "localhost"
CHROMA_PORT       = 8000
CHROMA_COLLECTION = "juegos"
EMBED_MODEL       = "all-MiniLM-L6-v2"
TOP_K             = 5


def build_texto(juego: dict) -> str:
    partes = [juego.get("nombre", "")]
    partes += juego.get("generos", [])
    partes += juego.get("tags", [])
    estudio = juego.get("estudio", [])
    if estudio:
        partes.append(f"Estudio: {', '.join(estudio)}")
    return " ".join(p for p in partes if p)



def conectar_mongo():
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=4000)
        client.admin.command("ping")
        col = client[DB_NAME][COLLECTION_NAME]
        print(f"  MongoDB conectado  ({MONGO_HOST}:{MONGO_PORT} / {DB_NAME})")
        return col
    except ConnectionFailure as e:
        print(f"  MongoDB: {e}")
        sys.exit(1)


def conectar_chroma():
    try:
        client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
        col = client.get_or_create_collection(CHROMA_COLLECTION)
        print(f"  ChromaDB conectado ({CHROMA_HOST}:{CHROMA_PORT})")
        return col
    except Exception as e:
        print(f"  ChromaDB: {e}")
        sys.exit(1)


def buscar_por_nombre(mongo_col, texto: str):
    return list(mongo_col.find(
        {"nombre": {"$regex": texto, "$options": "i"}},
        {"_id": 0},
    ))


def buscar_semantico(chroma_col, model, query: str):
    emb = model.encode(query).tolist()
    resultado = chroma_col.query(
        query_embeddings=[emb],
        n_results=TOP_K,
        include=["metadatas", "distances"],
    )
    juegos = []
    for meta, dist in zip(resultado["metadatas"][0], resultado["distances"][0]):
        similitud = max(0.0, (1 - dist / 2) * 100)
        juegos.append({
            "nombre":    meta.get("nombre"),
            "id":        meta.get("id"),
            "generos":   meta.get("generos", ""),
            "tags":      meta.get("tags", ""),
            "similitud": round(similitud, 1),
        })
    return juegos


def añadir_juego(mongo_col, chroma_col, model):
    print("\n  — Añadir nuevo juego —")
    print("  (deja en blanco los campos opcionales)\n")

    try:
        id_str = input("  ID (número único): ").strip()
        if not id_str.isdigit():
            print("  El ID debe ser un número entero.")
            return
        app_id = int(id_str)

        if mongo_col.find_one({"id": app_id}):
            print(f"  Ya existe un juego con ID {app_id}.")
            return

        nombre = input("  Nombre           : ").strip()
        if not nombre:
            print("  El nombre es obligatorio.")
            return

        generos_str = input("  Géneros (sep. por coma): ").strip()
        tags_str    = input("  Tags    (sep. por coma): ").strip()
        estudio_str = input("  Estudio (sep. por coma): ").strip()
        precio      = input("  Precio (ej: Mex$ 99.99): ").strip() or "N/A"
        fecha       = input("  Fecha de lanzamiento   : ").strip() or "N/A"

        generos = [g.strip() for g in generos_str.split(",") if g.strip()]
        tags    = [t.strip() for t in tags_str.split(",")    if t.strip()]
        estudio = [e.strip() for e in estudio_str.split(",") if e.strip()]

        juego = {
            "id":                app_id,
            "nombre":            nombre,
            "estudio":           estudio,
            "publisher":         [],
            "valoracion":        "0 pos / 0 neg",
            "generos":           generos,
            "tags":              tags,
            "fecha_lanzamiento": fecha,
            "precio":            precio,
            "requerimientos":    {"minimos": "", "recomendados": ""},
            "peso_estimado":     "No especificado",
            "dlcs":              [],
        }

        mongo_col.insert_one({**juego, "_id": app_id})
        print(f"\n  '{nombre}' guardado en MongoDB.")

        texto = build_texto(juego)
        emb   = model.encode(texto).tolist()
        chroma_col.add(
            ids=[str(app_id)],
            embeddings=[emb],
            documents=[texto],
            metadatas=[{
                "nombre":  nombre,
                "id":      app_id,
                "generos": ", ".join(generos),
                "tags":    ", ".join(tags),
            }],
        )
        print(f"  '{nombre}' indexado en ChromaDB.")

    except KeyboardInterrupt:
        print("\n  Cancelado.")


def imprimir_menu():
    print("\n" + "═" * 52)
    print("   Buscador de Juegos Steam")
    print("═" * 52)
    print("  1.  Buscar por nombre")
    print("  2.  Buscar por similitud")
    print("  3.  Añadir juego")
    print("  0.  Salir")
    print("═" * 52)


def main():
    print("\nConectanto...\n")
    mongo_col  = conectar_mongo()
    chroma_col = conectar_chroma()
    print(f"  Cargando modelo de embeddings ({EMBED_MODEL})...")
    model = SentenceTransformer(EMBED_MODEL)
    print(f"  Modelo listo\n")

    while True:
        imprimir_menu()
        opcion = input("  Elige una opcion: ").strip()

        if opcion == "0":
            print("  ¡Adios!\n")
            break

        elif opcion == "1":
            nombre = input("\n  Nombre del juego: ").strip()
            if not nombre:
                continue
            resultados = buscar_por_nombre(mongo_col, nombre)
            if not resultados:
                print(f"\n  Sin resultados para '{nombre}'.")
            else:
                print(f"\n  {len(resultados)} juego(s) encontrado(s):\n")
                for juego in resultados:
                    resumen = {k: v for k, v in juego.items() if k != "requerimientos"}
                    print(json.dumps(resumen, ensure_ascii=False, indent=4))
                    print("  " + "─" * 48)

        elif opcion == "2":
            query = input("\n  Describe qué buscas: ").strip()
            if not query:
                continue
            print("  Buscando...\n")
            try:
                resultados = buscar_semantico(chroma_col, model, query)
                print(f"  Top {TOP_K} resultados para '{query}':\n")
                for i, j in enumerate(resultados, 1):
                    print(f"  {i}. {j['nombre']}  (ID: {j['id']})")
                    print(f"     Similitud: {j['similitud']}%")
                    if j["generos"]:
                        print(f"     Géneros : {j['generos']}")
                    if j["tags"]:
                        print(f"     Tags    : {j['tags']}")
                    print()
            except Exception as e:
                print(f"  Error al buscar: {e}")

        elif opcion == "3":
            añadir_juego(mongo_col, chroma_col, model)

        else:
            print("  Opción no válida.")


if __name__ == "__main__":
    main()