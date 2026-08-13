(() => {
  let selectedFiles = [];

  const dropZone = document.getElementById('batchDropZone');
  const fileInput = document.getElementById('batchFileInput');
  const fileListBox = document.getElementById('batchFileList');
  const keywordsInput = document.getElementById('batchKeywordsInput');
  const useRegex = document.getElementById('batchUseRegex');
  const caseSensitive = document.getElementById('batchCaseSensitive');
  const detectInvisible = document.getElementById('batchDetectInvisible');
  const btnAnalyze = document.getElementById('btnBatchAnalyze');
  const btnZip = document.getElementById('btnBatchDownloadZip');
  const progressWrap = document.getElementById('batchProgressWrap');
  const progressBar = document.getElementById('batchProgressBar');
  const batchError = document.getElementById('batchError');
  const resultsBody = document.getElementById('batchResultsBody');
  const logBox = document.getElementById('batchLog');

  function log(msg) {
    const ts = new Date().toLocaleTimeString();
    logBox.textContent += `[${ts}] ${msg}\n`;
    logBox.scrollTop = logBox.scrollHeight;
  }

  function updateFileList() {
    if (!selectedFiles.length) {
      fileListBox.textContent = '';
      return;
    }
    fileListBox.textContent = `${selectedFiles.length} archivo(s): ` + selectedFiles.map((f) => f.name).join(', ');
  }

  ['dragover', 'dragenter'].forEach((evt) =>
    dropZone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropZone.classList.add('wm-drag-over');
    })
  );
  ['dragleave', 'drop'].forEach((evt) =>
    dropZone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropZone.classList.remove('wm-drag-over');
    })
  );
  dropZone.addEventListener('drop', (e) => {
    if (e.dataTransfer.files.length) {
      selectedFiles = Array.from(e.dataTransfer.files);
      updateFileList();
    }
  });
  fileInput.addEventListener('change', () => {
    selectedFiles = Array.from(fileInput.files);
    updateFileList();
  });

  function currentConfig() {
    return {
      keywords: keywordsInput.value.split(',').map((k) => k.trim()).filter(Boolean),
      use_regex: useRegex.checked,
      case_sensitive: caseSensitive.checked,
      detect_invisible_unicode: detectInvisible.checked,
    };
  }

  function buildForm() {
    const form = new FormData();
    selectedFiles.forEach((f) => form.append('files', f));
    const cfg = currentConfig();
    form.append('keywords', cfg.keywords.join(','));
    form.append('use_regex', cfg.use_regex);
    form.append('case_sensitive', cfg.case_sensitive);
    form.append('detect_invisible_unicode', cfg.detect_invisible_unicode);
    return form;
  }

  async function analyzeBatch() {
    batchError.classList.add('d-none');
    if (!selectedFiles.length) {
      batchError.textContent = 'Selecciona al menos un archivo.';
      batchError.classList.remove('d-none');
      return;
    }
    btnAnalyze.disabled = true;
    btnAnalyze.textContent = 'Procesando...';
    progressWrap.classList.remove('d-none');
    progressBar.style.width = '15%';
    log(`Enviando ${selectedFiles.length} archivo(s) al servidor...`);

    try {
      const res = await fetch('/api/batch/detect', { method: 'POST', body: buildForm() });
      progressBar.style.width = '70%';
      if (!res.ok) {
        const data = await res.json().catch(() => ({ detail: 'Error en el procesamiento por lote' }));
        throw new Error(data.detail);
      }
      const data = await res.json();
      progressBar.style.width = '100%';
      renderResults(data.results);
      log(`Completado: ${data.results.length} archivo(s) procesados.`);
      btnZip.classList.remove('d-none');
    } catch (err) {
      batchError.textContent = err.message || 'Error inesperado';
      batchError.classList.remove('d-none');
      log(`Error: ${err.message}`);
    } finally {
      btnAnalyze.disabled = false;
      btnAnalyze.textContent = 'Analizar lote';
      setTimeout(() => progressWrap.classList.add('d-none'), 800);
    }
  }

  function renderResults(results) {
    resultsBody.innerHTML = '';
    results.forEach((r) => {
      const tr = document.createElement('tr');
      if (r.status === 'error') {
        tr.innerHTML = `<td>${escapeHtml(r.filename)}</td><td><span class="wm-tag wm-tag-found">error</span></td><td class="wm-muted">${escapeHtml(r.message || '')}</td>`;
        log(`\u2717 ${r.filename}: ${r.message}`);
      } else {
        const d = r.detection;
        const badge = d.clean
          ? '<span class="wm-tag wm-tag-clean">limpio</span>'
          : `<span class="wm-tag wm-tag-found">${d.total_findings} hallazgo(s)</span>`;
        tr.innerHTML = `<td>${escapeHtml(r.filename)}</td><td>ok</td><td>${badge}</td>`;
        log(`\u2713 ${r.filename}: ${d.total_findings} hallazgo(s)`);
      }
      resultsBody.appendChild(tr);
    });
  }

  btnAnalyze.addEventListener('click', analyzeBatch);
  btnZip.addEventListener('click', async () => {
    log('Generando ZIP con archivos limpios...');
    const res = await fetch('/api/batch/clean-zip', { method: 'POST', body: buildForm() });
    if (!res.ok) {
      log('Error al generar el ZIP.');
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'cleaned_files.zip';
    a.click();
    URL.revokeObjectURL(url);
    log('ZIP descargado.');
  });
})();
