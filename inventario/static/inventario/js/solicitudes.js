(function () {
  const inicio = document.getElementById('horarioInicio');
  const fin = document.getElementById('horarioFin');
  const contenedor = document.getElementById('items-container');

  const ahora = new Date();
  ahora.setMinutes(ahora.getMinutes() - ahora.getTimezoneOffset());
  inicio.min = ahora.toISOString().slice(0, 16);
  inicio.addEventListener('change', () => {
    fin.min = inicio.value;
    if (fin.value && fin.value <= inicio.value) fin.value = '';
  });

  function actualizarTopeStock(selectEl) {
    const row = selectEl.closest('.item-row');
    if (!row) return;
    const inputCantidad = row.querySelector('.cantidad-input');
    const stockHint = row.querySelector('.stock-hint');
    const selectedOpt = selectEl.options[selectEl.selectedIndex];
    if (!selectedOpt) return;

    const tipo = selectedOpt.dataset.tipo;
    const stock = parseInt(selectedOpt.dataset.stock) || 1;

    if (tipo === 'equipo') {
      inputCantidad.min = 1;
      inputCantidad.max = 1;
      inputCantidad.value = 1;
      inputCantidad.readOnly = true;
      if (stockHint) stockHint.innerText = 'máx. 1';
    } else {
      inputCantidad.readOnly = false;
      inputCantidad.min = 1;
      inputCantidad.max = stock;
      if (stockHint) stockHint.innerText = `máx. ${stock}`;

      const currentVal = parseInt(inputCantidad.value) || 1;
      if (currentVal > stock) {
        inputCantidad.value = stock;
      } else if (currentVal < 1) {
        inputCantidad.value = 1;
      }
    }
  }

  function validarCantidadInput(inputEl) {
    const max = parseInt(inputEl.max);
    const min = parseInt(inputEl.min) || 1;
    const val = parseInt(inputEl.value);

    if (max && val > max) {
      inputEl.value = max;
      inputEl.classList.add('is-invalid');
      setTimeout(() => { inputEl.classList.remove('is-invalid'); }, 800);
    } else if (val < min && inputEl.value !== '') {
      inputEl.value = min;
    }
  }

  function actualizarContador() {
    document.getElementById('items-contador').innerText = contenedor.querySelectorAll('.item-row').length;
  }

  function selectores() {
    return [...contenedor.querySelectorAll('.item-select')];
  }

  function itemsElegidos() {
    return new Set(selectores().map((sel) => sel.value));
  }

  function sincronizarOpciones() {
    const elegidos = itemsElegidos();
    selectores().forEach((sel) => {
      [...sel.options].forEach((opt) => {
        opt.disabled = opt.dataset.agotado === '1' || (opt.value !== sel.value && elegidos.has(opt.value));
      });
    });
  }

  function agregarItem() {
    const elegidos = itemsElegidos();
    const plantilla = contenedor.querySelector('.item-row');
    const libre = [...plantilla.querySelector('.item-select').options]
      .find((opt) => opt.dataset.agotado !== '1' && !elegidos.has(opt.value));
    if (!libre) {
      window.mostrarAlerta('Ya agregaste todos los ítems disponibles.', 'Sin más ítems');
      return;
    }
    const newRow = plantilla.cloneNode(true);
    const select = newRow.querySelector('.item-select');
    newRow.querySelector('.cantidad-input').value = 1;
    contenedor.appendChild(newRow);
    select.value = libre.value;
    actualizarTopeStock(select);
    sincronizarOpciones();
    actualizarContador();
    contenedor.scrollTop = contenedor.scrollHeight;
    select.focus();
  }

  function removerItem(btn) {
    if (contenedor.querySelectorAll('.item-row').length > 1) {
      btn.closest('.item-row').remove();
      sincronizarOpciones();
      actualizarContador();
    } else {
      window.mostrarAlerta('La solicitud debe tener al menos un ítem.', 'Ítem Requerido');
    }
  }

  contenedor.addEventListener('change', (e) => {
    if (!e.target.matches('.item-select')) return;
    actualizarTopeStock(e.target);
    sincronizarOpciones();
  });
  contenedor.addEventListener('input', (e) => {
    if (e.target.matches('.cantidad-input')) validarCantidadInput(e.target);
  });
  document.addEventListener('click', (e) => {
    const boton = e.target.closest('[data-accion]');
    if (!boton) return;
    if (boton.dataset.accion === 'agregar-item') agregarItem();
    if (boton.dataset.accion === 'quitar-item') removerItem(boton);
  });

  selectores().forEach(actualizarTopeStock);
  sincronizarOpciones();
})();
