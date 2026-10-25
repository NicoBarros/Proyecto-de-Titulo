(function () {
  // Prevención de acceso tras cierre de sesión vía botón Atrás del navegador (BFCache):
  // Si la página se recupera de la memoria caché del navegador, fuerza la recarga
  // para que el servidor verifique la autenticación y redirija al login.
  window.addEventListener('pageshow', function (event) {
    var navEntries = window.performance && performance.getEntriesByType && performance.getEntriesByType('navigation');
    var isBackForward = event.persisted || (navEntries && navEntries[0] && navEntries[0].type === 'back_forward');
    if (isBackForward) {
      window.location.reload();
    }
  });

  if ('scrollRestoration' in history) {
    history.scrollRestoration = 'manual';
  }

  var scrollKey = 'leica_scroll_' + window.location.pathname;

  // Restauración instantánea directa sin animaciones ni retrasos
  var savedPos = sessionStorage.getItem(scrollKey);
  if (savedPos !== null) {
    var pos = parseInt(savedPos, 10);
    if (!isNaN(pos) && pos > 0) {
      window.scrollTo({ top: pos, left: 0, behavior: 'instant' });
    }
  }

  // Save scroll position continuously and before unload
  window.addEventListener('scroll', function () {
    sessionStorage.setItem(scrollKey, window.scrollY);
  }, { passive: true });

  window.addEventListener('beforeunload', function () {
    sessionStorage.setItem(scrollKey, window.scrollY);
  });

  // Clear destination scroll only when user explicitly clicks a sidebar navigation item
  document.addEventListener('click', function (e) {
    var navLink = e.target.closest('.leica-nav-item, .leica-sidebar-brand a');
    if (navLink) {
      try {
        var url = new URL(navLink.href, window.location.origin);
        sessionStorage.removeItem('leica_scroll_' + url.pathname);
        sessionStorage.removeItem(scrollKey);
      } catch (err) {}
      return;
    }

    var a = e.target.closest('a');
    if (a && a.href && !a.getAttribute('href').startsWith('#')) {
      try {
        var targetUrl = new URL(a.href, window.location.origin);
        if (targetUrl.pathname !== window.location.pathname) {
          sessionStorage.removeItem('leica_scroll_' + targetUrl.pathname);
        }
      } catch (err) {}
    }
  });

  // Helper global para alertas informativas con modal Bootstrap integrado
  window.mostrarAlerta = function (mensaje, titulo, opciones) {
    opciones = opciones || {};
    var modalEl = document.getElementById('leicaConfirmModal');
    if (!modalEl) {
      window.nativeAlert ? window.nativeAlert(mensaje) : alert(mensaje);
      return;
    }
    var bsModal = bootstrap.Modal.getOrCreateInstance(modalEl);

    var titleEl = document.getElementById('leicaConfirmTitle');
    var msgEl = document.getElementById('leicaConfirmMessage');
    var btnEl = document.getElementById('leicaConfirmBtn');
    var cancelBtn = modalEl.querySelector('[data-bs-dismiss="modal"]');
    var iconEl = document.getElementById('leicaConfirmIcon');

    titleEl.textContent = titulo || 'Aviso';
    msgEl.textContent = mensaje;
    btnEl.textContent = opciones.btnText || 'Aceptar';
    btnEl.className = 'btn btn-sm px-4 fw-semibold ' + (opciones.btnClass || 'btn-leica');

    if (cancelBtn) cancelBtn.style.display = 'none';

    iconEl.className = opciones.iconClass || 'bi bi-info-circle-fill fs-3 text-warning';
    iconEl.parentElement.className = 'd-inline-flex align-items-center justify-content-center rounded-circle bg-warning-subtle text-warning';

    var newBtn = btnEl.cloneNode(true);
    btnEl.parentNode.replaceChild(newBtn, btnEl);

    function cleanup() {
      if (cancelBtn) cancelBtn.style.display = '';
      iconEl.className = 'bi bi-exclamation-triangle-fill fs-3';
      iconEl.parentElement.className = 'd-inline-flex align-items-center justify-content-center rounded-circle bg-danger-subtle text-danger';
    }

    newBtn.addEventListener('click', function () {
      bsModal.hide();
      cleanup();
      if (typeof opciones.onClose === 'function') opciones.onClose();
    });

    modalEl.addEventListener('hidden.bs.modal', function handler() {
      cleanup();
      modalEl.removeEventListener('hidden.bs.modal', handler);
    });

    bsModal.show();
  };

  // Redirigir llamadas de alert() nativo hacia el modal integrado
  window.nativeAlert = window.alert;
  window.alert = function (mensaje) {
    window.mostrarAlerta(mensaje, 'Aviso');
  };

  // Helper global para confirmar acciones con modal Bootstrap integrado
  window.confirmarAccion = function (options) {
    var modalEl = document.getElementById('leicaConfirmModal');
    if (!modalEl) {
      if (confirm(options.message || '¿Confirmar acción?')) {
        if (typeof options.onConfirm === 'function') options.onConfirm();
      }
      return;
    }
    var bsModal = bootstrap.Modal.getOrCreateInstance(modalEl);

    var titleEl = document.getElementById('leicaConfirmTitle');
    var msgEl = document.getElementById('leicaConfirmMessage');
    var btnEl = document.getElementById('leicaConfirmBtn');
    var iconEl = document.getElementById('leicaConfirmIcon');

    titleEl.textContent = options.title || '¿Confirmar acción?';
    msgEl.textContent = options.message || '¿Estás seguro de continuar?';
    btnEl.textContent = options.btnText || 'Confirmar';
    btnEl.className = 'btn btn-sm px-3 fw-semibold ' + (options.btnClass || 'btn-danger');

    if (options.iconClass) {
      iconEl.className = options.iconClass;
    } else {
      iconEl.className = 'bi bi-exclamation-triangle-fill fs-3';
    }

    var newBtn = btnEl.cloneNode(true);
    btnEl.parentNode.replaceChild(newBtn, btnEl);

    newBtn.addEventListener('click', function () {
      bsModal.hide();
      if (typeof options.onConfirm === 'function') {
        options.onConfirm();
      }
    });

    bsModal.show();
  };

  // Interceptor de data-confirm para reemplazar el confirm() nativo del navegador
  document.addEventListener('click', function (e) {
    var trigger = e.target.closest('[data-confirm]');
    if (!trigger) return;

    e.preventDefault();
    e.stopPropagation();

    var message = trigger.getAttribute('data-confirm');
    var title = trigger.getAttribute('data-confirm-title') || '¿Confirmar acción?';
    var btnText = trigger.getAttribute('data-confirm-btn') || 'Confirmar';
    var btnClass = trigger.getAttribute('data-confirm-class') || 'btn-danger';

    window.confirmarAccion({
      title: title,
      message: message,
      btnText: btnText,
      btnClass: btnClass,
      onConfirm: function () {
        var form = trigger.closest('form');
        if (form) {
          if (trigger.name) {
            var hidden = document.createElement('input');
            hidden.type = 'hidden';
            hidden.name = trigger.name;
            hidden.value = trigger.value || '';
            form.appendChild(hidden);
          }
          form.submit();
        } else if (trigger.tagName === 'A' && trigger.href) {
          window.location.href = trigger.href;
        }
      }
    });
  });

  document.addEventListener('click', function (e) {
    var campo = e.target.closest('input[type="date"], input[type="datetime-local"], input[type="time"]');
    if (campo && typeof campo.showPicker === 'function') {
      try { campo.showPicker(); } catch (err) {}
    }
  });

  var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
  tooltipTriggerList.forEach(function (el) {
    new bootstrap.Tooltip(el);
  });
  document.addEventListener('change', function (e) {
    var campo = e.target.closest('[data-autosubmit]');
    if (campo && campo.form) campo.form.submit();
  });
})();
