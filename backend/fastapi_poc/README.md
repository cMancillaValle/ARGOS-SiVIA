# Prueba de Concepto (PoC): WebSocket de Cámara en FastAPI
**Proyecto ARGOS-SiViA v1.7.5**

Este módulo implementa un servidor de prueba **FastAPI independiente y aislado** que replica el endpoint WebSocket de recepción de video de cámaras remotas (`WS /api/camaras/client/push`), sin modificar el servidor principal Flask ni alterar las rutas productivas o el frontend.

---

## 1. Requisitos y Dependencias

Para ejecutar este servidor de prueba, se requieren las dependencias indicadas en `requirements-fastapi-poc.txt`:

```bash
pip install -r backend/fastapi_poc/requirements-fastapi-poc.txt
```

Dependencias mínimas:
* `fastapi>=0.110.0`
* `uvicorn[standard]>=0.28.0`
* `websockets>=12.0`

---

## 2. Ejecución del Servidor de Prueba (Puerto 8001)

Desde la carpeta `backend/`:

```bash
cd backend
uvicorn fastapi_poc.app:app --host 0.0.0.0 --port 8001 --workers 1
```

O desde la raíz del proyecto:

```bash
uvicorn backend.fastapi_poc.app:app --host 0.0.0.0 --port 8001 --workers 1
```

> [!IMPORTANT]
> **Ejecución con 1 solo worker (`--workers 1`):**
> Este servidor debe ejecutarse inicialmente con **un único worker**.
> El buffer de frames (`core_ia.athena.client_frame_buffer.client_buffer`), los hilos de inferencia de Athena y el mapa de clientes/cámaras residen en **memoria local compartida** dentro del proceso de Python. Múltiples workers de Uvicorn crearían procesos separados con memoria aislada, impidiendo que Athena consuma los frames recibidos en otro worker sin una capa externa (como Redis).

---

## 3. Protocolo WebSocket Soportado

El servidor replica el protocolo exacto del backend Flask (`backend/routes/camera_client.py`):

* **Endpoint:** `WS /api/camaras/client/push`

### Mensajes del Cliente:
1. **Handshake inicial (obligatorio dentro de los primeros 10s):**
   ```json
   {
     "token": "<token-de-sesion-valido>",
     "cam_id": 1
   }
   ```
2. **Frames JPEG (Base64):**
   ```json
   {
     "type": "frame",
     "data": "data:image/jpeg;base64,...",
     "ts": 1727480000000
   }
   ```
3. **Keep-alive Ping:**
   ```json
   {
     "type": "ping"
   }
   ```

### Respuestas del Servidor:
* **Handshake Exitoso:**
  ```json
  {"type": "ok", "client_id": "a1b2c3d4", "cam_id": 1}
  ```
* **Pong:**
  ```json
  {"type": "pong"}
  ```
* **Errores (cierra la conexión tras enviar el error):**
  * Token inválido/expirado: `{"type": "error", "message": "No autorizado"}`
  * Falta de parámetro de cámara: `{"type": "error", "message": "cam_id requerido"}`
  * Tipo de cámara no válido: `{"type": "error", "message": "cam_id inválido"}`
  * Timeout inicial: `{"type": "error", "message": "Timeout handshake"}`
  * Formato JSON erróneo: `{"type": "error", "message": "Handshake inválido"}`

---

## 4. Verificación y Pruebas

Se incluye un script de prueba automatizado `test_client.py` que comprueba:
* Handshake válido y asignación de `client_id`
* Rechazo y cierre con token inválido
* Rechazo por `cam_id` ausente/inválido
* Flujo de Ping / Pong
* Recepción y decodificación de frame JPEG en `client_buffer`
* Limpieza adecuada de `client_buffer` y mapa de cámaras al desconectar

### Opción A: Modo In-Process (Autónomo sin levantar Uvicorn)
```bash
python backend/fastapi_poc/test_client.py
```

### Opción B: Modo Live Network (Con Uvicorn corriendo en puerto 8001)
```bash
python backend/fastapi_poc/test_client.py --ws-url ws://127.0.0.1:8001/api/camaras/client/push
```

### Opción C: Prueba manual desde la Consola del Navegador (DevTools)
Abriendo la consola de JavaScript en cualquier navegador web:
```javascript
const ws = new WebSocket("ws://localhost:8001/api/camaras/client/push");
ws.onopen = () => {
    console.log("Conectado a FastAPI WS");
    // Enviar handshake (reemplazar con un token activo de la sesión)
    ws.send(JSON.stringify({ token: localStorage.getItem("token") || "tu_token", cam_id: 1 }));
};
ws.onmessage = (e) => console.log("Servidor:", JSON.parse(e.data));
```
