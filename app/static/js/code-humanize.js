(() => {
  const codeInput = document.getElementById('codeInput');
  const codeLanguage = document.getElementById('codeLanguage');
  const codeIntensity = document.getElementById('codeIntensity');
  const btnHumanizeCode = document.getElementById('btnHumanizeCode');
  const btnHumanizeCodeSpinner = document.getElementById('btnHumanizeCodeSpinner');
  const btnHumanizeCodeLabel = document.getElementById('btnHumanizeCodeLabel');
  const codeHumanizeError = document.getElementById('codeHumanizeError');
  const codeResult = document.getElementById('codeResult');
  const codeChanges = document.getElementById('codeChanges');
  const codeDetectedLang = document.getElementById('codeDetectedLang');
  const btnCopyCode = document.getElementById('btnCopyCode');

  let humanizedCode = '';

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  function setLoading(isLoading) {
    btnHumanizeCode.disabled = isLoading;
    btnHumanizeCodeSpinner.classList.toggle('d-none', !isLoading);
    btnHumanizeCodeLabel.innerHTML = isLoading
      ? 'Procesando&hellip;'
      : '<i class="bi bi-magic me-1"></i>Humanizar comentarios';
  }

  async function humanizeCode() {
    codeHumanizeError.classList.add('d-none');
    const code = codeInput.value;
    if (!code.trim()) {
      codeHumanizeError.textContent = 'Pega algo de código primero.';
      codeHumanizeError.classList.remove('d-none');
      return;
    }
    setLoading(true);
    try {
      const res = await fetch('/api/humanize-code', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code,
          language: codeLanguage.value,
          intensity: codeIntensity.value,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Error al humanizar el código');
      }
      const data = await res.json();
      humanizedCode = data.humanized;
      codeResult.textContent = data.humanized;
      codeDetectedLang.textContent = data.language;
      codeDetectedLang.classList.remove('d-none');
      codeChanges.innerHTML = '';
      data.changes.forEach((c) => {
        const li = document.createElement('li');
        li.innerHTML = `<i class="bi bi-arrow-right-short"></i><span>${escapeHtml(c)}</span>`;
        codeChanges.appendChild(li);
      });
    } catch (err) {
      codeHumanizeError.textContent = err.message || 'Error inesperado';
      codeHumanizeError.classList.remove('d-none');
    } finally {
      setLoading(false);
    }
  }

  btnHumanizeCode.addEventListener('click', humanizeCode);
  btnCopyCode.addEventListener('click', async () => {
    if (!humanizedCode) return;
    try {
      await navigator.clipboard.writeText(humanizedCode);
      const original = btnCopyCode.innerHTML;
      btnCopyCode.innerHTML = '<i class="bi bi-check2 me-1"></i>Copiado';
      setTimeout(() => { btnCopyCode.innerHTML = original; }, 1500);
    } catch (err) {
      // clipboard API unavailable/denied - nothing else we can do here
    }
  });
})();
