# Proyecto Titulo LEICA Inventario — Prototipo funcional 

Código base (backend + frontend + base de datos) para el Sistema de Gestión
de Inventario y Préstamo de Equipos con IA del Laboratorio LEICA (INACAP
Valdivia), construido a partir de la Formulación de Proyecto de Título.

Este **no** es un demo visual: es un servidor real con base de datos, login,
roles y reglas de negocio funcionando, pensado para que sigas construyendo
sobre él durante tus sprints (ver Tabla 2, Cronograma).

## Stack y por qué

- **Backend:** Node.js + Express + SQLite (`better-sqlite3`).
- **Frontend:** HTML/CSS/JS sin framework (servido por el mismo Express), para
  que no tengas que levantar dos servidores ni configurar un build.
- **Base de datos:** SQLite en un archivo (`data/leica.db`) para que el
  prototipo corra sin instalar un motor aparte. Como toda la lógica vive en
  `src/routes/*.js` (no en SQL específico de SQLite), migrar a PostgreSQL o
  MySQL en producción es sobre todo cambiar `src/db/db.js` por un driver/pool
  distinto — coherente con la arquitectura cliente-servidor de tres capas
  definida en la sección VII de tu Formulación.

## Cómo correrlo

```bash
cd leica-inventario
npm install
cp .env.example .env
npm run seed      # crea la BD y un usuario de ejemplo por cada rol
npm start         # http://localhost:3000
```

Usuarios de ejemplo (ver `src/db/seed.js`), contraseña para todos: `Leica2026!`

| Rol | Email |
|---|---|
| Encargado de Laboratorio | encargado.leica@inacapmail.cl |
| Control de Calidad | calidad@inacapmail.cl |
| Docente | docente1@inacapmail.cl |
| Director de Carrera | dcarrera@inacapmail.cl |
| Comité Ejecutivo | vicerrector@inacapmail.cl |
| Estudiante | estudiante1@inacapmail.cl |

## Qué hace falta para que sea "de verdad" tuyo

1. **Dominio institucional real**: `DOMINIO_INSTITUCIONAL` en `.env` hoy es
   `inacapmail.cl` de ejemplo; cámbialo por el dominio real de correo de
   INACAP y conecta `src/routes/auth.routes.js` contra el directorio real
   (hoy valida contra la tabla `usuarios` local).
2. **IA de búsqueda (RF-11)**: funciona con un respaldo por palabras clave.
   Agrega tu `ANTHROPIC_API_KEY` en `.env` para que use la API de Claude de
   verdad (ver `src/routes/search.routes.js`).
3. **Reconocimiento por foto (RF-12/HU-12)**: no está implementado todavía;
   es el siguiente paso natural una vez que el CRUD y las solicitudes estén
   probados con el Encargado de Laboratorio.
4. **Base de datos de producción**: migrar de SQLite a Postgres/MySQL cuando
   el servidor/infraestructura de INACAP esté definido (ver RNF-04, RNF-05).
5. **Despliegue en el servidor de LEICA**: sin virtualización, según la
   restricción institucional relevada en la entrevista (Anexo 5/6).

## Mapeo de Requisitos Funcionales → código

| RF | Descripción | Archivo |
|---|---|---|
| RF-01 | Registrar equipo con código único | `src/routes/equipment.routes.js` |
| RF-02 | Edición concurrente sin bloqueo mutuo | `equipment.routes.js` (campo `version`, optimistic locking) |
| RF-03 | Insumos por cantidad, sin negativos | `src/routes/supplies.routes.js`, `requests.routes.js` (entrega) |
| RF-04 | Roles de lectura/escritura | `src/middleware/auth.js` (`ROLES_ESCRITURA_INVENTARIO`) |
| RF-05 | Autenticación por correo institucional | `src/routes/auth.routes.js` |
| RF-06 | Solicitud en representación de un estudiante | `src/routes/requests.routes.js` (`en_representacion_de`) |
| RF-07 | Validar disponibilidad en tiempo real | `requests.routes.js` (`POST /:id/aprobar`) |
| RF-08 | Registrar salida/devolución con trazabilidad | `requests.routes.js` (`entregar`, `devolver`), tabla `movimientos` |
| RF-09 | Bloqueo automático por atraso | `requests.routes.js` (`devolver`), tabla `bloqueos` |
| RF-10 | Regla del 70% (reparar/dar de baja) | `src/routes/maintenance.routes.js` |
| RF-11 | Búsqueda en lenguaje natural | `src/routes/search.routes.js` |
| RF-13 | Reportes agregados | `src/routes/reports.routes.js` |
| RF-14 | Migración desde Excel/SharePoint | `src/routes/migration.routes.js` |

Cada archivo de rutas trae además, en su encabezado, el comentario con el RF
exacto que implementa (redactado igual que en tu tabla de requisitos), para
que te sea fácil defender ante el profesor qué parte del código corresponde
a qué requisito.

## Hallazgos de la entrevista ya incorporados (Anexo 6)

- Solicitudes con varios ítems / kits (tabla `solicitud_items`).
- Distinción insumo renovable/perecible y aviso de stock bajo (tabla `insumos`).
- Lugar de uso dentro/fuera de sede (tabla `solicitudes`).
- Bloqueo automático de máximo 1 semana (RF-09).

## Estructura

```
src/
  db/          esquema SQL, conexión y datos de ejemplo
  middleware/  autenticación JWT y control de roles
  routes/      un archivo por módulo funcional (ver tabla arriba)
  server.js    arma Express, monta las rutas y sirve el frontend
public/
  index.html, css/, js/app.js   frontend SPA sin build (fetch a /api/*)
```
