(function () {
  const modalEl = document.getElementById('pwdModal');
  const modal = modalEl ? new bootstrap.Modal(modalEl) : null;

  document.addEventListener('click', (e) => {
    const boton = e.target.closest('[data-reset-password]');
    if (!boton || !modal) return;
    document.getElementById('pwdModalUserId').value = boton.dataset.userId;
    document.getElementById('pwdModalUser').innerText = 'Usuario: ' + boton.dataset.email;
    modal.show();
  });
})();
