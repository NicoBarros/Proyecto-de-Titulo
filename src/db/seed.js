// Carga datos de ejemplo: un usuario por rol (RF-04/RF-05) y algunos
// equipos/insumos para poder probar el resto de los endpoints de inmediato.
// Ejecutar con: npm run seed

const bcrypt = require('bcryptjs');
const db = require('./db');

const PASSWORD = 'Leica2026!'; // password de ejemplo para TODOS los usuarios semilla

const usuarios = [
  { email: 'vicerrector@inacapmail.cl', nombre: 'Vicerrector Sede Valdivia', rol: 'comite_ejecutivo' },
  { email: 'dcarrera@inacapmail.cl', nombre: 'Directora de Carrera', rol: 'director_carrera' },
  { email: 'calidad@inacapmail.cl', nombre: 'Daniela Quezada (Control de Calidad)', rol: 'control_calidad' },
  { email: 'encargado.leica@inacapmail.cl', nombre: 'Juan Gomez (Encargado LEICA)', rol: 'encargado_laboratorio' },
  { email: 'docente1@inacapmail.cl', nombre: 'Docente Redes', rol: 'docente' },
  { email: 'estudiante1@inacapmail.cl', nombre: 'Estudiante Ejemplo', rol: 'estudiante', seccion: 'INF-301N' },
];

const insertUsuario = db.prepare(`
  INSERT OR IGNORE INTO usuarios (email, nombre, password_hash, rol, seccion)
  VALUES (@email, @nombre, @password_hash, @rol, @seccion)
`);

const hash = bcrypt.hashSync(PASSWORD, 10);
const insertMany = db.transaction((rows) => {
  for (const u of rows) {
    insertUsuario.run({ ...u, password_hash: hash, seccion: u.seccion || null });
  }
});
insertMany(usuarios);

const equipos = [
  { codigo_inventario: 'LEICA-RT-001', nombre: 'Router Cisco ISR 4321', modelo: 'ISR4321', especificaciones: '2 WAN, 2 LAN', ubicacion: 'Rack A1', valor_adquisicion: 650000 },
  { codigo_inventario: 'LEICA-SW-014', nombre: 'Switch Cisco Catalyst 2960', modelo: 'WS-C2960', especificaciones: '24 puertos', ubicacion: 'Rack A2', valor_adquisicion: 420000 },
  { codigo_inventario: 'LEICA-AP-007', nombre: 'Access Point Cisco Aironet', modelo: 'AIR-AP1852', especificaciones: '802.11ac', ubicacion: 'Bodega', valor_adquisicion: 310000 },
];
const insertEquipo = db.prepare(`
  INSERT OR IGNORE INTO equipos (codigo_inventario, nombre, modelo, especificaciones, ubicacion, valor_adquisicion)
  VALUES (@codigo_inventario, @nombre, @modelo, @especificaciones, @ubicacion, @valor_adquisicion)
`);
db.transaction((rows) => { for (const e of rows) insertEquipo.run(e); })(equipos);

const insumos = [
  { nombre: 'Cable UTP cat 6 (metros)', categoria: 'Cableado', tipo: 'perecible', cantidad_total: 500, cantidad_disponible: 500, umbral_minimo: 50 },
  { nombre: 'Conector RJ45', categoria: 'Cableado', tipo: 'renovable', cantidad_total: 300, cantidad_disponible: 300, umbral_minimo: 30 },
  { nombre: 'Kit Arduino Uno + sensores', categoria: 'Electronica', tipo: 'renovable', cantidad_total: 20, cantidad_disponible: 20, umbral_minimo: 5 },
];
const insertInsumo = db.prepare(`
  INSERT OR IGNORE INTO insumos (nombre, categoria, tipo, cantidad_total, cantidad_disponible, umbral_minimo)
  VALUES (@nombre, @categoria, @tipo, @cantidad_total, @cantidad_disponible, @umbral_minimo)
`);
db.transaction((rows) => { for (const i of rows) insertInsumo.run(i); })(insumos);

console.log('Seed completo. Password de todos los usuarios de ejemplo:', PASSWORD);
console.log('Usuarios creados:', usuarios.map((u) => `${u.email} (${u.rol})`).join('\n  '));
