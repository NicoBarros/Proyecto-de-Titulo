// SPA minimalista (sin framework) con ruteo por hash. Cada seccion
// corresponde a uno o varios RF de la Formulacion del Proyecto de Titulo.
const state = { user: null };

const ROLE_LABELS = {
  estudiante: 'Estudiante',
  docente: 'Docente',
  director_carrera: 'Director de Carrera',
  encargado_laboratorio: 'Encargado de Laboratorio',
  control_calidad: 'Control de Calidad',
  comite_ejecutivo: 'Comité Ejecutivo',
};
const APRUEBA = ['docente', 'director_carrera', 'encargado_laboratorio'];
const ESCRIBE_INVENTARIO = ['encargado_laboratorio', 'control_calidad'];

const ROUTES = [
  { path: 'dashboard', label: 'Resumen', render: renderDashboard },
  { path: 'inventario', label: 'Inventario', render: renderInventario },
  { path: 'solicitudes', label: 'Solicitudes', render: renderSolicitudes },
  { path: 'mantenimiento', label: 'Mantenimiento', render: renderMantenimiento },
  { path: 'reportes', label: 'Reportes', render: renderReportes },
  { path: 'busqueda', label: 'Búsqueda IA', render: renderBusqueda },
  { path: 'migracion', label: 'Migración Excel', render: renderMigracion, roles: ESCRIBE_INVENTARIO },
];

function esc(s) { return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
function badge(v) { return `<span class="badge ${esc(v)}">${esc(v)}</span>`; }
function showMsg(container, text, type = 'error') {
  container.insertAdjacentHTML('afterbegin', `<div class="msg ${type}">${esc(text)}</div>`);
}

async function boot() {
  if (Api.token()) {
    try { state.user = (await Api.get('/auth/me')).user; } catch (e) { Api.clearToken(); }
  }
  renderChrome();
  window.addEventListener('hashchange', route);
  route();
}

function renderChrome() {
  const nav = document.getElementById('nav');
  const userbox = document.getElementById('userbox');
  if (!state.user) { nav.innerHTML = ''; userbox.innerHTML = ''; return; }

  nav.innerHTML = ROUTES
    .filter((r) => !r.roles || r.roles.includes(state.user.rol))
    .map((r) => `<button data-path="${r.path}">${r.label}</button>`)
    .join('');
  nav.querySelectorAll('button').forEach((b) => b.onclick = () => { location.hash = '#/' + b.dataset.path; });

  userbox.innerHTML = `${esc(state.user.nombre)} · <strong>${esc(ROLE_LABELS[state.user.rol] || state.user.rol)}</strong> <button id="logout">Salir</button>`;
  document.getElementById('logout').onclick = () => { Api.clearToken(); state.user = null; renderChrome(); location.hash = '#/login'; };
}

function route() {
  const path = (location.hash.replace(/^#\//, '') || (state.user ? 'dashboard' : 'login'));
  if (!state.user && path !== 'login') { location.hash = '#/login'; return; }
  if (state.user && path === 'login') { location.hash = '#/dashboard'; return; }

  document.querySelectorAll('.nav button').forEach((b) => b.classList.toggle('active', b.dataset.path === path));

  const app = document.getElementById('app');
  if (path === 'login') return renderLogin(app);
  const r = ROUTES.find((x) => x.path === path) || ROUTES[0];
  r.render(app);
}

// ---------------------------------------------------------------- LOGIN --
function renderLogin(app) {
  app.innerHTML = `
    <div class="login-wrap card">
      <h2>Ingresar</h2>
      <form id="loginForm">
        <div class="field"><label>Correo institucional</label><input name="email" type="email" placeholder="encargado.leica@inacapmail.cl" required></div>
        <div class="field" style="margin-top:8px"><label>Contraseña</label><input name="password" type="password" required></div>
        <button class="btn" style="margin-top:14px" type="submit">Ingresar</button>
      </form>
      <p class="hint">RF-05: autenticación con correo institucional (@inacapmail.cl).<br>
      Usuarios de ejemplo (ver <code>src/db/seed.js</code>), contraseña <code>Leica2026!</code>:<br>
      encargado.leica@inacapmail.cl · docente1@inacapmail.cl · calidad@inacapmail.cl · dcarrera@inacapmail.cl · estudiante1@inacapmail.cl</p>
    </div>`;
  document.getElementById('loginForm').onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
      const { token, user } = await Api.post('/auth/login', { email: fd.get('email'), password: fd.get('password') });
      Api.setToken(token);
      state.user = user;
      renderChrome();
      location.hash = '#/dashboard';
    } catch (err) { showMsg(app, err.message); }
  };
}

// ------------------------------------------------------------ DASHBOARD --
async function renderDashboard(app) {
  app.innerHTML = '<div class="card">Cargando…</div>';
  try {
    const r = await Api.get('/reportes/resumen');
    app.innerHTML = `
      <div class="card">
        <h2>Resumen general (RF-13)</h2>
        <div class="grid">
          ${stat(r.total_equipos, 'Equipos totales')}
          ${stat(r.equipos_disponibles, 'Disponibles')}
          ${stat(r.equipos_prestados, 'Prestados')}
          ${stat(r.equipos_mantenimiento, 'En mantenimiento')}
          ${stat(r.solicitudes_pendientes, 'Solicitudes pendientes')}
          ${stat(r.solicitudes_atrasadas, 'Atrasadas')}
          ${stat(r.insumos_bajo_stock, 'Insumos bajo stock')}
        </div>
      </div>`;
  } catch (err) { showMsg(app, err.message); }
}
function stat(n, l) { return `<div class="stat"><div class="n">${n ?? 0}</div><div class="l">${esc(l)}</div></div>`; }

// ------------------------------------------------------------ INVENTARIO --
let invTab = 'equipos';
async function renderInventario(app) {
  const puedeEscribir = ESCRIBE_INVENTARIO.includes(state.user.rol);
  app.innerHTML = `
    <div class="card">
      <h2>Inventario (RF-01 a RF-04)</h2>
      <div class="tabs">
        <button data-t="equipos" class="${invTab === 'equipos' ? 'active' : ''}">Equipos activos</button>
        <button data-t="insumos" class="${invTab === 'insumos' ? 'active' : ''}">Insumos</button>
      </div>
      <div id="invBody">Cargando…</div>
    </div>`;
  app.querySelectorAll('.tabs button').forEach((b) => b.onclick = () => { invTab = b.dataset.t; renderInventario(app); });
  const body = document.getElementById('invBody');
  if (invTab === 'equipos') await renderEquipos(body, puedeEscribir); else await renderInsumos(body, puedeEscribir);
}

async function renderEquipos(body, puedeEscribir) {
  const equipos = await Api.get('/equipos');
  body.innerHTML = `
    ${puedeEscribir ? `
    <form class="inline" id="fEquipo">
      <div class="field"><label>Código*</label><input name="codigo_inventario" required></div>
      <div class="field"><label>Nombre*</label><input name="nombre" required></div>
      <div class="field"><label>Modelo</label><input name="modelo"></div>
      <div class="field"><label>Ubicación</label><input name="ubicacion"></div>
      <div class="field"><label>Valor ($)</label><input name="valor_adquisicion" type="number"></div>
      <button class="btn" type="submit">Agregar (RF-01)</button>
    </form>` : ''}
    <table>
      <thead><tr><th>Código</th><th>Nombre</th><th>Modelo</th><th>Ubicación</th><th>Estado</th>${puedeEscribir ? '<th></th>' : ''}</tr></thead>
      <tbody>${equipos.map((e) => `
        <tr>
          <td>${esc(e.codigo_inventario)}</td><td>${esc(e.nombre)}</td><td>${esc(e.modelo)}</td><td>${esc(e.ubicacion)}</td>
          <td>${badge(e.estado)}</td>
          ${puedeEscribir ? `<td><button class="btn chico secundario" data-del="${e.id}">Eliminar</button></td>` : ''}
        </tr>`).join('')}
      </tbody>
    </table>
    <p class="hint">RF-02: cada fila tiene un número de versión interno; dos personas pueden editar equipos distintos a la vez sin bloquear la tabla completa (a diferencia del Excel actual).</p>`;

  if (puedeEscribir) {
    document.getElementById('fEquipo').onsubmit = async (e) => {
      e.preventDefault();
      const fd = Object.fromEntries(new FormData(e.target));
      try { await Api.post('/equipos', fd); renderEquipos(body, puedeEscribir); }
      catch (err) { showMsg(body, err.message); }
    };
    body.querySelectorAll('[data-del]').forEach((b) => b.onclick = async () => {
      if (!confirm('¿Eliminar este equipo?')) return;
      await Api.del('/equipos/' + b.dataset.del); renderEquipos(body, puedeEscribir);
    });
  }
}

async function renderInsumos(body, puedeEscribir) {
  const insumos = await Api.get('/insumos');
  body.innerHTML = `
    ${puedeEscribir ? `
    <form class="inline" id="fInsumo">
      <div class="field"><label>Nombre*</label><input name="nombre" required></div>
      <div class="field"><label>Categoría</label><input name="categoria"></div>
      <div class="field"><label>Tipo</label>
        <select name="tipo"><option value="perecible">Perecible</option><option value="renovable">Renovable</option></select>
      </div>
      <div class="field"><label>Cantidad*</label><input name="cantidad_total" type="number" required></div>
      <div class="field"><label>Umbral mínimo</label><input name="umbral_minimo" type="number" value="0"></div>
      <button class="btn" type="submit">Agregar (RF-03)</button>
    </form>` : ''}
    <table>
      <thead><tr><th>Nombre</th><th>Categoría</th><th>Tipo</th><th>Disponible / Total</th>${puedeEscribir ? '<th></th>' : ''}</tr></thead>
      <tbody>${insumos.map((i) => `
        <tr>
          <td>${esc(i.nombre)}</td><td>${esc(i.categoria)}</td><td>${esc(i.tipo)}</td>
          <td class="${i.cantidad_disponible <= i.umbral_minimo ? 'badge en_mantenimiento' : ''}">${i.cantidad_disponible} / ${i.cantidad_total}</td>
          ${puedeEscribir ? `<td><button class="btn chico secundario" data-del="${i.id}">Eliminar</button></td>` : ''}
        </tr>`).join('')}
      </tbody>
    </table>`;
  if (puedeEscribir) {
    document.getElementById('fInsumo').onsubmit = async (e) => {
      e.preventDefault();
      const fd = Object.fromEntries(new FormData(e.target));
      try { await Api.post('/insumos', fd); renderInsumos(body, puedeEscribir); }
      catch (err) { showMsg(body, err.message); }
    };
    body.querySelectorAll('[data-del]').forEach((b) => b.onclick = async () => {
      if (!confirm('¿Eliminar este insumo?')) return;
      await Api.del('/insumos/' + b.dataset.del); renderInsumos(body, puedeEscribir);
    });
  }
}

// --------------------------------------------------------- SOLICITUDES --
async function renderSolicitudes(app) {
  const [equipos, insumos, solicitudes] = await Promise.all([
    Api.get('/equipos?estado=disponible'), Api.get('/insumos'), Api.get('/solicitudes'),
  ]);
  const puedeAprobar = APRUEBA.includes(state.user.rol);

  app.innerHTML = `
    <div class="card">
      <h2>Nueva solicitud (RF-06, RF-07)</h2>
      <form id="fSolicitud">
        <div class="inline">
          <div class="field"><label>Ítem</label>
            <select name="item">
              <optgroup label="Equipos disponibles">
                ${equipos.map((e) => `<option value="equipo:${e.id}">${esc(e.nombre)} (${esc(e.codigo_inventario)})</option>`).join('')}
              </optgroup>
              <optgroup label="Insumos">
                ${insumos.map((i) => `<option value="insumo:${i.id}">${esc(i.nombre)} — disp. ${i.cantidad_disponible}</option>`).join('')}
              </optgroup>
            </select>
          </div>
          <div class="field"><label>Cantidad</label><input name="cantidad" type="number" value="1" min="1"></div>
          <div class="field"><label>Lugar de uso</label>
            <select name="lugar_uso"><option value="dentro_sede">Dentro de sede</option><option value="fuera_sede">Fuera de sede</option></select>
          </div>
          <div class="field"><label>Inicio</label><input name="horario_inicio" type="datetime-local" required></div>
          <div class="field"><label>Fin</label><input name="horario_fin" type="datetime-local" required></div>
          <div class="field"><label>Justificación</label><input name="justificacion" placeholder="ej. clase práctica"></div>
          <button class="btn" type="submit">Solicitar</button>
        </div>
      </form>
      <p class="hint">Nota del prototipo: un ítem por solicitud para simplificar el formulario; el modelo de datos (solicitud_items) ya admite varios ítems o "kits" por solicitud (hallazgo entrevista, Anexo 6 #11).</p>
    </div>
    <div class="card">
      <h2>Solicitudes</h2>
      <table>
        <thead><tr><th>#</th><th>Ítems</th><th>Horario</th><th>Lugar</th><th>Estado</th><th></th></tr></thead>
        <tbody>${solicitudes.map((s) => `
          <tr>
            <td>${s.id}</td>
            <td>${s.items.map((it) => esc(it.equipo_nombre || it.insumo_nombre)).join(', ')}</td>
            <td>${fmtRango(s.horario_inicio, s.horario_fin)}</td>
            <td>${esc(s.lugar_uso)}</td>
            <td>${badge(s.estado)}</td>
            <td>${accionesSolicitud(s, puedeAprobar)}</td>
          </tr>`).join('')}
        </tbody>
      </table>
    </div>`;

  document.getElementById('fSolicitud').onsubmit = async (e) => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    const [tipo, id] = fd.item.split(':');
    const item = tipo === 'equipo' ? { equipo_id: Number(id), cantidad: 1 } : { insumo_id: Number(id), cantidad: Number(fd.cantidad) || 1 };
    try {
      await Api.post('/solicitudes', {
        lugar_uso: fd.lugar_uso, justificacion: fd.justificacion,
        horario_inicio: fd.horario_inicio, horario_fin: fd.horario_fin, items: [item],
      });
      renderSolicitudes(app);
    } catch (err) { showMsg(app, err.message); }
  };

  app.querySelectorAll('[data-accion]').forEach((b) => b.onclick = async () => {
    try {
      let body = {};
      if (b.dataset.accion === 'devolver') {
        const estado_equipo = prompt('Estado del equipo al devolver (excelente/bueno/dañado/inservible):', 'bueno') || 'bueno';
        body = { estado_equipo };
      }
      await Api.post(`/solicitudes/${b.dataset.id}/${b.dataset.accion}`, body);
      renderSolicitudes(app);
    } catch (err) { showMsg(app, err.message); }
  });
}
function fmtRango(a, b) { const f = (x) => new Date(x).toLocaleString('es-CL', { dateStyle: 'short', timeStyle: 'short' }); return `${f(a)} → ${f(b)}`; }
function accionesSolicitud(s, puedeAprobar) {
  if (!puedeAprobar) return '';
  if (s.estado === 'pendiente') return btnAccion(s.id, 'aprobar', 'Aprobar') + btnAccion(s.id, 'rechazar', 'Rechazar', 'secundario');
  if (s.estado === 'aprobada') return btnAccion(s.id, 'entregar', 'Entregar');
  if (s.estado === 'entregada') return btnAccion(s.id, 'devolver', 'Registrar devolución');
  return '';
}
function btnAccion(id, accion, label, cls = '') { return `<button class="btn chico ${cls}" data-accion="${accion}" data-id="${id}">${label}</button>`; }

// ------------------------------------------------------------- MANTENIMIENTO --
async function renderMantenimiento(app) {
  const puedeEscribir = ESCRIBE_INVENTARIO.includes(state.user.rol);
  const [equipos, registros] = await Promise.all([Api.get('/equipos'), Api.get('/mantenimientos')]);
  app.innerHTML = `
    <div class="card">
      <h2>Mantenimiento (RF-10 — regla del 70%)</h2>
      ${puedeEscribir ? `
      <form class="inline" id="fMant">
        <div class="field"><label>Equipo</label>
          <select name="equipo_id">${equipos.map((e) => `<option value="${e.id}">${esc(e.nombre)} (${esc(e.codigo_inventario)})</option>`).join('')}</select>
        </div>
        <div class="field"><label>Falla</label><input name="falla_descrita" required></div>
        <div class="field"><label>Costo cotizado ($)</label><input name="costo_cotizado" type="number" required></div>
        <button class="btn" type="submit">Diagnosticar</button>
      </form>` : ''}
      <table>
        <thead><tr><th>Equipo</th><th>Falla</th><th>Costo</th><th>% del valor</th><th>Decisión</th>${puedeEscribir ? '<th></th>' : ''}</tr></thead>
        <tbody>${registros.map((m) => `
          <tr>
            <td>${esc(m.equipo_nombre)}</td><td>${esc(m.falla_descrita)}</td>
            <td>${m.costo_cotizado ?? '-'}</td>
            <td>${m.porcentaje_costo != null ? (m.porcentaje_costo * 100).toFixed(1) + '%' : '-'}</td>
            <td>${badge(m.decision)}</td>
            ${puedeEscribir && m.decision === 'pendiente' ? `<td>
              <button class="btn chico" data-res="reparar" data-id="${m.id}">Confirmar reparar</button>
              <button class="btn chico secundario" data-res="dar_baja" data-id="${m.id}">Confirmar baja</button>
            </td>` : (puedeEscribir ? '<td></td>' : '')}
          </tr>`).join('')}
        </tbody>
      </table>
    </div>`;
  if (puedeEscribir) {
    document.getElementById('fMant').onsubmit = async (e) => {
      e.preventDefault();
      const fd = Object.fromEntries(new FormData(e.target));
      try {
        const r = await Api.post('/mantenimientos', fd);
        alert(r.sugerencia_explicacion);
        renderMantenimiento(app);
      } catch (err) { showMsg(app, err.message); }
    };
    app.querySelectorAll('[data-res]').forEach((b) => b.onclick = async () => {
      await Api.post(`/mantenimientos/${b.dataset.id}/resolver`, { decision: b.dataset.res });
      renderMantenimiento(app);
    });
  }
}

// ------------------------------------------------------------- REPORTES --
async function renderReportes(app) {
  const [top, vencidos, sinMov] = await Promise.all([
    Api.get('/reportes/equipos-mas-solicitados'),
    Api.get('/reportes/prestamos-vencidos'),
    Api.get('/reportes/equipos-sin-movimiento?dias=90'),
  ]);
  app.innerHTML = `
    <div class="card"><h2>Equipos más solicitados (RF-13)</h2>
      <table><thead><tr><th>Equipo</th><th>Veces solicitado</th></tr></thead>
      <tbody>${top.map((t) => `<tr><td>${esc(t.nombre)}</td><td>${t.veces_solicitado}</td></tr>`).join('') || '<tr><td colspan=2>Sin datos aún.</td></tr>'}</tbody></table>
    </div>
    <div class="card"><h2>Préstamos vencidos</h2>
      <table><thead><tr><th>Solicitante</th><th>Vence</th></tr></thead>
      <tbody>${vencidos.map((v) => `<tr><td>${esc(v.solicitante_nombre)}</td><td>${fmtRango(v.horario_inicio, v.horario_fin)}</td></tr>`).join('') || '<tr><td colspan=2>Ninguno.</td></tr>'}</tbody></table>
    </div>
    <div class="card"><h2>Equipos sin movimiento (90 días)</h2>
      <table><thead><tr><th>Equipo</th><th>Código</th><th>Estado</th></tr></thead>
      <tbody>${sinMov.map((e) => `<tr><td>${esc(e.nombre)}</td><td>${esc(e.codigo_inventario)}</td><td>${badge(e.estado)}</td></tr>`).join('') || '<tr><td colspan=3>Todos los equipos tienen movimiento reciente.</td></tr>'}</tbody></table>
    </div>`;
}

// ------------------------------------------------------------- BÚSQUEDA IA --
async function renderBusqueda(app) {
  app.innerHTML = `
    <div class="card">
      <h2>Búsqueda inteligente (RF-11 / RNF-06)</h2>
      <form id="fBusqueda" class="inline">
        <div class="field" style="flex:1"><label>Describe lo que necesitas</label>
          <input name="consulta" style="width:100%" placeholder="ej: necesito algo para armar una red con 3 routers para la clase de mañana" required></div>
        <button class="btn" type="submit">Buscar</button>
      </form>
      <div id="resBusqueda"></div>
      <p class="hint">Delega la interpretación de lenguaje natural a una API externa (Claude) cuando ANTHROPIC_API_KEY está configurada en <code>.env</code>; si no, usa un respaldo por palabras clave para que el prototipo funcione igual.</p>
    </div>`;
  document.getElementById('fBusqueda').onsubmit = async (e) => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    const res = document.getElementById('resBusqueda');
    res.innerHTML = 'Buscando…';
    try {
      const { fuente, resultados } = await Api.post('/busqueda', fd);
      res.innerHTML = `<p class="hint">Fuente: ${esc(fuente)}</p>` + (resultados.length
        ? `<table><thead><tr><th>Equipo</th><th>Código</th><th>Estado</th></tr></thead><tbody>
            ${resultados.map((r) => `<tr><td>${esc(r.nombre)}</td><td>${esc(r.codigo_inventario)}</td><td>${badge(r.estado)}</td></tr>`).join('')}
           </tbody></table>`
        : '<p>No se encontraron equipos relevantes disponibles.</p>');
    } catch (err) { showMsg(res, err.message); }
  };
}

// ------------------------------------------------------------- MIGRACIÓN --
async function renderMigracion(app) {
  app.innerHTML = `
    <div class="card">
      <h2>Migración desde Excel/SharePoint (RF-14)</h2>
      <p>Exporta la planilla actual a CSV (Excel → Archivo → Guardar como → CSV) con columnas:
      <code>tipo,codigo_inventario,nombre,modelo,especificaciones,ubicacion,estado,valor_adquisicion,categoria,tipo_insumo,cantidad</code>
      (<code>tipo</code> = <code>equipo</code> o <code>insumo</code>).</p>
      <form id="fMigra" class="inline">
        <input type="file" name="archivo" accept=".csv" required>
        <button class="btn" type="submit">Importar</button>
      </form>
      <div id="resMigra"></div>
    </div>`;
  document.getElementById('fMigra').onsubmit = async (e) => {
    e.preventDefault();
    const file = e.target.archivo.files[0];
    const fd = new FormData(); fd.append('archivo', file);
    const res = document.getElementById('resMigra');
    try {
      const r = await Api.postForm('/migracion', fd);
      res.innerHTML = `<div class="msg ok">Importadas ${r.filas_importadas}/${r.filas_totales} filas. Errores: ${r.filas_con_error}.</div>
        ${r.errores.length ? `<ul>${r.errores.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}`;
    } catch (err) { showMsg(res, err.message); }
  };
}

boot();
