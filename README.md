# Proyecto Titulo LEICA Inventario — Prototipo funcional 

Código base (backend + frontend + base de datos) para el Sistema de Gestión
de Inventario y Préstamo de Equipos con IA del Laboratorio LEICA (INACAP
Valdivia), construido a partir de la Formulación de Proyecto de Título.

## Stack y por qué

- **Backend:** Node.js + Express + SQLite.
- **Frontend:** HTML/CSS/JS sin framework.
- **Base de datos:** SQLite.
  
## Cómo correrlo

```bash
cd leica-inventario
npm install
cp .env.example .env
npm run seed      
npm start         
```

Usuarios de ejemplo, contraseña para todos: `Leica2026!`

| Rol | Email |
| Encargado de Laboratorio | encargado.leica@inacapmail.cl |
| Control de Calidad | calidad@inacapmail.cl |
| Docente | docente1@inacapmail.cl |
| Director de Carrera | dcarrera@inacapmail.cl |
| Comité Ejecutivo | vicerrector@inacapmail.cl |
| Estudiante | estudiante1@inacapmail.cl |

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
