// Conexion a la base de datos relacional (SQLite para desarrollo/prototipo).
//
// NOTA DE ARQUITECTURA (ver seccion VII de la Formulacion del Proyecto de Titulo):
// el proyecto define una arquitectura cliente-servidor de tres capas con una
// base de datos relacional alojada en el servidor on-premise de LEICA. Se usa
// SQLite aqui para que el prototipo corra sin instalar un motor de BD aparte;
// para producción basta con migrar schema.sql a PostgreSQL/MySQL y reemplazar
// este archivo por un pool de conexiones (pg / mysql2), ya que toda la logica
// de negocio vive en las rutas (src/routes), no en este modulo.

const path = require('path');
const fs = require('fs');
const Database = require('better-sqlite3');

const DB_PATH = process.env.DB_PATH || path.join(__dirname, '..', '..', 'data', 'leica.db');

fs.mkdirSync(path.dirname(DB_PATH), { recursive: true });

const db = new Database(DB_PATH);
db.pragma('journal_mode = WAL'); // permite lecturas concurrentes mientras se escribe (apoya RF-02)
db.pragma('foreign_keys = ON');

function initSchema() {
  const schema = fs.readFileSync(path.join(__dirname, 'schema.sql'), 'utf8');
  db.exec(schema);
}

initSchema();

module.exports = db;
