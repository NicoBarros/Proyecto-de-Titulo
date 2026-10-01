// RF-05: El sistema debe permitir la autenticacion de docentes y personal de
// LEICA mediante correo institucional, rechazando credenciales no validas.
const express = require('express');
const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const db = require('../db/db');
const { JWT_SECRET, requireAuth } = require('../middleware/auth');

const router = express.Router();

// Dominio institucional aceptado. En produccion esto deberia validarse contra
// el directorio/correo institucional real de INACAP (ver Anexo 5, entrevista,
// seccion "Login institucional"): aqui se deja como variable de entorno para
// no hardcodear un dominio real.
const DOMINIO_INSTITUCIONAL = process.env.DOMINIO_INSTITUCIONAL || 'inacapmail.cl';

router.post('/login', (req, res) => {
  const { email, password } = req.body;
  if (!email || !password) {
    return res.status(400).json({ error: 'Email y password son obligatorios.' });
  }
  if (!email.endsWith('@' + DOMINIO_INSTITUCIONAL)) {
    return res.status(401).json({ error: 'Debe autenticarse con su correo institucional.' });
  }

  const user = db.prepare('SELECT * FROM usuarios WHERE email = ? AND activo = 1').get(email);
  if (!user) return res.status(401).json({ error: 'Credenciales no validas.' });

  // RF-09: cuenta bloqueada por atraso en una devolucion
  if (user.bloqueado_hasta && new Date(user.bloqueado_hasta) > new Date()) {
    return res.status(403).json({
      error: `Cuenta bloqueada hasta ${user.bloqueado_hasta} por atraso en una devolucion.`,
    });
  }

  const ok = bcrypt.compareSync(password, user.password_hash);
  if (!ok) return res.status(401).json({ error: 'Credenciales no validas.' });

  const token = jwt.sign(
    { id: user.id, email: user.email, nombre: user.nombre, rol: user.rol, seccion: user.seccion },
    JWT_SECRET,
    { expiresIn: '8h' }
  );
  res.json({ token, user: { id: user.id, email: user.email, nombre: user.nombre, rol: user.rol, seccion: user.seccion } });
});

router.get('/me', requireAuth, (req, res) => {
  res.json({ user: req.user });
});

module.exports = router;
