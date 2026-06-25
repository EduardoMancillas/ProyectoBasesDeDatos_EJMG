"""
mongo2chroma.py
---------------
Lee todos los juegos de MongoDB y los indexa en ChromaDB
usando embeddings locales (sentence-transformers, sin API key).

Uso:
    python mongo2chroma.py
    python mongo2chroma.py --reset   # Borra la colección antes de importar
"""

import argparse
import os
import sys

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
import chromadb
from sentence_transformers import SentenceTransformer

# =================================================================
# CONFIGURACIÓN
# =================================================================
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
# =================================================================


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
        print(f"MongoDB conectado  ({MONGO_HOST}:{MONGO_PORT} / {DB_NAME})")
        return col
    except ConnectionFailure as e:
        print(f"MongoDB no disponible: {e}")
        sys.exit(1)


def conectar_chroma():
    try:
        client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
        print(f"ChromaDB conectado ({CHROMA_HOST}:{CHROMA_PORT})")
        return client
    except Exception as e:
        print(f"ChromaDB no disponible: {e}")
        sys.exit(1)


def migrar(reset: bool = False):
    print("\n═══════════════════════════════════════")
    print("  mongo2chroma — Migración local       ")
    print("═══════════════════════════════════════\n")

    mongo_col     = conectar_mongo()
    chroma_client = conectar_chroma()

    print(f"  Cargando modelo de embeddings ({EMBED_MODEL})...")
    model = SentenceTransformer(EMBED_MODEL)
    print(f"  Modelo cargado\n")

    if reset:
        try:
            chroma_client.delete_collection(CHROMA_COLLECTION)
            print(f"  Colección '{CHROMA_COLLECTION}' eliminada (--reset).")
        except Exception:
            pass

    collection = chroma_client.get_or_create_collection(CHROMA_COLLECTION)

    existing_ids = set(collection.get(include=[])["ids"])
    print(f"  IDs ya en ChromaDB : {len(existing_ids)}")

    juegos = list(mongo_col.find({}, {"_id": 0}))
    print(f"  Juegos en MongoDB  : {len(juegos)}")

    pendientes = [j for j in juegos if str(j["id"]) not in existing_ids]
    print(f"  Juegos a migrar    : {len(pendientes)}\n")

    if not pendientes:
        print("  Nada que migrar. ChromaDB ya está al día.")
        return

    total   = len(pendientes)
    ok      = 0
    errores = 0

    for i, juego in enumerate(pendientes, 1):
        try:
            texto = build_texto(juego)
            emb   = model.encode(texto).tolist()

            collection.add(
                ids=[str(juego["id"])],
                embeddings=[emb],
                documents=[texto],
                metadatas=[{
                    "nombre":  juego.get("nombre", ""),
                    "id":      int(juego["id"]),
                    "generos": ", ".join(juego.get("generos", [])),
                    "tags":    ", ".join(juego.get("tags", [])),
                }],
            )
            ok += 1
            print(f"  [{i}/{total}] {juego['nombre']}")
        except Exception as e:
            errores += 1
            print(f"  [{i}/{total}] {juego.get('nombre', '?')} — {e}")

    print(f"\n  Migrados        : {ok}")
    print(f"  Errores         : {errores}")
    print(f"  Total en ChromaDB : {collection.count()}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Borra la colección antes de migrar.")
    args = parser.parse_args()
    migrar(reset=args.reset)
