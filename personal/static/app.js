const fileInput = document.getElementById('file-input');
const dropzone = document.getElementById('dropzone');
if (dropzone && fileInput) {
  for (const event of ['dragenter', 'dragover']) dropzone.addEventListener(event, e => { e.preventDefault(); dropzone.classList.add('dragover'); });
  for (const event of ['dragleave', 'drop']) dropzone.addEventListener(event, e => { e.preventDefault(); dropzone.classList.remove('dragover'); });
  dropzone.addEventListener('drop', e => {
    if (e.dataTransfer.files.length) { fileInput.files = e.dataTransfer.files; fileInput.dispatchEvent(new Event('change')); }
  });
  fileInput.addEventListener('change', () => {
    const label = dropzone.querySelector('strong');
    label.textContent = fileInput.files[0]?.name || 'Tu siguiente cartera empieza aquí';
  });
}
for (const form of document.querySelectorAll('[data-payment-form]')) {
  form.addEventListener('submit', event => {
    const amount = form.elements.amount.value;
    if (!confirm(`¿Confirmas registrar un pago de $${amount} MXN? El saldo se reducirá y el movimiento quedará en el historial.`)) {
      event.preventDefault();
    }
  });
}
for (const form of document.querySelectorAll('[data-message-form]')) {
  form.addEventListener('submit', event => {
    if (form.elements.mode.value === 'live') {
      const count = form.querySelectorAll('input[name="clients"]:checked').length;
      if (!confirm(`¿Confirmas enviar un mensaje REAL a ${count} destinatarios por la API oficial de WhatsApp? El proveedor puede cobrar estos mensajes.`)) event.preventDefault();
    }
  });
}
