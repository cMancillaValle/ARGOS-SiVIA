# ARGOS-SiVIA

## Plataforma de monitoreo inteligente basada en visión por computador

**Prototipo académico de investigación**  
Universidad Central, Bogotá, Colombia

ARGOS-SiVIA (Sistema de Visión Artificial) es una plataforma de software desarrollada con fines académicos para explorar la detección y el registro de posibles evasiones de pasaje y accesos no autorizados en estaciones de transporte público masivo.

El proyecto integra un motor de visión por computador, un backend para la gestión de información, una interfaz web multirol y un asistente conversacional. Su arquitectura modular permite desarrollar, evaluar y ampliar progresivamente sus capacidades.

> El sistema es un prototipo académico. Sus capacidades de detección requieren validación en condiciones reales antes de considerar su uso operativo.

## Tecnologías

### Lenguajes y desarrollo

[![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![JavaScript](https://img.shields.io/badge/JavaScript-F7DF1E?style=for-the-badge&logo=javascript&logoColor=black)](https://developer.mozilla.org/en-US/docs/Web/JavaScript)
[![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![HTML5](https://img.shields.io/badge/HTML5-E34F26?style=for-the-badge&logo=html5&logoColor=white)](https://developer.mozilla.org/en-US/docs/Web/HTML)
[![CSS3](https://img.shields.io/badge/CSS3-1572B6?style=for-the-badge&logo=css&logoColor=white)](https://developer.mozilla.org/en-US/docs/Web/CSS)

### Backend y almacenamiento

[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![SQLite](https://img.shields.io/badge/SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Pydantic](https://img.shields.io/badge/Pydantic-E92063?style=for-the-badge)](https://docs.pydantic.dev/)

### Visión por computador e inteligencia artificial

[![YOLOv8](https://img.shields.io/badge/YOLOv8-111F68?style=for-the-badge)](https://docs.ultralytics.com/)
[![OpenCV](https://img.shields.io/badge/OpenCV-5C3EE8?style=for-the-badge&logo=opencv&logoColor=white)](https://opencv.org/)
[![MediaPipe](https://img.shields.io/badge/MediaPipe-0097A7?style=for-the-badge)](https://ai.google.dev/edge/mediapipe)
[![PyTorch](https://img.shields.io/badge/PyTorch-EE4C2C?style=for-the-badge&logo=pytorch&logoColor=white)](https://pytorch.org/)

### Interfaz y herramientas

[![React](https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Vite-646CFF?style=for-the-badge&logo=vite&logoColor=white)](https://vite.dev/)
[![Git](https://img.shields.io/badge/Git-F05032?style=for-the-badge&logo=git&logoColor=white)](https://git-scm.com/)
[![Markdown](https://img.shields.io/badge/Markdown-000000?style=for-the-badge&logo=markdown&logoColor=white)](https://www.markdownguide.org/)

## Funcionalidades principales

### Athena: motor de visión por computador

Athena es el módulo encargado del procesamiento visual y del análisis de escenas.

- Detección y seguimiento de personas mediante YOLOv8 y ByteTrack.
- Estimación de postura corporal mediante MediaPipe Pose.
- Análisis de movimientos asociados a posibles evasiones de pasaje.
- Delimitación de zonas de interés mediante líneas virtuales.
- Procesamiento de archivos de video y fuentes de cámara compatibles.
- Generación de eventos a partir de las condiciones detectadas.

Las detecciones representan resultados del sistema que deben evaluarse y validarse. No constituyen, por sí solas, una confirmación de una infracción.

### Backend: API y gestión del sistema

El backend centraliza la lógica de negocio, la autenticación y la comunicación entre módulos.

- API REST desarrollada con FastAPI.
- Autenticación mediante tokens.
- Control de acceso basado en roles y permisos.
- Gestión de usuarios, cámaras y eventos.
- Registro de acciones para auditoría.
- Persistencia de información mediante SQLite.
- Comunicación en tiempo real mediante mecanismos de streaming y eventos.
- Funciones de autenticación de dos factores y recuperación de cuentas.

### Dashboard: interfaz web

La interfaz permite acceder a las funciones de gestión y monitoreo desde un panel centralizado.

- Visualización de cámaras y fuentes de video.
- Consulta de eventos generados por el sistema.
- Gestión de usuarios y permisos.
- Acceso a estadísticas e información del sistema.
- Módulos de auditoría, infraestructura y notificaciones.
- Interfaz adaptada a diferentes roles de usuario.

### Hermes: asistente conversacional

Hermes es un asistente integrado en la plataforma para facilitar las consultas sobre el sistema.

- Identificación de intenciones y extracción de entidades mediante reglas.
- Respuestas contextuales basadas en información disponible en el sistema.
- Restricción de consultas según los permisos del usuario.
- Historial de conversación asociado a la sesión.
- Interfaz independiente desarrollada con React y TypeScript.

Hermes utiliza un motor basado en reglas, no un modelo de lenguaje de gran escala.

## Arquitectura general

ARGOS-SiVIA se organiza en módulos con responsabilidades diferenciadas:

| Módulo | Responsabilidad |
|---|---|
| Frontend | Interfaz web, navegación y presentación de información. |
| Backend | API, autenticación, permisos y lógica de negocio. |
| Athena | Procesamiento de video, detección y seguimiento de personas. |
| Hermes | Asistencia conversacional y consultas contextuales. |
| Base de datos | Persistencia de usuarios, eventos y datos del sistema. |

La separación de estos componentes facilita el mantenimiento y permite evolucionar cada módulo de forma progresiva.

## Estructura del proyecto

```text
ARGOS-SiVIA/
├── backend/
│   ├── api/
│   │   └── routers/
│   ├── core_ia/
│   │   └── athena/
│   │       ├── detectors/
│   │       ├── logic/
│   │       └── events/
│   ├── database/
│   ├── services/
│   └── main.py
├── frontend/
│   ├── css/
│   ├── js/
│   ├── views/
│   └── components/
├── frontend-hermes/
│   └── src/
├── database/
├── requirements.txt
├── .env.example
└── README.md
```

La estructura es orientativa y resume los directorios principales del proyecto.

## Requisitos

Antes de ejecutar el sistema, verifica que el entorno disponga de las siguientes herramientas:

- Python 3.10 o superior, sujeto a las dependencias actuales del proyecto.
- Node.js y npm para compilar el widget de Hermes.
- Dependencias de visión por computador e inferencia de modelos.
- Un archivo de configuración `.env` con los parámetros necesarios.

Las versiones exactas deben consultarse en los archivos de dependencias de cada módulo.

## Configuración

1. Clona el repositorio.
2. Revisa las dependencias del backend y del motor de visión.
3. Instala las dependencias del frontend de Hermes si necesitas compilarlo.
4. Crea un archivo `.env` a partir de `.env.example`.
5. Configura los parámetros requeridos para autenticación, correo y servicios opcionales.
6. Inicia los componentes siguiendo las instrucciones de desarrollo vigentes.

**Importante:** no publiques contraseñas, tokens, claves criptográficas ni credenciales personales en el repositorio.

Los comandos específicos de instalación y ejecución se documentarán de acuerdo con la configuración vigente del proyecto.

## Estado del proyecto

ARGOS-SiVIA es un prototipo académico en evolución. Su desarrollo contempla mejoras en la interfaz, la detección visual, la experiencia de consulta y la validación de los resultados.

Entre las líneas de trabajo previstas se encuentran:

- Evolución de la interfaz web hacia una arquitectura React y TypeScript.
- Mejora de las capacidades conversacionales de Hermes.
- Optimización de la comunicación entre Athena y el backend.
- Validación del sistema con conjuntos de video representativos.
- Ampliación de las opciones de consulta y exportación de informes.
- Evaluación de alternativas de almacenamiento para futuras necesidades.

Estas líneas de trabajo no implican que las funcionalidades correspondientes estén implementadas actualmente.

## Contexto académico

ARGOS-SiVIA se desarrolla como un proyecto académico de investigación en visión por computador, desarrollo web e integración de sistemas.

El objetivo es construir una base tecnológica modular que permita estudiar el procesamiento visual, la gestión de eventos y el diseño de plataformas de monitoreo inteligente.

## Colaboradores

- **Carlos Mancilla.**
- **Xavier Bravo:** [GitHub](https://github.com/xbravob-alt)
- **Esteban Vallejo:** [GitHub](https://github.com/evallejog)

## Repositorio

[Consultar el código fuente de ARGOS-SiVIA](https://github.com/cMancillaValle/ARGOS-SiVIA)

---

**ARGOS-SiVIA**  
Prototipo académico de visión artificial.