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
  const recipients = [...form.querySelectorAll('input[name="clients"]')];
  const balanceOnly = form.elements.balance_only;
  const updateCount = () => {
    const count = recipients.filter(input => input.checked).length;
    form.querySelector('[data-recipient-count]').textContent = `${count} destinatarios seleccionados · máximo 50`;
  };
  form.querySelector('[data-select-recipients]').addEventListener('click', () => {
    let count = 0;
    for (const input of recipients) {
      input.checked = !input.disabled && (!balanceOnly.checked || Number(input.dataset.balance) > 0) && count < 50;
      if (input.checked) count++;
    }
    updateCount();
  });
  form.querySelector('[data-clear-recipients]').addEventListener('click', () => {
    recipients.forEach(input => { input.checked = false; });
    updateCount();
  });
  form.addEventListener('change', () => {
    if (balanceOnly.checked) recipients.filter(input => Number(input.dataset.balance) <= 0).forEach(input => { input.checked = false; });
    updateCount();
  });
  form.addEventListener('submit', event => {
    const count = recipients.filter(input => input.checked).length;
    if (count < 1 || count > 50) {
      event.preventDefault();
      alert('Selecciona entre 1 y 50 destinatarios autorizados.');
      return;
    }
    if (form.elements.mode.value === 'live') {
      const count = form.querySelectorAll('input[name="clients"]:checked').length;
      if (!confirm(`¿Confirmas enviar un mensaje REAL a ${count} destinatarios por la API oficial de WhatsApp? El proveedor puede cobrar estos mensajes.`)) event.preventDefault();
    }
  });
}
