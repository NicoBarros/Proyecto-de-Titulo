// RF-03: registrar insumos por cantidad (sin codigo individual), descontando
//        stock al prestarse y validando que no quede negativo.
// Incluye los hallazgos de la entrevista (Anexo 6, #16): distincion entre
// insumo renovable/perecible y aviso de stock bajo (umbral_minimo).
const express = require('express');
const db = require('../db/db');
const { requireAuth, requireRole, ROLES_ESCRITURA_INVENTARIO } = require('../middleware/auth');

const router = express.Router();
router.use(requireAuth);

router.get('/', (req, res) => {
  const { bajo_stock } = req.query;
  let sql = 'SELECT * FROM insumos';
  if (bajo_stock === 'true') sql += ' WHERE cantidad_disponible <= umbral_minimo';
  sql += ' ORDER BY nombre';
  res.json(db.prepare(sql).all());
});

router.post('/', requireRole(...ROLES_ESCRITURA_INVENTARIO), (req, res) => {
  const { nombre, categoria, tipo, cantidad_total, umbral_minimo } = req.body;
  if (!nombre || cantidad_total === undefined) {
    return res.status(400).json({ error: 'nombre y cantidad_total son obligatorios.' });
  }
  const info = db.prepare(`
    INSERT INTO insumos (nombre, categoria, tipo, cantidad_total, cantidad_disponible, umbral_minimo)
    VALUES (?, ?, ?, ?, ?, ?)
  `).run(nombre, categoria || null, tipo || 'perecible', cantidad_total, cantidad_total, umbral_minimo || 0);
  res.status(201).json(db.prepare('SELECT * FROM insumos WHERE id = ?').get(info.lastInsertRowid));
});

router.put('/:id', requireRole(...ROLES_ESCRITURA_INVENTARIO), (req, res) => {
  const { version, nombre, categoria, tipo, cantidad_total, umbral_minimo } = req.body;
  if (version === undefined) return res.status(400).json({ error: 'Falta "version".' });
  const result = db.prepare(`
    UPDATE insumos SET
      nombre = COALESCE(?, nombre),
      categoria = COALESCE(?, categoria),
      tipo = COALESCE(?, tipo),
      cantidad_total = COALESCE(?, cantidad_total),
      umbral_minimo = COALESCE(?, umbral_minimo),
      version = version + 1,
      updated_at = datetime('now')
    WHERE id = ? AND version = ?
  `).run(nombre, categoria, tipo, cantidad_total, umbral_minimo, req.params.id, version);
  if (result.changes === 0) return res.status(409).json({ error: 'Conflicto de version. Vuelve a cargar el registro.' });
  res.json(db.prepare('SELECT * FROM insumos WHERE id = ?').get(req.params.id));
});

router.delete('/:id', requireRole(...ROLES_ESCRITURA_INVENTARIO), (req, res) => {
  const result = db.prepare('DELETE FROM insumos WHERE id = ?').run(req.params.id);
  if (result.changes === 0) return res.status(404).json({ error: 'Insumo no encontrado.' });
  res.status(204).send();
});

module.exports = router;
