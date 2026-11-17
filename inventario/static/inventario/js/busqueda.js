(function () {
  const formulario = document.getElementById('fBusqueda');
  const resultado = document.getElementById('resBusqueda');
  const FUENTES = {
    hibrida_local: 'Recuperación híbrida',
    semantica_local: 'Búsqueda semántica',
    ia_gemini: 'Gemini',
    palabras_clave_local: 'Palabras clave',
  };

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
    cargando.append(spinner, document.createTextNode(' Buscando...'));
    resultado.replaceChildren(cargando);
  }

  function mostrarTabla(resultados) {
    const wrapper = el('div', undefined, 'table-responsive');
    const tabla = el('table', undefined, 'table table-hover align-middle');
    const encabezado = el('tr');
    ['#', 'Equipo', 'Modelo', 'Disponibles'].forEach((t) => encabezado.append(el('th', t)));
    const thead = el('thead');
    thead.append(encabezado);
    const tbody = el('tbody');
    resultados.forEach((r, i) => {
      const tr = el('tr');
      tr.append(el('td', String(i + 1), 'text-muted small'));
      const tdNombre = el('td');
      const enlace = el('a', r.nombre, 'link-equipo');
      enlace.href = r.url;
      tdNombre.append(enlace);
      const tdDisponibles = el('td');
      tdDisponibles.append(el('span', String(r.disponibles), 'badge disponible'));
      tr.append(tdNombre, el('td', r.modelo || '—', 'text-muted'), tdDisponibles);
      tbody.append(tr);
    });
    tabla.append(thead, tbody);
    wrapper.append(tabla);
    resultado.append(wrapper);
  }

  function cajaRespuesta() {
    const caja = el('div', undefined, 'rag-respuesta mb-3');
    caja.append(icono('bi bi-stars rag-icono'));
    const cargando = el('p', undefined, 'mb-0 d-flex align-items-center gap-2 text-muted');
    const spinner = el('span', undefined, 'spinner-border spinner-border-sm');
    spinner.setAttribute('role', 'status');
    cargando.append(spinner, document.createTextNode('Generando respuesta...'));
    caja.append(cargando);
    return caja;
  }

  async function cargarRespuesta(url, caja, resultados) {
    try {
      const resp = await fetch(url, {
        method: 'POST',
        headers: { 'X-CSRFToken': formulario.querySelector('[name=csrfmiddlewaretoken]').value },
      });
      const data = await resp.json();
      if (!resp.ok || !data.respuesta) throw new Error();
      caja.lastChild.replaceWith(parrafoRespuesta(data.respuesta, resultados));
    } catch (err) {
      caja.remove();
    }
  }

  function parrafoRespuesta(texto, resultados) {
    const parrafo = el('p', undefined, 'mb-0');
    let ultimo = 0;
    texto.replace(/\[E(\d+)\]/g, (cita, numero, posicion) => {
      parrafo.append(document.createTextNode(texto.slice(ultimo, posicion)));
      const item = resultados[Number(numero) - 1];
      if (item) {
        const enlace = el('a', numero, 'rag-cita');
        enlace.href = item.url;
        enlace.title = item.nombre;
        parrafo.append(enlace);
      }
      ultimo = posicion + cita.length;
      return cita;
    });
    parrafo.append(document.createTextNode(texto.slice(ultimo)));
    return parrafo;
  }

  function mostrarCalificacion(url) {
    const barra = el('div', undefined, 'rag-calificacion d-flex align-items-center gap-2 mt-2');
    barra.append(el('span', '¿Te sirvió esta búsqueda?', 'small text-muted'));
    const token = formulario.querySelector('[name=csrfmiddlewaretoken]').value;
    const botones = [['1', 'bi-hand-thumbs-up', 'Sí'], ['0', 'bi-hand-thumbs-down', 'No']].map(([valor, clase, etiqueta]) => {
      const boton = el('button', undefined, 'btn btn-sm btn-outline-secondary');
      boton.type = 'button';
      boton.dataset.util = valor;
      boton.setAttribute('aria-label', etiqueta);
      boton.append(icono(`bi ${clase}`));
      boton.addEventListener('click', async () => {
        const datos = new FormData();
        datos.append('util', valor);
        botones.forEach((b) => { b.disabled = true; });
        try {
          const resp = await fetch(url, { method: 'POST', headers: { 'X-CSRFToken': token }, body: datos });
          if (!resp.ok) throw new Error();
          boton.classList.replace('btn-outline-secondary', valor === '1' ? 'btn-success' : 'btn-danger');
        } catch (err) {
          botones.forEach((b) => { b.disabled = false; });
        }
      });
      return boton;
    });
    barra.append(...botones);
    resultado.append(barra);
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

      resultado.replaceChildren(el('p', `Fuente: ${FUENTES[data.fuente] || data.fuente}`, 'hint mb-3'));
      if (data.generar) {
        const caja = cajaRespuesta();
        resultado.append(caja);
        cargarRespuesta(data.generar, caja, data.resultados);
      }
      if (data.resultados.length > 0) {
        mostrarTabla(data.resultados);
      } else {
        mostrarVacio();
      }
      mostrarCalificacion(data.calificar);
    } catch (err) {
      mostrarError(err.message);
    }
  });
})();
