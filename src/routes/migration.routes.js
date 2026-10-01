// RF-14: permitir migrar los equipos e insumos existentes desde la
//        planilla Excel/SharePoint, conservando sus atributos originales.
//
// Se recibe un CSV (exportado desde Excel: Archivo > Guardar como > CSV)
// con columnas: tipo,codigo_inventario,nombre,modelo,especificaciones,
// ubicacion,estado,valor_adquisicion,categoria,tipo_insumo,cantidad
const express = require('express');
const multer = require('multer');
const { parse } = require('csv-parse/sync');
const db = require('../db/db');
const { requireAuth, requireRole, ROLES_ESCRITURA_INVENTARIO } = require('../middleware/auth');

const router = express.Router();
const upload = multer({ storage: multer.memoryStorage() });
router.use(requireAuth);

router.post('/', requireRole(...ROLES_ESCRITURA_INVENTARIO), upload.single('archivo'), (req, res) => {
  if (!req.file) return res.status(400).json({ error: 'Falta el archivo CSV (campo "archivo").' });

  let filas;
  try {
    filas = parse(req.file.buffer.toString('utf8'), { columns: true, skip_empty_lines: true, trim: true });
  } catch (err) {
    return res.status(400).json({ error: 'No se pudo leer el CSV: ' + err.message });
  }

  const insertEquipo = db.prepare(`
    INSERT OR IGNORE INTO equipos (codigo_inventario, nombre, modelo, especificaciones, ubicacion, estado, valor_adquisicion)
    VALUES (?, ?, ?, ?, ?, COALESCE(?, 'disponible'), ?)
  `);
  const insertInsumo = db.prepare(`
    INSERT INTO insumos (nombre, categoria, tipo, cantidad_total, cantidad_disponible)
    VALUES (?, ?, COALESCE(?, 'perecible'), ?, ?)
  `);

  let importadas = 0;
  const errores = [];

  const correr = db.transaction(() => {
    filas.forEach((fila, idx) => {
      try {
        if ((fila.tipo || '').toLowerCase() === 'equipo') {
          if (!fila.codigo_inventario || !fila.nombre) throw new Error('faltan codigo_inventario/nombre');
          insertEquipo.run(fila.codigo_inventario, fila.nombre, fila.modelo || null, fila.especificaciones || null, fila.ubicacion || null, fila.estado || null, Number(fila.valor_adquisicion) || null);
        } else if ((fila.tipo || '').toLowerCase() === 'insumo') {
          if (!fila.nombre) throw new Error('falta nombre');
          const cant = Number(fila.cantidad) || 0;
          insertInsumo.run(fila.nombre, fila.categoria || null, fila.tipo_insumo || null, cant, cant);
        } else {
          throw new Error(`columna "tipo" debe ser 'equipo' o 'insumo' (fila ${idx + 2})`);
        }
        importadas++;
      } catch (err) {
        errores.push(`Fila ${idx + 2}: ${err.message}`);
      }
    });
  });
  correr();

  const info = db.prepare(`
    INSERT INTO migraciones (archivo_origen, filas_totales, filas_importadas, filas_con_error, detalle_errores, ejecutado_por)
    VALUES (?, ?, ?, ?, ?, ?)
  `).run(req.file.originalname, filas.length, importadas, errores.length, JSON.stringify(errores), req.user.id);

  res.json({
    migracion_id: info.lastInsertRowid,
    filas_totales: filas.length,
    filas_importadas: importadas,
    filas_con_error: errores.length,
    errores,
  });
});

router.get('/', requireRole(...ROLES_ESCRITURA_INVENTARIO), (req, res) => {
  res.json(db.prepare('SELECT * FROM migraciones ORDER BY fecha DESC').all());
});

module.exports = router;
