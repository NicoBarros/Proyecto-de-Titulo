// RF-05: autenticacion mediante correo institucional (valida credenciales).
// RF-04: define roles de acceso de lectura y escritura.
const jwt = require('jsonwebtoken');

const JWT_SECRET = process.env.JWT_SECRET || 'dev-secret-change-me';

function requireAuth(req, res, next) {
  const header = req.headers.authorization || '';
  const token = header.startsWith('Bearer ') ? header.slice(7) : null;
  if (!token) return res.status(401).json({ error: 'No autenticado. Falta el token.' });
  try {
    req.user = jwt.verify(token, JWT_SECRET);
    next();
  } catch (err) {
    return res.status(401).json({ error: 'Token invalido o expirado.' });
  }
}

// RF-04: roles con permiso de escritura sobre el inventario
const ROLES_ESCRITURA_INVENTARIO = ['encargado_laboratorio', 'control_calidad'];

// Roles que pueden autorizar una solicitud (RF-06)
const ROLES_APROBADORES = ['docente', 'director_carrera', 'encargado_laboratorio'];

function requireRole(...rolesPermitidos) {
  return (req, res, next) => {
    if (!req.user) return res.status(401).json({ error: 'No autenticado.' });
    if (!rolesPermitidos.includes(req.user.rol)) {
      return res.status(403).json({
        error: `Rol '${req.user.rol}' no tiene permiso para esta accion. Roles permitidos: ${rolesPermitidos.join(', ')}`,
      });
    }
    next();
  };
}

module.exports = { requireAuth, requireRole, JWT_SECRET, ROLES_ESCRITURA_INVENTARIO, ROLES_APROBADORES };
