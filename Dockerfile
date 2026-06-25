# Usamos una imagen oficial de Python ligera
FROM python:3.10-slim

# Establecemos el directorio de trabajo
WORKDIR /app

# Copiamos los archivos de requerimientos primero (si tienes un requirements.txt)
# Si no lo tienes, instalaremos las dependencias directamente aquí.
RUN pip install --no-cache-dir fastapi uvicorn python-dotenv redis pymongo chromadb sentence-transformers requests sqlalchemy passlib bcrypt pyjwt psycopg2-binary pydantic

# Copiamos el resto del código a la carpeta /app del contenedor
COPY . /app

# Exponemos el puerto que usará la API
EXPOSE 8080

# Comando para iniciar la aplicación
CMD ["uvicorn", "Api:app", "--host", "0.0.0.0", "--port", "8080"]