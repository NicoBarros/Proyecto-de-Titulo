(function () {
  const modalEl = document.getElementById('qrModal');
  const modal = modalEl ? new bootstrap.Modal(modalEl) : null;

  document.addEventListener('click', (e) => {
    const boton = e.target.closest('[data-qr]');
    if (!boton || !modal) return;
    document.getElementById('qrModalLabel').textContent = 'QR: ' + boton.dataset.codigo;
    document.getElementById('qrImage').src = boton.dataset.qr;
    document.getElementById('qrDescargar').href = boton.dataset.qr + '?descargar=1';
    modal.show();
  });
})();
