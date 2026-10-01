-- Esquema de base de datos - Sistema de Gestion de Inventario LEICA
-- Cubre RF-01 a RF-14 segun Formulacion de Proyecto de Titulo

PRAGMA foreign_keys = ON;

-- RF-04 / RF-05: usuarios y roles (autenticacion por correo institucional)
CREATE TABLE IF NOT EXISTS usuarios (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL UNIQUE,
  nombre TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  rol TEXT NOT NULL CHECK (rol IN (
    'estudiante', 'docente', 'director_carrera',
    'encargado_laboratorio', 'control_calidad', 'comite_ejecutivo'
  )),
  seccion TEXT,                 -- para estudiantes (usado en bloqueos RF-09)
  activo INTEGER NOT NULL DEFAULT 1,
  bloqueado_hasta TEXT,         -- RF-09: fecha ISO hasta la cual el usuario esta bloqueado
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- RF-01: equipos activos (con codigo unico)
CREATE TABLE IF NOT EXISTS equipos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  codigo_inventario TEXT NOT NULL UNIQUE,
  nombre TEXT NOT NULL,
  modelo TEXT,
  especificaciones TEXT,
  ubicacion TEXT,
  estado TEXT NOT NULL DEFAULT 'disponible' CHECK (estado IN (
    'disponible', 'prestado', 'en_mantenimiento', 'fuera_servicio'
  )),
  valor_adquisicion REAL,
  version INTEGER NOT NULL DEFAULT 1,  -- RF-02: control de edicion concurrente (optimistic locking)
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- RF-03: insumos (por cantidad, sin codigo individual)
CREATE TABLE IF NOT EXISTS insumos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nombre TEXT NOT NULL,
  categoria TEXT,
  tipo TEXT NOT NULL DEFAULT 'perecible' CHECK (tipo IN ('renovable', 'perecible')), -- hallazgo entrevista (Anexo 6, #16)
  cantidad_total INTEGER NOT NULL DEFAULT 0,
  cantidad_disponible INTEGER NOT NULL DEFAULT 0,
  umbral_minimo INTEGER NOT NULL DEFAULT 0,   -- hallazgo entrevista: aviso de stock bajo
  version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- RF-06/RF-07: solicitudes
CREATE TABLE IF NOT EXISTS solicitudes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  solicitante_id INTEGER NOT NULL REFERENCES usuarios(id),
  en_representacion_de INTEGER REFERENCES usuarios(id), -- si el solicitante es docente/director actuando por un estudiante
  lugar_uso TEXT NOT NULL DEFAULT 'dentro_sede' CHECK (lugar_uso IN ('dentro_sede', 'fuera_sede')), -- hallazgo entrevista #7
  justificacion TEXT,
  horario_inicio TEXT NOT NULL,
  horario_fin TEXT NOT NULL,
  estado TEXT NOT NULL DEFAULT 'pendiente' CHECK (estado IN (
    'pendiente', 'aprobada', 'rechazada', 'entregada', 'devuelta', 'atrasada', 'cancelada'
  )),
  aprobado_por INTEGER REFERENCES usuarios(id),
  fecha_aprobacion TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Detalle de la solicitud: permite varios equipos/insumos por solicitud (kits) - hallazgo entrevista #11
CREATE TABLE IF NOT EXISTS solicitud_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  solicitud_id INTEGER NOT NULL REFERENCES solicitudes(id) ON DELETE CASCADE,
  equipo_id INTEGER REFERENCES equipos(id),
  insumo_id INTEGER REFERENCES insumos(id),
  cantidad INTEGER NOT NULL DEFAULT 1,
  CHECK ((equipo_id IS NOT NULL AND insumo_id IS NULL) OR (equipo_id IS NULL AND insumo_id IS NOT NULL))
);

-- RF-08 / RNF-07: trazabilidad de movimientos (entrega / devolucion)
CREATE TABLE IF NOT EXISTS movimientos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  solicitud_id INTEGER NOT NULL REFERENCES solicitudes(id),
  tipo TEXT NOT NULL CHECK (tipo IN ('entrega', 'devolucion')),
  fecha TEXT NOT NULL DEFAULT (datetime('now')),
  responsable_id INTEGER NOT NULL REFERENCES usuarios(id),
  estado_equipo TEXT,       -- RF-08 / hallazgo #13: condicion al devolver
  observacion TEXT
);

-- RF-09: bloqueos automaticos por atraso
CREATE TABLE IF NOT EXISTS bloqueos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
  seccion TEXT,
  solicitud_id INTEGER REFERENCES solicitudes(id),
  fecha_inicio TEXT NOT NULL DEFAULT (datetime('now')),
  fecha_fin TEXT NOT NULL,   -- maximo 1 semana segun entrevista (hallazgo #10)
  motivo TEXT
);

-- RF-10: mantenimiento y regla del 70%
CREATE TABLE IF NOT EXISTS mantenimientos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  equipo_id INTEGER NOT NULL REFERENCES equipos(id),
  falla_descrita TEXT,
  costo_cotizado REAL,
  porcentaje_costo REAL,     -- costo_cotizado / valor_adquisicion
  decision TEXT CHECK (decision IN ('reparar', 'dar_baja', 'pendiente')) DEFAULT 'pendiente',
  fecha_diagnostico TEXT NOT NULL DEFAULT (datetime('now')),
  fecha_resolucion TEXT,
  reportado_por INTEGER REFERENCES usuarios(id)
);

-- RF-14: registro de migraciones desde la planilla Excel/SharePoint
CREATE TABLE IF NOT EXISTS migraciones (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  archivo_origen TEXT,
  filas_totales INTEGER,
  filas_importadas INTEGER,
  filas_con_error INTEGER,
  detalle_errores TEXT,
  ejecutado_por INTEGER REFERENCES usuarios(id),
  fecha TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_equipos_estado ON equipos(estado);
CREATE INDEX IF NOT EXISTS idx_solicitudes_estado ON solicitudes(estado);
CREATE INDEX IF NOT EXISTS idx_solicitudes_solicitante ON solicitudes(solicitante_id);
CREATE INDEX IF NOT EXISTS idx_movimientos_solicitud ON movimientos(solicitud_id);
