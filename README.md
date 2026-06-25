# API GeForce Now - Sistema de Gestión y Búsqueda Semántica

Este proyecto es una API RESTful desarrollada con **FastAPI**, diseñada para gestionar un catálogo de juegos y sesiones de usuarios simulando el entorno de GeForce Now. Implementa una arquitectura multicontenedor robusta utilizando **Docker** y múltiples motores de bases de datos para separar responsabilidades y optimizar el rendimiento.

## 🚀 Características Principales

El proyecto cumple con los siguientes requerimientos técnicos:

* **Autenticación Segura (JWT):** Sistema de registro y login utilizando contraseñas encriptadas con `bcrypt` y almacenamiento en **PostgreSQL**.
* **Gestión de Datos (CRUD):** Endpoints completos para la administración de juegos y sesiones de usuarios utilizando **MongoDB**.
* **Búsqueda Semántica con IA:** Integración con **ChromaDB** y el modelo de embeddings `all-MiniLM-L6-v2` para buscar juegos por similitud de contexto y no solo por coincidencias exactas de texto.
* **Caché de Alto Rendimiento:** Implementación de **Redis** para almacenar en caché las consultas frecuentes a MongoDB, reduciendo los tiempos de respuesta.
* **Documentación Interactiva:** Todos los endpoints están documentados y son probables mediante **Swagger UI**.
* **Infraestructura Contenerizada:** Todo el ecosistema (API + 4 bases de datos) se levanta y orquesta mediante **Docker Compose**.

## 🛠️ Tecnologías Utilizadas

* **Backend:** Python 3.10, FastAPI, Uvicorn, Pydantic.
* **Bases de Datos:**
  * **MongoDB:** Almacenamiento principal de documentos (Juegos y Sesiones).
  * **PostgreSQL:** Almacenamiento relacional para credenciales de usuarios.
  * **ChromaDB:** Base de datos vectorial para embeddings e IA.
  * **Redis:** Sistema de caché en memoria.
* **Despliegue:** Docker, Docker Compose.

## ⚙️ Instalación y Configuración

### Prerrequisitos
* [Docker](https://www.docker.com/) y Docker Compose instalados en tu sistema.
* Git.

### Pasos para levantar el entorno

1. **Clonar el repositorio:**
   ```bash
   git clone [https://github.com/TU_USUARIO/api-geforcenow-evaluacion.git](https://github.com/TU_USUARIO/api-geforcenow-evaluacion.git)
   cd api-geforcenow-evaluacion
