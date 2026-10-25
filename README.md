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
| `GEMINI_MODELO` / `GEMINI_MODELO_RESPALDO` | Opcionales. Modelo principal y de respaldo (por defecto `gemini-2.5-flash` y `gemini-2.5-flash-lite`) |
| `POSTGRES_BIN` | Opcional. Carpeta de `pg_dump` y `pg_restore` si no están en el PATH |
| `SESION_MINUTOS` | Minutos de inactividad antes de cerrar la sesión. Por defecto `60` |

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

## Seguridad

- **Inicio de sesión:** después de 5 intentos fallidos con un mismo correo desde un mismo equipo, el acceso
  se bloquea por 15 minutos (`django-axes`). Un inicio exitoso reinicia el contador.
- **Sesiones:** expiran tras 60 minutos sin actividad y al cerrar el navegador.
- **Registro de seguridad:** inicios y cierres de sesión, intentos fallidos, bloqueos y accesos denegados
  quedan registrados con fecha, usuario, IP y ruta. Se consultan en `/admin/` → **Eventos de seguridad**
  (solo lectura) y también se escriben en el log de la aplicación.
- **Transporte:** HTTPS obligatorio, HSTS de un año, cookies seguras y TLS 1.2 como mínimo.
- **Recursos externos:** Bootstrap y Bootstrap Icons se cargan con verificación de integridad (SRI).
- **Base de datos:** en Azure, el firewall solo acepta conexiones desde las IP de salida de la aplicación.
- **Dependencias:** cada push ejecuta `pip-audit` contra la base de vulnerabilidades conocidas, y Dependabot
  propone actualizaciones semanales.

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

## Despliegue en Azure

Arquitectura de producción:

| Componente | Servicio de Azure |
|---|---|
| Aplicación (Django + Gunicorn) | App Service en Linux, plan B1 |
| Base de datos | Azure Database for PostgreSQL – Flexible Server (Burstable B1ms, respaldos de 7 días) |
| Archivos estáticos | WhiteNoise, servidos por la misma aplicación |
| Integración y entrega continua | GitHub Actions (`.github/workflows/ci-cd.yml`) |
| Monitoreo de disponibilidad | Health check de App Service sobre `/salud/` |

### 1. Crear la infraestructura

Abre **Azure Cloud Shell** (ícono `>_` en el portal de Azure, modo Bash), clona el repositorio y ejecuta:

```bash
git clone https://github.com/NicoBarros/Proyecto-de-Titulo.git
cd Proyecto-de-Titulo
export APP_NAME=leica-inventario
export ADMIN_EMAIL=encargado@inacapmail.cl
export ADMIN_PASSWORD='una-clave-segura'
bash azure/crear_infraestructura.sh
```

`APP_NAME` define la URL (`https://APP_NAME.azurewebsites.net`) y debe ser única en Azure. El script crea
el grupo de recursos, el servidor PostgreSQL con su base, el plan y la aplicación, y configura las
variables de entorno, el comando de inicio, HTTPS obligatorio, TLS 1.2 y el health check. Al terminar
muestra la clave de la base de datos y el perfil de publicación.

Variables opcionales:

| Variable | Valor por defecto |
|---|---|
| `LOCATION` | `brazilsouth` (usa `chilecentral` si tu suscripción tiene esa región) |
| `RESOURCE_GROUP` | `rg-leica-inventario` |
| `PLAN_SKU` | `B1` (`F1` es gratuito, sin Always On y con 60 minutos de CPU al día) |
| `PYTHON_VERSION` | `3.14` (usa `3.13` si App Service aún no ofrece 3.14) |
| `PG_VERSION` | `17` |
| `GEMINI_API_KEY` | vacío |

### 2. Conectar GitHub Actions

En el repositorio de GitHub, **Settings → Secrets and variables → Actions**:

- **Secrets → New repository secret:** `AZURE_WEBAPP_PUBLISH_PROFILE`, con el XML completo que mostró el script.
- **Variables → New repository variable:** `AZURE_WEBAPP_NAME`, con el valor de `APP_NAME`.

Desde ese momento, cada push a `main` ejecuta las pruebas contra PostgreSQL y, solo si todas pasan,
despliega en App Service. Los Pull Requests ejecutan las pruebas sin desplegar. Para el primer
despliegue, entra a **Actions → CI/CD → Run workflow**.

### 3. Operación

- En cada arranque, `startup.sh` aplica las migraciones, genera los archivos estáticos, crea el
  administrador (solo si no existe) e inicia Gunicorn.
- Los logs se ven en el portal, en **App Service → Log stream**.
- `GET /salud/` responde `{"estado": "ok", "base_de_datos": "ok"}` o un 503 si la base no está disponible.
- Azure respalda la base automáticamente (7 días, restauración a cualquier minuto). Además,
  `python manage.py respaldar` y `python manage.py restaurar` generan y restauran respaldos propios
  verificados con SHA-256. La política y los procedimientos están en [docs/respaldos.md](docs/respaldos.md).

### Alternativa: Render

El repositorio también incluye `render.yaml` y `build.sh`. En [Render](https://render.com), entra a
**New → Blueprint**, conecta el repositorio y completa `ADMIN_EMAIL`, `ADMIN_PASSWORD` y, si quieres,
`GEMINI_API_KEY`.

## Estructura

```
leica_project/        Configuración de Django (settings, urls, wsgi)
inventario/
  models.py           Usuario, Equipo, Insumo, Solicitud, Movimiento, Bloqueo, Mantenimiento, Migracion
  views.py            Lógica de negocio de cada pantalla
  templates/          Plantillas HTML
  static/             CSS e imágenes
  migrations/         Migraciones de la base de datos
  management/commands/ seed, respaldar, restaurar, marcar_atrasadas, crear_admin
  tests/              Suite de tests
azure/                Script de infraestructura
docs/respaldos.md     Política y procedimientos de respaldo
```

Hubo un prototipo anterior en Node/Express. Ya no forma parte del proyecto y se conserva en la
etiqueta git `archivo/prototipo-node`.
