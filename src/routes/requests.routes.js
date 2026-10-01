// RF-06: marcar una solicitud como realizada en representacion de un
//        estudiante, derivandola a autorizacion de un docente o Director de
//        Carrera. Tambien cubre el hallazgo de la entrevista (Anexo 6, #7 y
//        #11): lugar de uso (dentro/fuera de sede) y solicitudes multi-item
//        (kits).
// RF-07: validar disponibilidad del equipo en tiempo real, impidiendo
//        aprobar dos solicitudes simultaneas sobre el mismo equipo/horario.
// RF-08: registrar la salida y devolucion con fecha, responsable y
//        observacion de estado, manteniendo trazabilidad completa.
// RF-09: bloquear automaticamente la cuenta de un solicitante (y su
//        seccion) que no devuelva un equipo dentro del plazo (max. 1 semana,
//        segun Anexo 6 #10).
const express = require('express');
const db = require('../db/db');
const { requireAuth, requireRole, ROLES_APROBADORES } = require('../middleware/auth');

const router = express.Router();
router.use(requireAuth);

// --- Crear solicitud -------------------------------------------------
// body: { en_representacion_de?, lugar_uso, justificacion, horario_inicio,
//         horario_fin, items: [{ equipo_id | insumo_id, cantidad }] }
router.post('/', (req, res) => {
  const { en_representacion_de, lugar_uso, justificacion, horario_inicio, horario_fin, items } = req.body;
  if (!horario_inicio || !horario_fin || !Array.isArray(items) || items.length === 0) {
    return res.status(400).json({ error: 'horario_inicio, horario_fin y al menos un item son obligatorios.' });
  }

  const insert = db.transaction(() => {
    const info = db.prepare(`
      INSERT INTO solicitudes (solicitante_id, en_representacion_de, lugar_uso, justificacion, horario_inicio, horario_fin)
      VALUES (?, ?, ?, ?, ?, ?)
    `).run(req.user.id, en_representacion_de || null, lugar_uso || 'dentro_sede', justificacion || null, horario_inicio, horario_fin);

    const itemStmt = db.prepare('INSERT INTO solicitud_items (solicitud_id, equipo_id, insumo_id, cantidad) VALUES (?, ?, ?, ?)');
    for (const item of items) {
      itemStmt.run(info.lastInsertRowid, item.equipo_id || null, item.insumo_id || null, item.cantidad || 1);
    }
    return info.lastInsertRowid;
  });

  const id = insert();
  res.status(201).json(getSolicitudCompleta(id));
});

router.get('/', (req, res) => {
  const { estado, mias } = req.query;
  let sql = 'SELECT * FROM solicitudes WHERE 1=1';
  const params = [];
  if (estado) { sql += ' AND estado = ?'; params.push(estado); }
  if (mias === 'true') { sql += ' AND solicitante_id = ?'; params.push(req.user.id); }
  sql += ' ORDER BY created_at DESC';
  const rows = db.prepare(sql).all(...params);
  res.json(rows.map((r) => getSolicitudCompleta(r.id)));
});

router.get('/:id', (req, res) => {
  const s = getSolicitudCompleta(req.params.id);
  if (!s) return res.status(404).json({ error: 'Solicitud no encontrada.' });
  res.json(s);
});

function getSolicitudCompleta(id) {
  const solicitud = db.prepare('SELECT * FROM solicitudes WHERE id = ?').get(id);
  if (!solicitud) return null;
  const items = db.prepare(`
    SELECT si.*, e.nombre AS equipo_nombre, e.codigo_inventario, i.nombre AS insumo_nombre
    FROM solicitud_items si
    LEFT JOIN equipos e ON e.id = si.equipo_id
    LEFT JOIN insumos i ON i.id = si.insumo_id
    WHERE si.solicitud_id = ?
  `).all(id);
  const movimientos = db.prepare('SELECT * FROM movimientos WHERE solicitud_id = ? ORDER BY fecha').all(id);
  return { ...solicitud, items, movimientos };
}

// --- Aprobar / rechazar (RF-06, RF-07) --------------------------------
router.post('/:id/aprobar', requireRole(...ROLES_APROBADORES), (req, res) => {
  const solicitud = db.prepare('SELECT * FROM solicitudes WHERE id = ?').get(req.params.id);
  if (!solicitud) return res.status(404).json({ error: 'Solicitud no encontrada.' });
  if (solicitud.estado !== 'pendiente') return res.status(409).json({ error: `La solicitud ya esta en estado '${solicitud.estado}'.` });

  // RF-07: no permitir dos solicitudes aprobadas sobre el mismo equipo con
  // horario que se superponga.
  const items = db.prepare('SELECT * FROM solicitud_items WHERE solicitud_id = ?').all(solicitud.id);
  for (const item of items) {
    if (!item.equipo_id) continue;
    const choque = db.prepare(`
      SELECT s.id FROM solicitudes s
      JOIN solicitud_items si ON si.solicitud_id = s.id
      WHERE si.equipo_id = ?
        AND s.id != ?
        AND s.estado IN ('aprobada', 'entregada')
        AND NOT (s.horario_fin <= ? OR s.horario_inicio >= ?)
    `).get(item.equipo_id, solicitud.id, solicitud.horario_inicio, solicitud.horario_fin);
    if (choque) {
      return res.status(409).json({ error: `El equipo id=${item.equipo_id} ya esta reservado en un horario que se superpone (solicitud #${choque.id}).` });
    }
  }

  db.prepare(`
    UPDATE solicitudes SET estado = 'aprobada', aprobado_por = ?, fecha_aprobacion = datetime('now') WHERE id = ?
  `).run(req.user.id, solicitud.id);
  res.json(getSolicitudCompleta(solicitud.id));
});

router.post('/:id/rechazar', requireRole(...ROLES_APROBADORES), (req, res) => {
  const result = db.prepare(`UPDATE solicitudes SET estado = 'rechazada' WHERE id = ? AND estado = 'pendiente'`).run(req.params.id);
  if (result.changes === 0) return res.status(409).json({ error: 'Solo se puede rechazar una solicitud pendiente.' });
  res.json(getSolicitudCompleta(req.params.id));
});

// --- Entrega (RF-08) ---------------------------------------------------
router.post('/:id/entregar', requireRole(...ROLES_APROBADORES), (req, res) => {
  const solicitud = db.prepare('SELECT * FROM solicitudes WHERE id = ?').get(req.params.id);
  if (!solicitud) return res.status(404).json({ error: 'Solicitud no encontrada.' });
  if (solicitud.estado !== 'aprobada') return res.status(409).json({ error: 'Solo se puede entregar una solicitud aprobada.' });

  const items = db.prepare('SELECT * FROM solicitud_items WHERE solicitud_id = ?').all(solicitud.id);
  const entregar = db.transaction(() => {
    for (const item of items) {
      if (item.equipo_id) {
        db.prepare(`UPDATE equipos SET estado = 'prestado', version = version + 1, updated_at = datetime('now') WHERE id = ?`).run(item.equipo_id);
      } else if (item.insumo_id) {
        // RF-03: descuenta stock sin dejarlo negativo
        const insumo = db.prepare('SELECT * FROM insumos WHERE id = ?').get(item.insumo_id);
        if (!insumo || insumo.cantidad_disponible < item.cantidad) {
          throw new Error(`Stock insuficiente para el insumo id=${item.insumo_id}.`);
        }
        db.prepare(`UPDATE insumos SET cantidad_disponible = cantidad_disponible - ?, version = version + 1 WHERE id = ?`).run(item.cantidad, item.insumo_id);
      }
    }
    db.prepare(`UPDATE solicitudes SET estado = 'entregada' WHERE id = ?`).run(solicitud.id);
    db.prepare(`INSERT INTO movimientos (solicitud_id, tipo, responsable_id, observacion) VALUES (?, 'entrega', ?, ?)`)
      .run(solicitud.id, req.user.id, req.body.observacion || null);
  });

  try {
    entregar();
  } catch (err) {
    return res.status(409).json({ error: err.message });
  }
  res.json(getSolicitudCompleta(solicitud.id));
});

// --- Devolucion (RF-08, RF-09, RF-10 vinculado via mantenimiento) ------
// body: { estado_equipo: 'excelente'|'bueno'|'dañado'|'inservible', observacion, atrasada }
router.post('/:id/devolver', requireRole(...ROLES_APROBADORES), (req, res) => {
  const solicitud = db.prepare('SELECT * FROM solicitudes WHERE id = ?').get(req.params.id);
  if (!solicitud) return res.status(404).json({ error: 'Solicitud no encontrada.' });
  if (solicitud.estado !== 'entregada') return res.status(409).json({ error: 'Solo se puede devolver una solicitud entregada.' });

  const { estado_equipo, observacion } = req.body;
  const atrasada = new Date() > new Date(solicitud.horario_fin);
  const items = db.prepare('SELECT * FROM solicitud_items WHERE solicitud_id = ?').all(solicitud.id);

  const devolver = db.transaction(() => {
    for (const item of items) {
      if (item.equipo_id) {
        const nuevoEstado = estado_equipo === 'dañado' || estado_equipo === 'inservible' ? 'en_mantenimiento' : 'disponible';
        db.prepare(`UPDATE equipos SET estado = ?, version = version + 1, updated_at = datetime('now') WHERE id = ?`).run(nuevoEstado, item.equipo_id);
      } else if (item.insumo_id) {
        const insumo = db.prepare('SELECT * FROM insumos WHERE id = ?').get(item.insumo_id);
        if (insumo && insumo.tipo === 'renovable') {
          // hallazgo entrevista (Anexo 6, #16): solo el insumo renovable vuelve al stock
          db.prepare(`UPDATE insumos SET cantidad_disponible = cantidad_disponible + ?, version = version + 1 WHERE id = ?`).run(item.cantidad, item.insumo_id);
        }
      }
    }

    db.prepare(`UPDATE solicitudes SET estado = ? WHERE id = ?`).run(atrasada ? 'atrasada' : 'devuelta', solicitud.id);
    db.prepare(`INSERT INTO movimientos (solicitud_id, tipo, responsable_id, estado_equipo, observacion) VALUES (?, 'devolucion', ?, ?, ?)`)
      .run(solicitud.id, req.user.id, estado_equipo || null, observacion || null);

    // RF-09: bloqueo automatico de 1 semana (maximo, segun Anexo 6 #10) si hubo atraso
    if (atrasada) {
      const usuarioBloqueado = solicitud.en_representacion_de || solicitud.solicitante_id;
      const usuario = db.prepare('SELECT * FROM usuarios WHERE id = ?').get(usuarioBloqueado);
      const hasta = new Date();
      hasta.setDate(hasta.getDate() + 7);
      const hastaIso = hasta.toISOString();
      db.prepare(`UPDATE usuarios SET bloqueado_hasta = ? WHERE id = ?`).run(hastaIso, usuarioBloqueado);
      db.prepare(`INSERT INTO bloqueos (usuario_id, seccion, solicitud_id, fecha_fin, motivo) VALUES (?, ?, ?, ?, ?)`)
        .run(usuarioBloqueado, usuario ? usuario.seccion : null, solicitud.id, hastaIso, 'Devolucion atrasada');
    }
  });

  devolver();
  res.json(getSolicitudCompleta(solicitud.id));
});

module.exports = router;
