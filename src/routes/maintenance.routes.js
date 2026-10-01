// RF-10: derivar un equipo dañado a mantenimiento y aplicar la regla de
//        costo: si la cotizacion de reparacion es >= 70% del valor del
//        equipo, se sugiere darlo de baja; si es menor, se sugiere repararlo.
const express = require('express');
const db = require('../db/db');
const { requireAuth, requireRole, ROLES_ESCRITURA_INVENTARIO } = require('../middleware/auth');

const router = express.Router();
router.use(requireAuth);

router.get('/', (req, res) => {
  res.json(db.prepare(`
    SELECT m.*, e.nombre AS equipo_nombre, e.codigo_inventario
    FROM mantenimientos m JOIN equipos e ON e.id = m.equipo_id
    ORDER BY m.fecha_diagnostico DESC
  `).all());
});

// Registrar diagnostico + cotizacion -> el sistema SUGIERE la decision.
router.post('/', requireRole(...ROLES_ESCRITURA_INVENTARIO), (req, res) => {
  const { equipo_id, falla_descrita, costo_cotizado } = req.body;
  const equipo = db.prepare('SELECT * FROM equipos WHERE id = ?').get(equipo_id);
  if (!equipo) return res.status(404).json({ error: 'Equipo no encontrado.' });

  let porcentaje = null;
  let sugerencia = 'pendiente';
  if (equipo.valor_adquisicion && costo_cotizado !== undefined) {
    porcentaje = costo_cotizado / equipo.valor_adquisicion;
    sugerencia = porcentaje >= 0.70 ? 'dar_baja' : 'reparar';
  }

  const info = db.prepare(`
    INSERT INTO mantenimientos (equipo_id, falla_descrita, costo_cotizado, porcentaje_costo, decision, reportado_por)
    VALUES (?, ?, ?, ?, ?, ?)
  `).run(equipo_id, falla_descrita || null, costo_cotizado ?? null, porcentaje, sugerencia, req.user.id);

  db.prepare(`UPDATE equipos SET estado = 'en_mantenimiento', version = version + 1 WHERE id = ?`).run(equipo_id);

  res.status(201).json({
    ...db.prepare('SELECT * FROM mantenimientos WHERE id = ?').get(info.lastInsertRowid),
    sugerencia_explicacion: porcentaje !== null
      ? `Costo = ${(porcentaje * 100).toFixed(1)}% del valor del equipo (umbral: 70%) -> se sugiere '${sugerencia}'.`
      : 'Falta valor_adquisicion del equipo o costo_cotizado para calcular la sugerencia.',
  });
});

// Confirmar la decision final (reparar / dar_baja) y cerrar el caso.
router.post('/:id/resolver', requireRole(...ROLES_ESCRITURA_INVENTARIO), (req, res) => {
  const { decision } = req.body; // 'reparar' | 'dar_baja'
  if (!['reparar', 'dar_baja'].includes(decision)) {
    return res.status(400).json({ error: "decision debe ser 'reparar' o 'dar_baja'." });
  }
  const mantenimiento = db.prepare('SELECT * FROM mantenimientos WHERE id = ?').get(req.params.id);
  if (!mantenimiento) return res.status(404).json({ error: 'Registro de mantenimiento no encontrado.' });

  db.prepare(`UPDATE mantenimientos SET decision = ?, fecha_resolucion = datetime('now') WHERE id = ?`).run(decision, req.params.id);
  const nuevoEstadoEquipo = decision === 'dar_baja' ? 'fuera_servicio' : 'disponible';
  db.prepare(`UPDATE equipos SET estado = ?, version = version + 1 WHERE id = ?`).run(nuevoEstadoEquipo, mantenimiento.equipo_id);

  res.json(db.prepare('SELECT * FROM mantenimientos WHERE id = ?').get(req.params.id));
});

module.exports = router;
