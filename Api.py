"""Api.py
--------
API HTTP (FastAPI) para consultar la biblioteca de Steam.
Eduardo de Jesús Mancillas García
"""

import os
import sys
import json
from functools import lru_cache

from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from jwt import PyJWTError
from pydantic import BaseModel, Field
import redis
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
import chromadb
import requests
from sentence_transformers import SentenceTransformer

# =================================================================
# CONFIGURACIÓN 
# =================================================================
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

MONGO_HOST = os.getenv("MONGO_HOST", "localhost")
MONGO_PORT = int(os.getenv("MONGO_PORT", 27017))
MONGO_URI = f"mongodb://{MONGO_HOST}:{MONGO_PORT}/"
DB_NAME = os.getenv("MONGODB_DATABASE", "steam")
COLLECTION_NAME = "juegos"
CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", 8000))
CHROMA_COLLECTION = "juegos"
EMBED_MODEL = "all-MiniLM-L6-v2"
TOP_K = 5
STEAM_API_KEY = os.getenv("STEAMWORKS_API_KEY") or os.getenv("STEAM_API_KEY")

from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from passlib.context import CryptContext
import jwt
from datetime import datetime, timedelta

# =================================================================
# CONFIGURACIÓN DE POSTGRESQL (Para los usuarios - Requisito 1 y 4)
# =================================================================
SQLALCHEMY_DATABASE_URL = os.getenv(
    "SQLALCHEMY_DATABASE_URL", 
    "postgresql://sail:password@localhost:5432/TrabajoMongo"
)

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Equivalente a User de Laravel
class UserSQL(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    password = Column(String)

# Crear las tablas en PostgreSQL si no existen
Base.metadata.create_all(bind=engine)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = "Password"

# =================================================================
# INICIALIZACIÓN DE FASTAPI Y REDIS
# =================================================================
app = FastAPI(
    title="GeForce Now API",
    description="API para gestionar sesiones y juegos con MongoDB, Redis y SQL.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Conexión a Redis 
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
redis_client = redis.Redis(host=REDIS_HOST, port=6379, db=0, decode_responses=True)

# =================================================================
# MODELOS DE VALIDACIÓN
# =================================================================
class JuegoBase(BaseModel):
    nombre: str = Field(..., min_length=1, description="Nombre del juego")
    estudio: list[str] = []
    publisher: list[str] = []
    valoracion: str = "0 pos / 0 neg"
    generos: list[str] = []
    tags: list[str] = []
    fecha_lanzamiento: str = "N/A"
    precio: str = "N/A"
    requerimientos: dict = {"minimos": "", "recomendados": ""}
    peso_estimado: str = "No especificado"
    dlcs: list = []

class JuegoCreate(JuegoBase):
    id: int = Field(..., description="ID único del juego (AppID)")
    steam_id: str | None = None

# Validación para ACTUALIZAR un juego (Punto 8)
class JuegoUpdate(JuegoBase):
    pass  # Reutiliza la misma estructura de campos válidos que JuegoBase

# Modelos para gestionar las Sesiones en MongoDB (Punto 3 y 8)
class SesionBase(BaseModel):
    usuario_id: int = Field(..., description="ID del usuario obtenido de PostgreSQL")
    juego_id: int = Field(..., description="AppID del juego en MongoDB")
    plataforma: str = Field(..., min_length=2, description="Dispositivo (ej: PC, Android, TV)")
    duracion_minutos: int = Field(0, ge=0, description="Duración de la sesión en minutos")

class SesionCreate(SesionBase):
    id: str = Field(..., min_length=3, description="ID único alfanumérico para la sesión")

class SesionUpdate(BaseModel):
    plataforma: str | None = Field(None, min_length=2)
    duracion_minutos: int | None = Field(None, ge=0)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")

def verificar_token(token: str = Depends(oauth2_scheme)):
    try:
        # Intentamos decodificar el token con tu SECRET_KEY
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Token inválido: No se encontró el usuario.")
        return {"email": email}
    except PyJWTError:
        raise HTTPException(status_code=401, detail="Token expirado o inválido.")

# =================================================================
# VALIDACIONES (Equivalente a RegisterRequest.php y LoginRequest.php)
# =================================================================
class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    email: str
    password: str = Field(..., min_length=8)

class LoginRequest(BaseModel):
    email: str
    password: str

class SteamImportRequest(BaseModel):
    steam_id: str
    api_key: str | None = None
    limite: int = 100

# =================================================================
# AUTH CONTROLLER
# =================================================================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def crear_token_acceso(data: dict):
    # Equivalente a createToken('auth_token')->plainTextToken
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=7)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm="HS256")

def get_sesiones_col():
    client = MongoClient(MONGO_URI)
    return client[DB_NAME]["sesiones"]

@app.post("/api/register", status_code=201)
def register(request: RegisterRequest, db = Depends(get_db)):
    # 1. Validar si el email ya existe (unique:users,email)
    user_exists = db.query(UserSQL).filter(UserSQL.email == request.email).first()
    if user_exists:
        raise HTTPException(status_code=400, detail="El correo ya está registrado.")
    
    # 2. Crear usuario con contraseña encriptada (Hash::make)
    hashed_password = pwd_context.hash(request.password)
    nuevo_usuario = UserSQL(name=request.name, email=request.email, password=hashed_password)
    db.add(nuevo_usuario)
    db.commit()
    db.refresh(nuevo_usuario)
    
    # 3. Generar token
    token = crear_token_acceso({"sub": nuevo_usuario.email})
    
    return {
        "data": {"id": nuevo_usuario.id, "name": nuevo_usuario.name, "email": nuevo_usuario.email},
        "token": token,
        "type": "Bearer"
    }

@app.post("/api/login")
def login(request: LoginRequest, db = Depends(get_db)):
    # 1. Buscar usuario
    user = db.query(UserSQL).filter(UserSQL.email == request.email).first()
    
    # 2. Verificar credenciales (Hash::check)
    if not user or not pwd_context.verify(request.password, user.password):
        raise HTTPException(status_code=401, detail="Las credenciales proporcionadas son incorrectas.")
    
    # 3. Generar token
    token = crear_token_acceso({"sub": user.email})
    
    return {
        "data": {"id": user.id, "name": user.name, "email": user.email},
        "token": token,
        "type": "Bearer"
    }


# =================================================================
# FUNCIONES DE CONEXIÓN
# =================================================================
def conectar_mongo():
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=4000)
        client.admin.command("ping")
        return client[DB_NAME][COLLECTION_NAME]
    except ConnectionFailure as e:
        print(f"MongoDB no disponible: {e}")
        sys.exit(1)

def conectar_chroma():
    try:
        client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
        return client.get_or_create_collection(CHROMA_COLLECTION)
    except Exception as e:
        print(f"ChromaDB no disponible: {e}")
        sys.exit(1)

@lru_cache(maxsize=1)
def get_model():
    return SentenceTransformer(EMBED_MODEL)

@lru_cache(maxsize=1)
def get_mongo_col():
    return conectar_mongo()

@lru_cache(maxsize=1)
def get_chroma_col():
    return conectar_chroma()

def build_texto(juego: dict) -> str:
    partes = [juego.get("nombre", "")]
    partes += juego.get("generos", [])
    partes += juego.get("tags", [])
    estudio = juego.get("estudio", [])
    if estudio:
        partes.append(f"Estudio: {', '.join(estudio)}")
    return " ".join(parte for parte in partes if parte)


@app.get("/api/health")
def health():
    try:
        mongo_col = get_mongo_col()
        chroma_col = get_chroma_col()
        return {
            "status": "ok",
            "mongo": {"database": DB_NAME, "collection": COLLECTION_NAME, "connected": True},
            "chroma": {"collection": CHROMA_COLLECTION, "connected": True, "count": chroma_col.count()},
            "total_mongo": mongo_col.count_documents({}),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/juegos")
def api_buscar_nombre(nombre: str = Query("", description="Nombre a buscar")):
    cache_key = f"juegos_search_{nombre}"
    cached_data = redis_client.get(cache_key)
    
    if cached_data:
        return {"source": "redis", "count": len(json.loads(cached_data)), "results": json.loads(cached_data)}

    # 2. Si no está en caché, consulta a MongoDB
    mongo_col = get_mongo_col()
    if nombre:
        juegos = list(mongo_col.find({"nombre": {"$regex": nombre, "$options": "i"}}, {"_id": 0}))
    else:
        juegos = list(mongo_col.find({}, {"_id": 0}))

    # 3. Guardar resultado en Redis por 60 segundos
    redis_client.setex(cache_key, 60, json.dumps(juegos))

    return {"source": "mongodb", "count": len(juegos), "results": juegos}

@app.post("/api/juegos/steam/importar")
def api_importar_steam(req: SteamImportRequest):
    # Usamos la llave que manda el usuario o la del .env
    key = req.api_key or STEAM_API_KEY
    if not key:
        raise HTTPException(status_code=400, detail="No se proporcionó API Key de Steam.")

    # 1. Obtener los IDs de Steam
    url_owned = f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?key={key}&steamid={req.steam_id}&format=json"
    try:
        res = requests.get(url_owned).json()
        if "response" not in res or "games" not in res["response"]:
            raise HTTPException(status_code=404, detail="No se encontraron juegos o el perfil es privado.")
        app_ids = [juego["appid"] for juego in res["response"]["games"]][:req.limite]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error conectando a Steam: {e}")

    mongo_col = get_mongo_col()
    chroma_col = get_chroma_col()
    model = get_model()

    importados = 0
    saltados = 0

    # 2. Procesar cada juego
    for app_id in app_ids:
        # Si ya existe en Mongo, lo saltamos
        if mongo_col.find_one({"id": app_id}):
            saltados += 1
            continue
            
        store_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&l=spanish"
        try:
            s_res = requests.get(store_url).json()
            if not s_res or str(app_id) not in s_res or not s_res[str(app_id)]['success']:
                saltados += 1
                continue

            data = s_res[str(app_id)]['data']
            
            nuevo_juego = {
                "id": app_id,
                "nombre": data.get("name", "Desconocido"),
                "estudio": data.get("developers", []),
                "generos": [g['description'] for g in data.get("genres", [])],
                "tags": [], # Simplificado para no saturar APIs de terceros
            }

            # Guardar en Mongo
            mongo_col.insert_one({**nuevo_juego, "_id": app_id})

            # Guardar en ChromaDB
            texto = build_texto(nuevo_juego)
            emb = model.encode(texto).tolist()
            chroma_col.add(
                ids=[str(app_id)],
                embeddings=[emb],
                documents=[texto],
                metadatas=[{
                    "nombre": nuevo_juego["nombre"],
                    "id": app_id,
                    "generos": ", ".join(nuevo_juego["generos"])
                }],
            )
            importados += 1
        except Exception:
            saltados += 1

    # Invalidad caché
    redis_client.delete("juegos_search_")

    return {
        "steam_id": req.steam_id,
        "total_encontrados": len(app_ids),
        "importados": importados,
        "saltados": saltados
    }

@app.get("/api/juegos/{app_id}")
def api_juego_por_id(app_id: int):
    # También añadimos Redis a esta consulta específica
    cache_key = f"juego_{app_id}"
    cached_data = redis_client.get(cache_key)
    if cached_data:
        return {"source": "redis", "result": json.loads(cached_data)}

    mongo_col = get_mongo_col()
    juego = mongo_col.find_one({"id": app_id}, {"_id": 0})

    if not juego:
        raise HTTPException(status_code=404, detail="Juego no encontrado")

    redis_client.setex(cache_key, 120, json.dumps(juego))
    return {"source": "mongodb", "result": juego}

@app.post("/api/juegos", status_code=201)
def api_crear_juego(juego: JuegoCreate, usuario = Depends(verificar_token)):
    mongo_col = get_mongo_col()
    chroma_col = get_chroma_col()
    model = get_model()

    if mongo_col.find_one({"id": juego.id}):
        raise HTTPException(status_code=409, detail=f"Ya existe un juego con ID {juego.id}")

    # Guardar en Mongo
    nuevo_juego = juego.model_dump()
    mongo_col.insert_one({**nuevo_juego, "_id": juego.id})

    # Guardar en ChromaDB
    texto = build_texto(nuevo_juego)
    emb = model.encode(texto).tolist()
    chroma_col.add(
        ids=[str(juego.id)],
        embeddings=[emb],
        documents=[texto],
        metadatas=[{
            "nombre": juego.nombre,
            "id": juego.id,
            "steam_id": juego.steam_id or "",
            "generos": ", ".join(juego.generos),
            "tags": ", ".join(juego.tags),
        }],
    )

    # INVALIDAR CACHE: Si añadimos un juego, el caché viejo ya no sirve
    redis_client.delete("juegos_search_")

    return {"mensaje": "Juego creado exitosamente", "data": nuevo_juego}

@app.get("/api/buscar/semantico")
def api_buscar_semantico(q: str = Query(..., description="Término a buscar"), top_k: int = 5):
    chroma_col = get_chroma_col()
    model = get_model()
    
    emb = model.encode(q).tolist()
    resultado = chroma_col.query(
        query_embeddings=[emb],
        n_results=top_k,
        include=["metadatas", "distances"],
    )

    juegos = []
    metadatas = resultado.get("metadatas", [[]])[0]
    distances = resultado.get("distances", [[]])[0]
    for meta, dist in zip(metadatas, distances):
        similitud = max(0.0, (1 - dist / 2) * 100)
        juegos.append({
            "nombre": meta.get("nombre"),
            "id": meta.get("id"),
            "generos": meta.get("generos", ""),
            "tags": meta.get("tags", ""),
            "similitud": round(similitud, 1),
        })

    return {"query": q, "count": len(juegos), "results": juegos}

@app.put("/api/juegos/{app_id}", status_code=200)
def api_actualizar_juego(app_id: int, juego: JuegoUpdate, usuario = Depends(verificar_token)):
    mongo_col = get_mongo_col()
    chroma_col = get_chroma_col()
    model = get_model()

    juego_existente = mongo_col.find_one({"id": app_id})
    if not juego_existente:
        raise HTTPException(status_code=404, detail=f"No se encontró ningún juego con ID {app_id}")

    # 1. Actualizar en MongoDB
    datos_actualizados = juego.model_dump()
    mongo_col.update_one({"id": app_id}, {"$set": datos_actualizados})

    # 2. Actualizar en ChromaDB (Búsqueda Semántica)
    texto = build_texto(datos_actualizados)
    emb = model.encode(texto).tolist()
    chroma_col.update(
        ids=[str(app_id)],
        embeddings=[emb],
        documents=[texto],
        metadatas=[{
            "nombre": juego.nombre,
            "id": app_id,
            "generos": ", ".join(juego.generos),
            "tags": ", ".join(juego.tags),
        }],
    )

    # 3. Invalidar el Caché viejo en Redis
    redis_client.delete(f"juego_{app_id}")
    redis_client.delete("juegos_search_")

    return {"mensaje": "Juego actualizado exitosamente en todos los sistemas", "data": datos_actualizados}


@app.delete("/api/juegos/{app_id}", status_code=200)
def api_eliminar_juego(app_id: int, usuario = Depends(verificar_token)):
    mongo_col = get_mongo_col()
    chroma_col = get_chroma_col()

    juego_existente = mongo_col.find_one({"id": app_id})
    if not juego_existente:
        raise HTTPException(status_code=404, detail=f"No se encontró ningún juego con ID {app_id}")

    # 1. Eliminar de MongoDB
    mongo_col.delete_one({"id": app_id})

    # 2. Eliminar de ChromaDB
    chroma_col.delete(ids=[str(app_id)])

    # 3. Eliminar de Redis
    redis_client.delete(f"juego_{app_id}")
    redis_client.delete("juegos_search_")

    return {"mensaje": f"Juego con ID {app_id} eliminado correctamente de la infraestructura"}

@app.post("/api/sesiones", status_code=201)
def crear_sesion(sesion: SesionCreate, usuario = Depends(verificar_token)):
    col = get_sesiones_col()
    if col.find_one({"id": sesion.id}):
        raise HTTPException(status_code=409, detail="El ID de sesión ya está registrado.")
    
    nueva_sesion = sesion.model_dump()
    col.insert_one({**nueva_sesion, "_id": sesion.id})
    return {"mensaje": "Sesión creada exitosamente", "data": nueva_sesion}


@app.get("/api/sesiones", status_code=200)
def listar_sesiones(usuario = Depends(verificar_token)):
    col = get_sesiones_col()
    return list(col.find({}, {"_id": 0}))


@app.get("/api/sesiones/{sesion_id}", status_code=200)
def obtener_sesion(sesion_id: str, usuario = Depends(verificar_token)):
    col = get_sesiones_col()
    sesion = col.find_one({"id": sesion_id}, {"_id": 0})
    if not sesion:
        raise HTTPException(status_code=404, detail="Sesión no encontrada.")
    return sesion


@app.put("/api/sesiones/{sesion_id}", status_code=200)
def actualizar_sesion(sesion_id: str, req: SesionUpdate, usuario = Depends(verificar_token)):
    col = get_sesiones_col()
    sesion = col.find_one({"id": sesion_id})
    if not sesion:
        raise HTTPException(status_code=404, detail="Sesión no encontrada.")
    
    # Filtrar solo los datos que el usuario envió para actualizar
    datos_nuevos = {k: v for k, v in req.model_dump().items() if v is not None}
    if not datos_nuevos:
        raise HTTPException(status_code=400, detail="No se enviaron campos válidos para actualizar.")

    col.update_one({"id": sesion_id}, {"$set": datos_nuevos})
    return {"mensaje": "Sesión actualizada correctamente"}


@app.delete("/api/sesiones/{sesion_id}", status_code=200)
def eliminar_sesion(sesion_id: str, usuario = Depends(verificar_token)):
    col = get_sesiones_col()
    resultado = col.delete_one({"id": sesion_id})
    if resultado.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Sesión no encontrada.")
    return {"mensaje": f"Sesión {sesion_id} eliminada correctamente"}

# Para correr el servidor
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("APP_PORT", "8080")) # Usando el puerto de .env
    uvicorn.run("Api:app", host="0.0.0.0", port=port, reload=True)