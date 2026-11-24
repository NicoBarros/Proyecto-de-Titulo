(function () {
  function normalizar(texto) {
    return texto.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  }

  function filtrar(entrada) {
    const select = entrada.closest('.filtro-grupo').querySelector('select');
    const terminos = normalizar(entrada.value).split(/\s+/).filter(Boolean);
    let primera = null;
    [...select.options].forEach((opt) => {
      const texto = normalizar(opt.textContent);
      opt.hidden = !terminos.every((t) => texto.includes(t));
      if (!opt.hidden && !opt.disabled && !primera) primera = opt;
    });
    select.querySelectorAll('optgroup').forEach((grupo) => {
      grupo.hidden = ![...grupo.children].some((opt) => !opt.hidden);
    });
    const actual = select.options[select.selectedIndex];
    if (primera && (!actual || actual.hidden)) {
      select.value = primera.value;
      select.dispatchEvent(new Event('change', { bubbles: true }));
    }
    entrada.classList.toggle('is-invalid', terminos.length > 0 && !primera);
  }

  document.addEventListener('input', (e) => {
    if (e.target.matches('.filtro-opciones')) filtrar(e.target);
  });

  window.limpiarFiltroOpciones = function (contenedor) {
    contenedor.querySelectorAll('.filtro-opciones').forEach((entrada) => {
      entrada.value = '';
      entrada.classList.remove('is-invalid');
    });
    contenedor.querySelectorAll('option, optgroup').forEach((el) => { el.hidden = false; });
  };
})();
