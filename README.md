# ARGOS - SiViA
## Plataforma de Monitoreo Inteligente Basada en Visión por Computador

> **Prototipo Académico de Investigación** · Universidad Central · Bogotá, Colombia

**ARGOS - SiViA** *(Sistema de Visión Artificial)* es una plataforma de software de monitoreo inteligente diseñada con fines académicos para la detección automática y reporte en tiempo real de evasión de pasaje y accesos no autorizados en estaciones de transporte público masivo (TransMilenio S.A.).

El sistema integra un pipeline de visión por computador con un backend REST, una interfaz web de gestión multi-rol y un asistente conversacional basado en NLP por reglas. Su arquitectura está pensada para ser modular y extensible, sirviendo como base tecnológica para investigación futura en sistemas de seguridad inteligente.

---

## ✨ Funcionalidades Principales

### 🎥 Módulo de Visión IA — Athena
- **Detección de personas** en tiempo real usando **YOLOv8n** (ultralytics)
- **Estimación de pose corporal** con **MediaPipe Pose** para clasificar comportamientos sospechosos (salto de torniquete, merodeo)
- **Detección de manos y gestos** con **MediaPipe Hands**
- **Detección facial** con **MediaPipe Face Mesh** para análisis de presencia
- **Detector de tarjetas/objetos** (OpenCV + contornos) para identificar elementos en zonas restringidas
- Procesamiento de cámara en tiempo real (webcam o cámara IP)
- Worker de inferencia independiente con comunicación inter-proceso con el backend Flask

### 🖥️ Backend REST — Flask
- API REST completa con autenticación por token (`X-Token`)
- **Control de Acceso Basado en Roles (RBAC)** con 6 roles: `admin`, `supervisor`, `operador`, `analista`, `técnico`, `auditor`
- Gestión completa de cámaras (CRUD)
- Registro y gestión de eventos de seguridad detectados
- Auditoría de acciones del sistema con log persistente
- Estadísticas del sistema en tiempo real
- Gestión de perfil de usuario con cambio de email y contraseña verificados por código OTP
- Autenticación de dos factores **2FA TOTP** (Google Authenticator compatible) con código QR
- Restablecimiento de contraseña por correo electrónico con códigos temporales (SMTP Gmail)
- Rate limiting y protección contra fuerza bruta (Flask-Limiter)
- Métricas de sistema en tiempo real (CPU, RAM, disco — psutil)
- Acceso remoto a cámara cliente via **WebSocket** (flask-sock)

### 🌐 Frontend Web — Dashboard Principal
- Interfaz SPA multi-panel renderizada dinámicamente con JavaScript
- **Landing page** de presentación del sistema
- **Panel de inicio de sesión** con soporte 2FA
- **Dashboard** de monitoreo con los siguientes módulos:
  - Vista de inicio con métricas del sistema
  - Monitor de cámaras registradas con stream en tiempo real
  - Eventos y alertas de seguridad (confirmar / descartar)
  - Gestión de usuarios y asignación de roles (RBAC)
  - Módulo de auditoría con exportación CSV
  - Estadísticas e informes de actividad
  - Configuración de parámetros del sistema e IA
  - Módulos de infraestructura (servidores, red, cámaras)
  - Notificaciones internas del sistema

### 🤖 Hermes IA — Asistente Conversacional
- Motor NLP liviano basado en reglas (sin dependencias de ML)
- Reconocimiento de intenciones (12 categorías) y extracción de entidades
- Respuestas contextuales basadas en datos reales de la base de datos
- Restricción de acceso a información por rol del usuario activo
- Micro-frontend independiente construido en **React + TypeScript** con **Vite**
- Historial de sesión en memoria por token de autenticación
- Sugerencias y acciones rápidas contextuales por rol

### 🌍 Acceso Remoto — Ngrok
- Túnel HTTP seguro via **pyngrok** para exponer el servidor Flask a internet
- Auto-detección del token desde archivo `.ngrok_token` o variable de entorno
- Construcción automática del micro-frontend Hermes antes de lanzar el túnel
- URL pública guardada en `.ngrok_url_actual` para consumo por otros scripts

---

## 🏗️ Arquitectura del Proyecto

```
ARGOS-SiVIA/
│
├── .env                        ← Variables de entorno (SMTP, Fernet, Flask, Ngrok)
├── .env.example                ← Plantilla de configuración
├── requirements.txt            ← Dependencias del servidor Flask
├── ngrok_tunnel.py             ← Lanzador del túnel de acceso remoto
├── start.py                    ← Script de inicio rápido local
│
├── frontend/                   ← Interfaz web principal (HTML + CSS + JS Vanilla)
│   ├── index.html              → Landing page
│   ├── login.html              → Inicio de sesión + 2FA
│   ├── dashboard.html          → Panel de control principal (SPA)
│   ├── css/
│   │   └── argos-design.css    → Sistema de diseño principal
│   ├── js/
│   │   ├── api.js              → Cliente API centralizado
│   │   ├── dashboard.js        → Lógica de paneles dinámicos
│   │   ├── permissions.js      → Control de acceso en UI por rol
│   │   ├── rbac.js             → Carga de matriz de permisos
│   │   └── router.js           → Enrutador de vistas del dashboard
│   ├── views/                  → Plantillas HTML por módulo del dashboard
│   └── components/             → Componentes reutilizables (sidebar, topbar)
│
├── frontend-hermes/            ← Micro-frontend Hermes IA (React + TypeScript)
│   ├── src/
│   │   ├── App.tsx             → Componente raíz
│   │   ├── hermes-widget.tsx   → Widget embebible del chatbot
│   │   ├── components/         → Componentes React del chat
│   │   ├── hooks/              → Custom hooks
│   │   ├── store/              → Estado global
│   │   ├── styles/             → Estilos del widget
│   │   └── types/              → Tipos TypeScript
│   └── dist/                   → Bundle compilado (generado por Vite)
│
├── backend/                    ← Servidor Flask (API REST + lógica de negocio)
│   ├── app.py                  → Entrada principal, registro de blueprints
│   ├── requirements.txt        → Dependencias de IA (torch, ultralytics, mediapipe)
│   ├── database/
│   │   └── db.py               → Esquema SQLite, inicialización y datos demo
│   ├── routes/                 → Blueprints Flask por dominio
│   │   ├── auth.py             → Autenticación + 2FA TOTP
│   │   ├── cameras.py          → CRUD cámaras + stream MJPEG
│   │   ├── camera_client.py    → WebSocket para cámara cliente remota
│   │   ├── events.py           → Gestión de eventos de seguridad
│   │   ├── stats.py            → Estadísticas del sistema
│   │   ├── users.py            → CRUD usuarios
│   │   ├── rbac_api.py         → API de permisos y matriz RBAC
│   │   ├── profile.py          → Perfil de usuario + cambio de email/contraseña
│   │   ├── reset_password.py   → Recuperación de contraseña por email
│   │   ├── auditoria.py        → Log de auditoría + exportación CSV
│   │   ├── chat.py             → Endpoint del asistente Hermes IA
│   │   └── system_metrics.py   → Métricas de CPU/RAM/disco + configuración IA
│   ├── services/               → Lógica de negocio desacoplada
│   │   ├── auth_service.py     → Tokens, decoradores @requiere_auth / @requiere_rol
│   │   ├── rbac.py             → Matriz RBAC y evaluación de permisos
│   │   ├── hermes_service.py   → Orquestador del pipeline Hermes IA
│   │   ├── hermes_intents.py   → Motor NLP por reglas (detección de intenciones)
│   │   ├── hermes_context.py   → Modelos Pydantic de contratos API
│   │   ├── hermes_session.py   → Historial de sesión en RAM
│   │   ├── email_service.py    → Envío de emails SMTP (OTP, reset password, 2FA)
│   │   ├── two_factor.py       → Gestión de TOTP + Fernet + QR
│   │   └── system_health.py    → Snapshot de métricas del sistema (psutil)
│   └── utils/
│       ├── limiter.py          → Rate limiter global (Flask-Limiter)
│       └── validators.py       → Validadores de entrada
│
├── backend/core_ia/athena/     ← Motor de Visión IA (Worker independiente)
│   ├── athena_engine.py        → Orchestrador del worker IA (proceso subprocess)
│   ├── athena_worker.py        → Worker de inferencia (YOLOv8 + MediaPipe)
│   ├── client_frame_buffer.py  → Buffer de frames de cámara cliente
│   ├── yolov8n.pt              → Pesos del modelo YOLOv8 nano
│   ├── detectors/              → Detectores especializados
│   │   ├── person_detector.py  → Detección de personas (YOLO)
│   │   ├── pose_detector.py    → Estimación de pose (MediaPipe Pose)
│   │   ├── hand_detector.py    → Detección de manos (MediaPipe Hands)
│   │   ├── face_detector.py    → Detección facial (MediaPipe Face Mesh)
│   │   └── card_detector.py    → Detección de tarjetas/objetos (OpenCV)
│   ├── logic/
│   │   └── decision_engine.py  → Motor de decisión de eventos
│   ├── events/
│   │   └── event_manager.py    → Registro de eventos al backend REST
│   ├── database/
│   │   └── db.py               → Conexión local SQLite del worker
│   └── dataset/                → Imágenes y etiquetas de entrenamiento YOLO
│
└── database/
    └── argos.db                ← Base de datos SQLite (auto-generada al inicio)
```

---

## ⚙️ Stack Tecnológico

### Backend
| Tecnología | Versión | Uso |
|---|---|---|
| **Python** | 3.10+ | Lenguaje base del servidor y IA |
| **Flask** | 3.0.3 | Framework servidor REST |
| **Flask-Limiter** | 3.8.0 | Rate limiting y protección brute-force |
| **flask-sock** | ≥ 0.7.0 | WebSocket para cámara cliente remota |
| **Werkzeug** | 3.0.3 | Seguridad: hashing de contraseñas PBKDF2 |
| **SQLite** | stdlib | Base de datos embebida |
| **pyotp** | 2.9.0 | Generación y validación TOTP (2FA) |
| **cryptography** | 43.0.3 | Cifrado Fernet del secreto TOTP |
| **qrcode[pil]** | 8.0 | Generación de código QR para 2FA |
| **psutil** | 6.1.1+ | Métricas de CPU, RAM y disco |
| **pydantic** | ≥ 2.0 | Validación de contratos API (Hermes) |
| **python-dotenv** | ≥ 1.0.1 | Carga de variables de entorno |

### Motor de Visión IA — Athena
| Tecnología | Versión | Uso |
|---|---|---|
| **YOLOv8n** (ultralytics) | 8.4.33 | Detección de objetos y personas en tiempo real |
| **MediaPipe** | 0.10.9 | Estimación de pose, manos y malla facial |
| **OpenCV** | 4.13.0 | Captura de video, procesamiento de frames |
| **PyTorch** | 2.11.0 | Backend de inferencia de YOLOv8 |
| **NumPy** | 2.2.6 | Operaciones matriciales sobre frames |

### Frontend Principal
| Tecnología | Uso |
|---|---|
| **HTML5 / CSS3** | Estructura y estilos del dashboard |
| **JavaScript (Vanilla ES6+)** | Lógica de paneles, API client, router SPA |
| **Google Fonts** | Rajdhani · Exo 2 · Share Tech Mono |

### Micro-Frontend Hermes IA
| Tecnología | Versión | Uso |
|---|---|---|
| **React** | 19.2.4 | Componentes del widget de chat |
| **TypeScript** | ~5.9.3 | Tipado estático |
| **Vite** | 8.0.1 | Bundler y servidor de desarrollo |
| **vite-plugin-css-injected-by-js** | 4.0.1 | Widget embebible sin CSS externo |

### Infraestructura y Herramientas
| Tecnología | Uso |
|---|---|
| **pyngrok** | Túnel HTTP para acceso remoto |
| **SMTP Gmail** | Envío de emails transaccionales (OTP, reset) |
| **Inno Setup** | Generación del instalador Windows (.exe) |

---

## 🚀 Instalación y Ejecución

### Requisitos previos
- **Python 3.10+** instalado y en el PATH
- **Node.js 18+** (solo si se va a compilar Hermes IA Widget)
- Crear y configurar el archivo `.env` a partir de `.env.example`

### 1. Instalación del servidor backend
```bash
# Crear entorno virtual e instalar dependencias del servidor
python -m venv backend_env
backend_env\Scripts\activate
pip install -r requirements.txt
```

### 2. Instalación del motor de IA (Athena)
```bash
# Crear entorno virtual e instalar dependencias de IA (PyTorch, YOLO, MediaPipe)
python -m venv vision_env
vision_env\Scripts\activate
pip install ultralytics opencv-python mediapipe torch
```

### 3. Iniciar el sistema
```bash
# Activar entorno del backend e iniciar el servidor
backend_env\Scripts\activate
python backend/app.py
```

> El servidor levanta en `http://localhost:5000`

### 4. Acceso remoto (opcional)
```bash
# Requiere token configurado en .env (NGROK_AUTHTOKEN) o archivo .ngrok_token
python ngrok_tunnel.py
```

---

## 👥 Usuarios de Acceso Demo

| Usuario | Contraseña | Rol | Permisos |
|---|---|---|---|
| `admin` | `admin123` | Administrador | Acceso total al sistema |
| `supervisor` | `sup123` | Supervisor | Monitoreo, alertas, análisis y reportes |
| `operador` | `op123` | Operador | Cámaras y gestión de alertas |
| `analista` | `an123` | Analista de Datos | Estadísticas e informes históricos |
| `tecnico` | `tec123` | Técnico / Ingeniero | IA, infraestructura y logs técnicos |
| `auditor` | `aud123` | Auditor | Solo lectura — auditoría e historial |

---

## 🔐 Configuración de Variables de Entorno

Copiar `.env.example` como `.env` y completar los valores:

```env
# Cifrado del secreto TOTP (2FA)
ARGOS_FERNET_KEY=<clave generada con Fernet.generate_key()>

# Servidor de correo SMTP (Gmail App Password)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=correo@gmail.com
SMTP_PASS=xxxx xxxx xxxx xxxx
SMTP_FROM=correo@gmail.com

# Modo desarrollo (1 = no envía emails, devuelve código en JSON)
ARGOS_DEV_MODE=1

# Clave secreta Flask para firmar sesiones
SECRET_KEY=<clave segura generada con secrets.token_hex(32)>

# Token de Ngrok para acceso remoto
NGROK_AUTHTOKEN=<token desde dashboard.ngrok.com>
```

---

## 🔮 Mejoras Futuras Planificadas

- **Migración a PostgreSQL:** Escalar la base de datos desde SQLite a PostgreSQL para soportar mayor volumen de eventos, logs de auditoría y concurrencia de usuarios en un entorno de producción real.
- **Migración completa de la UI a React:** Reemplazar el frontend en HTML/JS vanilla por una aplicación SPA React completa (con tipado TypeScript), ampliando la arquitectura tecnológica del micro-frontend Hermes.
- **Mejora del Chatbot Hermes IA:** Integrar modelos de lenguaje locales (LLM) o técnicas de NLP semántico más avanzadas para mejorar la comprensión y contextualización de las consultas del usuario.
- **Optimización del Flujo Athena IA ↔ Backend:** Refactorizar el canal de comunicación entre el worker de visión IA y el backend Flask (buffers de memoria compartida, ZeroMQ o WebSocket dedicado) para eliminar los retrasos actuales en el procesamiento de frames en tiempo real.
- **Validación con Videos de Campo:** Realizar pruebas exhaustivas y re-entrenamiento del modelo YOLOv8 utilizando grabaciones reales de personas evadiendo el pasaje en estaciones de TransMilenio para mejorar la precisión y reducir falsos positivos.
- **Exportación de Reportes PDF/Excel:** Añadir generación de reportes de incidencias y estadísticas en formatos descargables.
- **Autenticación JWT:** Migrar el esquema de tokens de sesión simples a JSON Web Tokens estándar para mayor interoperabilidad y seguridad.

---

*ARGOS - SiViA v1.7.5 · Prototipo Académico · Universidad Central*
