(function () {
  const formulario = document.getElementById('fBusqueda');
  const resultado = document.getElementById('resBusqueda');

  function el(tag, texto, clase) {
    const n = document.createElement(tag);
    if (texto !== undefined) n.textContent = texto;
    if (clase) n.className = clase;
    return n;
  }

  function icono(clase) {
    const i = el('i', undefined, clase);
    i.setAttribute('aria-hidden', 'true');
    return i;
  }

  function mostrarCargando() {
    const cargando = el('div', undefined, 'd-flex align-items-center gap-2 text-primary');
    const spinner = el('div', undefined, 'spinner-border spinner-border-sm');
    spinner.setAttribute('role', 'status');
    cargando.append(spinner, document.createTextNode(' Buscando con Inteligencia Artificial...'));
    resultado.replaceChildren(cargando);
  }

  function mostrarTabla(resultados) {
    const wrapper = el('div', undefined, 'table-responsive');
    const tabla = el('table', undefined, 'table table-hover align-middle');
    const encabezado = el('tr');
    ['Equipo', 'Código', 'Estado'].forEach((t) => encabezado.append(el('th', t)));
    const thead = el('thead');
    thead.append(encabezado);
    const tbody = el('tbody');
    resultados.forEach((r) => {
      const tr = el('tr');
      const tdNombre = el('td');
      const enlace = el('a', r.nombre, 'link-equipo');
      enlace.href = r.url;
      tdNombre.append(enlace);
      const tdEstado = el('td');
      tdEstado.append(el('span', r.estado, 'badge ' + r.estado.toLowerCase().replace(/ /g, '_')));
      tr.append(tdNombre, el('td', r.codigo_inventario), tdEstado);
      tbody.append(tr);
    });
    tabla.append(thead, tbody);
    wrapper.append(tabla);
    resultado.append(wrapper);
  }

  function mostrarVacio() {
    const vacio = el('div', undefined, 'text-center text-muted py-4');
    vacio.append(icono('bi bi-search fs-3 d-block mb-2'), document.createTextNode('No se encontraron equipos relevantes disponibles.'));
    resultado.append(vacio);
  }

  function mostrarError(mensaje) {
    const alerta = el('div', undefined, 'alert alert-danger border-0');
    alerta.append(icono('bi bi-exclamation-triangle-fill me-2'), document.createTextNode(mensaje));
    resultado.replaceChildren(alerta);
  }

  formulario.addEventListener('submit', async (e) => {
    e.preventDefault();
    mostrarCargando();
    try {
      const resp = await fetch(formulario.action, {
        method: 'POST',
        headers: { 'X-CSRFToken': formulario.querySelector('[name=csrfmiddlewaretoken]').value },
        body: new FormData(formulario),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || 'Error en la búsqueda');

      resultado.replaceChildren(el('p', `Fuente: ${data.fuente}`, 'hint mb-3'));
      if (data.resultados.length > 0) {
        mostrarTabla(data.resultados);
      } else {
        mostrarVacio();
      }
    } catch (err) {
      mostrarError(err.message);
    }
  });
})();
