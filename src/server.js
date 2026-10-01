require('dotenv').config();
const path = require('path');
const express = require('express');
const cors = require('cors');

const app = express();
app.use(cors());
app.use(express.json());

// --- API routes (una por cada bloque de RF, ver comentarios en cada archivo) ---
app.use('/api/auth', require('./routes/auth.routes'));
app.use('/api/equipos', require('./routes/equipment.routes'));
app.use('/api/insumos', require('./routes/supplies.routes'));
app.use('/api/solicitudes', require('./routes/requests.routes'));
app.use('/api/mantenimientos', require('./routes/maintenance.routes'));
app.use('/api/reportes', require('./routes/reports.routes'));
app.use('/api/busqueda', require('./routes/search.routes'));
app.use('/api/migracion', require('./routes/migration.routes'));

app.get('/api/health', (req, res) => res.json({ ok: true, servicio: 'leica-inventario-api' }));

// --- Frontend estatico (RNF: aplicacion web, un solo servidor para el prototipo) ---
app.use(express.static(path.join(__dirname, '..', 'public')));
app.get('*', (req, res, next) => {
  if (req.path.startsWith('/api/')) return next();
  res.sendFile(path.join(__dirname, '..', 'public', 'index.html'));
});

// Manejador de errores centralizado
app.use((err, req, res, next) => {
  console.error(err);
  res.status(500).json({ error: 'Error interno del servidor.' });
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`LEICA Inventario API + frontend corriendo en http://localhost:${PORT}`);
});
