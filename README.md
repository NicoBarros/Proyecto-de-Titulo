# LEICA Inventario

Sistema de gestión de inventario y préstamo de equipos del laboratorio LEICA, INACAP Sede Valdivia.
Proyecto de título.

Permite administrar equipos e insumos, solicitar préstamos (kits), aprobarlos, entregarlos y
registrar su devolución, sancionar atrasos, gestionar mantenimientos con la regla del 70 %,
generar reportes, exportar el inventario a Excel, registrar el historial de cambios de cada equipo,
generar códigos QR y buscar equipos en lenguaje natural con IA (Google Gemini).

## Stack

| Capa | Tecnología |
|---|---|
| Backend | Python 3.14 + Django 6.1 |
| Frontend | Plantillas de Django (HTML, CSS y JavaScript sin frameworks) |
| Base de datos | PostgreSQL (probado con la versión 18) |
| IA | Google Gemini (`google-genai`), con búsqueda local por palabras clave como respaldo |
| Producción | Gunicorn + WhiteNoise para archivos estáticos |

## Instalación local

Requisitos: Python 3.14 y PostgreSQL instalados. Los comandos son para PowerShell en Windows.

**1. Entorno virtual y dependencias**

```powershell
py -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

**2. Base de datos**

Crea un usuario y una base de datos para la aplicación. Abre `psql` como superusuario:

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h localhost
```

y ejecuta:

```sql
CREATE ROLE leica WITH LOGIN PASSWORD 'una-clave-segura' CREATEDB;
CREATE DATABASE leica_inventario OWNER leica ENCODING 'UTF8' TEMPLATE template0;
```

El permiso `CREATEDB` es necesario para que Django pueda crear la base temporal de los tests.

**3. Variables de entorno**

Copia `.env.example` como `.env` y completa los valores:

```powershell
copy .env.example .env
```

| Variable | Descripción |
|---|---|
| `SECRET_KEY` | Obligatoria. Genera una con `python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"` |
| `DEBUG` | `True` en desarrollo. Por defecto es `False` |
| `ALLOWED_HOSTS` | Dominios permitidos, separados por coma |
| `DATABASE_URL` | `postgres://leica:una-clave-segura@localhost:5432/leica_inventario` |
| `DOMINIO_INSTITUCIONAL` | Dominio de correo aceptado al crear usuarios (`inacapmail.cl`) |
| `GEMINI_API_KEY` | Opcional. Sin ella, la búsqueda usa solo palabras clave |

**4. Tablas, datos de prueba y servidor**

```powershell
python manage.py migrate
python manage.py seed
python manage.py runserver
```

La aplicación queda en http://127.0.0.1:8000.

## Usuarios de prueba

El comando `seed` crea estos usuarios, todos con la contraseña `Leica2026!`. Con `DEBUG=True`, la
pantalla de login también los muestra.

| Rol | Correo |
|---|---|
| Encargado de Laboratorio (superusuario) | encargado.leica@inacapmail.cl |
| Control de Calidad | calidad@inacapmail.cl |
| Director de Carrera | dcarrera@inacapmail.cl |
| Docente | docente1@inacapmail.cl |
| Estudiante | estudiante1@inacapmail.cl, estudiante2@inacapmail.cl |

No ejecutes `seed` en producción: crea un superusuario con una contraseña pública.

## Roles y permisos

Los permisos se validan en el servidor según el rol del usuario, no solo en la interfaz.

| Función | Estudiante | Docente | Director | Encargado | Control Calidad | Comité |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| Ver inventario y buscar equipos | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Crear solicitudes | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Solicitar en representación de un estudiante | | ✓ | ✓ | ✓ | ✓ | |
| Ver todas las solicitudes (el resto ve solo las propias) | | | ✓ | ✓ | ✓ | |
| Aprobar, entregar y recibir devoluciones | | | ✓ | ✓ | ✓ | |
| Mantenimiento | | | ✓ | ✓ | ✓ | |
| Reportes y KPIs | | | ✓ | ✓ | ✓ | ✓ |
| Editar inventario, exportar a Excel, QR e historial de equipos | | | | ✓ | ✓ | |

El **Panel Admin** es para usuarios staff. Un staff que no es superusuario solo gestiona cuentas
comunes: no puede modificar a otros administradores ni asignar roles con permisos de aprobación.

## Reglas de negocio principales

- **Préstamos:** una solicitud pasa por pendiente → aprobada → entregada → devuelta. Solo se puede
  rechazar mientras está pendiente o aprobada. Al aprobar se verifica que el equipo no esté reservado
  en un horario que se cruce.
- **Atrasos:** un préstamo entregado cuyo plazo venció pasa automáticamente a "Atrasada" y aparece
  como alerta en el dashboard de quienes aprueban. Si se devuelve tarde queda como "Devuelta con
  atraso". El comando `python manage.py marcar_atrasadas` permite programar esta revisión.
- **Representación:** docentes, directores, encargados y Control de Calidad pueden pedir un préstamo
  a nombre de un estudiante; en ese caso la sanción por atraso se aplica al estudiante.
- **Insumos:** los renovables vuelven al stock al devolverse; los perecibles se consumen.
- **Sanciones (RF-09):** una devolución atrasada bloquea al estudiante por 7 días para pedir préstamos.
- **Mantenimiento (RF-10):** si el costo de reparación es igual o mayor al 70 % del valor de
  adquisición, el sistema sugiere dar el equipo de baja.
- **Historial:** un equipo, insumo o usuario con préstamos o mantenimientos registrados no se puede
  eliminar. Para retirar un equipo se marca como "Fuera de servicio".
- **Auditoría:** cada creación, edición, cambio de estado o eliminación de un equipo queda registrada
  con usuario, fecha, valores anteriores y nuevos, y origen (inventario, préstamo, mantenimiento,
  panel o admin). Se consulta con el botón "Historial" de cada equipo.

## Exportar inventario a Excel

El botón "Exportar Inventario Excel" de la pantalla Inventario descarga `inventario_leica_AAAAMMDD.xlsx`
con tres hojas con formato: **Resumen** (equipos por estado, valor total e insumos con stock bajo),
**Equipos** e **Insumos**, con colores por estado y filtros en cada columna.

## Tests

```powershell
python manage.py test inventario
```

La suite está en `inventario/tests/` y cubre permisos por rol, inventario, el flujo de préstamos,
mantenimiento, exportación a Excel, códigos QR, auditoría, búsqueda con IA (Gemini simulado, nunca llama a la API real) y el panel
de administración.

## Despliegue

1. Define las variables de entorno del servidor: `SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS` y
   `DATABASE_URL`.
2. Comando de build:
   ```
   pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate
   ```
3. Comando de inicio:
   ```
   gunicorn leica_project.wsgi
   ```

`staticfiles/` no se versiona: `collectstatic` lo genera en cada despliegue.

## Estructura

```
leica_project/        Configuración de Django (settings, urls, wsgi)
inventario/
  models.py           Usuario, Equipo, Insumo, Solicitud, Movimiento, Bloqueo, Mantenimiento, Migracion
  views.py            Lógica de negocio de cada pantalla
  templates/          Plantillas HTML
  static/             CSS e imágenes
  migrations/         Migraciones de la base de datos
  management/commands/seed.py   Datos de prueba
  tests/              Suite de tests
```

Hubo un prototipo anterior en Node/Express. Ya no forma parte del proyecto y se conserva en la
etiqueta git `archivo/prototipo-node`.
