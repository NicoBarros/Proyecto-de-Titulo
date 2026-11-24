# Protección de datos personales (Ley N.° 21.719)

Registro de las actividades de tratamiento del sistema de inventario LEICA y de cómo se cumplen los
principios y derechos de la Ley N.° 19.628, modificada por la Ley N.° 21.719 (RNF-09 y RNF-11).

## Responsable

INACAP Sede Valdivia, a través del Laboratorio LEICA. El contacto que aparece en el aviso de privacidad
se configura con `PRIVACIDAD_CONTACTO`.

## Registro de actividades de tratamiento

| Actividad | Datos | Titulares | Finalidad | Base de licitud | Conservación | Dónde |
|---|---|---|---|---|---|---|
| Cuentas y permisos | Nombre, correo institucional, rol, sección, contraseña (hash) | Estudiantes, docentes, personal | Autenticar y autorizar según el rol | Relación académica o laboral con INACAP | Mientras la cuenta esté vigente | `Usuario` |
| Préstamos | Solicitudes, ítems, entregas, devoluciones, justificación, motivo de rechazo | Solicitantes y representados | Gestionar préstamos y trazabilidad para auditorías | Relación académica; interés legítimo en el resguardo del inventario | Mientras exista el registro; se anonimizan al suprimir la cuenta | `Solicitud`, `SolicitudItem`, `Movimiento` |
| Sanciones | Bloqueos, sección, fecha de término | Solicitantes con atraso | Aplicar la política de devoluciones | Reglamento del laboratorio | Mientras exista el registro | `Bloqueo` |
| Búsqueda con IA | Texto de la búsqueda, equipos recuperados, respuesta, calificación | Usuarios que buscan | Responder la búsqueda y medir su calidad | Interés legítimo en mejorar el servicio | Asociada al usuario `RETENCION_BUSQUEDAS_DIAS` (365); después sin identificar | `BusquedaIA` |
| Seguridad | Inicios y cierres de sesión, intentos fallidos, IP, navegador | Todos | Proteger las cuentas y detectar accesos indebidos | Obligación de seguridad del responsable | `RETENCION_EVENTOS_DIAS` (365) | `EventoSeguridad` |
| Derechos del titular | Tipo, detalle, respuesta | Titulares que ejercen derechos | Atender y acreditar la respuesta | Obligación legal | Mientras exista el registro | `SolicitudDerecho` |

## Principios

- **Licitud y finalidad:** los datos solo se usan para las finalidades del registro. El aviso de privacidad
  (`/privacidad/`) se enlaza desde el inicio de sesión y el pie de todas las páginas.
- **Proporcionalidad:** el sistema no pide RUT, teléfono, domicilio ni datos sensibles. Gemini recibe solo
  la consulta y fragmentos del catálogo de equipos (RNF-11); nunca nombre, correo ni historial.
- **Calidad:** el titular ve sus datos en "Mis datos" y puede pedir su rectificación.
- **Responsabilidad:** las solicitudes de derechos, sus respuestas y quién las resolvió quedan registradas.
- **Seguridad:** HTTPS obligatorio con HSTS, contraseñas con hash, bloqueo por intentos fallidos
  (django-axes), acceso por roles, registro de eventos de seguridad, respaldos con verificación SHA-256.
- **Conservación limitada:** las tareas programadas desvinculan las búsquedas antiguas de su autor y
  eliminan los eventos de seguridad vencidos.

## Derechos del titular

| Derecho | Cómo se ejerce | Efecto en el sistema |
|---|---|---|
| Acceso | "Mis datos" muestra perfil y resumen | Inmediato |
| Portabilidad | "Descargar mis datos" entrega un JSON con perfil, solicitudes, bloqueos, búsquedas, eventos y solicitudes de derechos | Inmediato |
| Rectificación | Solicitud desde "Mis datos" | El administrador corrige en el panel y responde |
| Supresión | Solicitud desde "Mis datos" | Al aceptarla, la cuenta se anonimiza: nombre, correo, sección y contraseña se reemplazan, las búsquedas y eventos de seguridad se desvinculan y la cuenta se cierra. Los préstamos se conservan sin datos identificables. No procede con préstamos en curso. |
| Oposición | Solicitud desde "Mis datos" | El administrador evalúa y responde |
| Bloqueo | Solicitud desde "Mis datos" | Al aceptarla, la cuenta se suspende |

Las solicitudes llegan por correo a los superusuarios y se resuelven en el panel de administración. El
plazo interno de respuesta es `PLAZO_DERECHOS_DIAS` (30 días); verificar que coincida con el plazo legal
vigente. Al resolverlas se avisa al titular por correo.

## Cifrado en reposo

- **Azure:** Azure Database for PostgreSQL Flexible Server cifra los datos y respaldos en reposo con
  AES-256 por defecto.
- **Servidor de LEICA:** antes de pasar a producción, cifrar el volumen de la base de datos y el disco de
  respaldos (LUKS en Linux o BitLocker en Windows) y guardar la clave de recuperación fuera del servidor.

## Encargados del tratamiento

| Proveedor | Datos que recibe | Uso |
|---|---|---|
| Microsoft Azure | Base de datos completa | Alojamiento del entorno de pruebas |
| Google Gemini | Texto de la búsqueda y fragmentos del catálogo | Redacción de la respuesta de búsqueda |
| Correo institucional (SMTP) | Correo y nombre del destinatario, datos de la solicitud | Avisos del sistema |
