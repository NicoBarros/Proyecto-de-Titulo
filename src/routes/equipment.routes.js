// RF-01: registrar un equipo activo con codigo unico, modelo y estado,
//        visible para todos los roles de lectura.
// RF-02: edicion concurrente del inventario por al menos dos usuarios sin
//        bloqueos mutuos -> se implementa con bloqueo optimista por fila
//        (columna "version"): dos personas pueden editar DOS EQUIPOS
//        DISTINTOS al mismo tiempo sin esperar; si dos ediciones chocan
//        sobre el MISMO equipo, la segunda recibe 409 y debe refrescar,
//        en vez de bloquear todo el archivo como ocurria con el Excel.
// RF-04: solo encargado_laboratorio y control_calidad pueden escribir.
const express = require('express');
const db = require('../db/db');
const { requireAuth, requireRole, ROLES_ESCRITURA_INVENTARIO } = require('../middleware/auth');

const router = express.Router();

router.use(requireAuth); // todos los roles autenticados tienen al menos lectura

router.get('/', (req, res) => {
  const { estado, q } = req.query;
  let sql = 'SELECT * FROM equipos WHERE 1=1';
  const params = [];
  if (estado) { sql += ' AND estado = ?'; params.push(estado); }
  if (q) { sql += ' AND (nombre LIKE ? OR codigo_inventario LIKE ? OR modelo LIKE ?)'; params.push(`%${q}%`, `%${q}%`, `%${q}%`); }
  sql += ' ORDER BY nombre';
  res.json(db.prepare(sql).all(...params));
});

router.get('/:id', (req, res) => {
  const equipo = db.prepare('SELECT * FROM equipos WHERE id = ?').get(req.params.id);
  if (!equipo) return res.status(404).json({ error: 'Equipo no encontrado.' });
  res.json(equipo);
});

router.post('/', requireRole(...ROLES_ESCRITURA_INVENTARIO), (req, res) => {
  const { codigo_inventario, nombre, modelo, especificaciones, ubicacion, valor_adquisicion } = req.body;
  if (!codigo_inventario || !nombre) {
    return res.status(400).json({ error: 'codigo_inventario y nombre son obligatorios.' });
  }
  try {
    const info = db.prepare(`
      INSERT INTO equipos (codigo_inventario, nombre, modelo, especificaciones, ubicacion, valor_adquisicion)
      VALUES (?, ?, ?, ?, ?, ?)
    `).run(codigo_inventario, nombre, modelo || null, especificaciones || null, ubicacion || null, valor_adquisicion || null);
    const equipo = db.prepare('SELECT * FROM equipos WHERE id = ?').get(info.lastInsertRowid);
    res.status(201).json(equipo);
  } catch (err) {
    if (String(err).includes('UNIQUE')) {
      return res.status(409).json({ error: `El codigo de inventario '${codigo_inventario}' ya existe.` });
    }
    res.status(500).json({ error: 'Error al crear el equipo.' });
  }
});

// PUT con bloqueo optimista: el cliente debe enviar la "version" que tenia
// cuando cargo el registro. Si alguien mas lo modifico entremedio, se
// rechaza con 409 en vez de permitir que un cambio pise al otro en silencio.
router.put('/:id', requireRole(...ROLES_ESCRITURA_INVENTARIO), (req, res) => {
  const { version, nombre, modelo, especificaciones, ubicacion, estado, valor_adquisicion } = req.body;
  if (version === undefined) return res.status(400).json({ error: 'Falta "version" para controlar edicion concurrente (RF-02).' });

  const actual = db.prepare('SELECT * FROM equipos WHERE id = ?').get(req.params.id);
  if (!actual) return res.status(404).json({ error: 'Equipo no encontrado.' });

  const result = db.prepare(`
    UPDATE equipos SET
      nombre = COALESCE(?, nombre),
      modelo = COALESCE(?, modelo),
      especificaciones = COALESCE(?, especificaciones),
      ubicacion = COALESCE(?, ubicacion),
      estado = COALESCE(?, estado),
      valor_adquisicion = COALESCE(?, valor_adquisicion),
      version = version + 1,
      updated_at = datetime('now')
    WHERE id = ? AND version = ?
  `).run(nombre, modelo, especificaciones, ubicacion, estado, valor_adquisicion, req.params.id, version);

  if (result.changes === 0) {
    return res.status(409).json({
      error: 'Conflicto de edicion: otro usuario modifico este equipo despues de que lo cargaste. Vuelve a cargarlo e intenta de nuevo.',
      actual,
    });
  }
  res.json(db.prepare('SELECT * FROM equipos WHERE id = ?').get(req.params.id));
});

router.delete('/:id', requireRole(...ROLES_ESCRITURA_INVENTARIO), (req, res) => {
  const result = db.prepare('DELETE FROM equipos WHERE id = ?').run(req.params.id);
  if (result.changes === 0) return res.status(404).json({ error: 'Equipo no encontrado.' });
  res.status(204).send();
});

module.exports = router;
