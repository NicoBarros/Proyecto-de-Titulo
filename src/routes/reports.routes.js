// RF-13 (HU-13): El sistema debe generar reportes agregados de uso del
// inventario (equipos mas solicitados, prestamos vencidos, equipos sin
// movimiento) sin permitir edicion desde ese reporte -> por eso estas rutas
// son solo GET.
const express = require('express');
const db = require('../db/db');
const { requireAuth } = require('../middleware/auth');

const router = express.Router();
router.use(requireAuth);

router.get('/equipos-mas-solicitados', (req, res) => {
  res.json(db.prepare(`
    SELECT e.id, e.nombre, e.codigo_inventario, COUNT(si.id) AS veces_solicitado
    FROM solicitud_items si
    JOIN equipos e ON e.id = si.equipo_id
    GROUP BY e.id
    ORDER BY veces_solicitado DESC
    LIMIT 20
  `).all());
});

router.get('/prestamos-vencidos', (req, res) => {
  res.json(db.prepare(`
    SELECT s.*, u.nombre AS solicitante_nombre, u.email AS solicitante_email
    FROM solicitudes s
    JOIN usuarios u ON u.id = s.solicitante_id
    WHERE s.estado = 'entregada' AND s.horario_fin < datetime('now')
  `).all());
});

router.get('/equipos-sin-movimiento', (req, res) => {
  const { dias = 90 } = req.query;
  res.json(db.prepare(`
    SELECT e.*
    FROM equipos e
    WHERE e.id NOT IN (
      SELECT DISTINCT si.equipo_id FROM solicitud_items si
      JOIN solicitudes s ON s.id = si.solicitud_id
      WHERE si.equipo_id IS NOT NULL AND s.created_at >= datetime('now', '-' || ? || ' days')
    )
  `).all(dias));
});

router.get('/resumen', (req, res) => {
  const totales = db.prepare(`
    SELECT
      (SELECT COUNT(*) FROM equipos) AS total_equipos,
      (SELECT COUNT(*) FROM equipos WHERE estado = 'disponible') AS equipos_disponibles,
      (SELECT COUNT(*) FROM equipos WHERE estado = 'prestado') AS equipos_prestados,
      (SELECT COUNT(*) FROM equipos WHERE estado = 'en_mantenimiento') AS equipos_mantenimiento,
      (SELECT COUNT(*) FROM solicitudes WHERE estado = 'pendiente') AS solicitudes_pendientes,
      (SELECT COUNT(*) FROM solicitudes WHERE estado = 'atrasada') AS solicitudes_atrasadas,
      (SELECT COUNT(*) FROM insumos WHERE cantidad_disponible <= umbral_minimo) AS insumos_bajo_stock
  `).get();
  res.json(totales);
});

module.exports = router;
