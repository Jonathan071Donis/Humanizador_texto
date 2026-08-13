(() => {
  let state = {
    filename: 'pasted_text.txt',
    content: '',
    detection: null,
  };

  const pasteArea = document.getElementById('pasteArea');
  const pasteFilename = document.getElementById('pasteFilename');
  const fileInput = document.getElementById('fileInput');
  const dropZone = document.getElementById('dropZone');
  const fileNamePreview = document.getElementById('fileNamePreview');
  const keywordsInput = document.getElementById('keywordsInput');
  const useRegex = document.getElementById('useRegex');
  const caseSensitive = document.getElementById('caseSensitive');
  const detectInvisible = document.getElementById('detectInvisible');
  const btnAnalyze = document.getElementById('btnAnalyze');
  const analyzeError = document.getElementById('analyzeError');

  const resultsWrap = document.getElementById('resultsWrap');
  const emptyState = document.getElementById('emptyState');
  const resultFilename = document.getElementById('resultFilename');
  const resultMeta = document.getElementById('resultMeta');
  const resultBadge = document.getElementById('resultBadge');
  const findingsList = document.getElementById('findingsList');
  const btnRemoveSelected = document.getElementById('btnRemoveSelected');
  const btnRemoveAll = document.getElementById('btnRemoveAll');
  const diffWrap = document.getElementById('diffWrap');
  const diffPreview = document.getElementById('diffPreview');
  const btnDownload = document.getElementById('btnDownload');

  let activeTab = 'paste';
  document.querySelectorAll('#sourceTabs button').forEach((btn) => {
    btn.addEventListener('click', () => {
      activeTab = btn.getAttribute('data-bs-target') === '#tabFile' ? 'file' : 'paste';
    });
  });

  let selectedFile = null;

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
      selectedFile = e.dataTransfer.files[0];
      fileInput.files = e.dataTransfer.files;
      fileNamePreview.textContent = `Archivo seleccionado: ${selectedFile.name}`;
    }
  });
  fileInput.addEventListener('change', () => {
    if (fileInput.files.length) {
      selectedFile = fileInput.files[0];
      fileNamePreview.textContent = `Archivo seleccionado: ${selectedFile.name}`;
    }
  });

  function currentConfig() {
    return {
      keywords: keywordsInput.value.split(',').map((k) => k.trim()).filter(Boolean),
      use_regex: useRegex.checked,
      case_sensitive: caseSensitive.checked,
      detect_invisible_unicode: detectInvisible.checked,
    };
  }

  async function analyze() {
    analyzeError.classList.add('d-none');
    btnAnalyze.disabled = true;
    btnAnalyze.textContent = 'Analizando...';
    try {
      let result;
      if (activeTab === 'paste') {
        const content = pasteArea.value;
        if (!content.trim()) throw new Error('Pega algo de texto primero.');
        const filename = pasteFilename.value.trim() || 'pasted_text.txt';
        const res = await fetch('/api/detect/text', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content, filename, config: currentConfig() }),
        });
        if (!res.ok) throw new Error((await res.json()).detail || 'Error al analizar');
        result = await res.json();
      } else {
        if (!selectedFile) throw new Error('Selecciona un archivo primero.');
        const form = new FormData();
        form.append('file', selectedFile);
        const cfg = currentConfig();
        form.append('keywords', cfg.keywords.join(','));
        form.append('use_regex', cfg.use_regex);
        form.append('case_sensitive', cfg.case_sensitive);
        form.append('detect_invisible_unicode', cfg.detect_invisible_unicode);
        const res = await fetch('/api/detect/file', { method: 'POST', body: form });
        if (!res.ok) throw new Error((await res.json()).detail || 'Error al analizar el archivo');
        result = await res.json();
      }
      state.filename = result.filename;
      state.content = result.extracted_text;
      state.detection = result;
      renderResults(result);
    } catch (err) {
      analyzeError.textContent = err.message || 'Error inesperado';
      analyzeError.classList.remove('d-none');
    } finally {
      btnAnalyze.disabled = false;
      btnAnalyze.textContent = 'Analizar';
    }
  }

  function renderResults(result) {
    resultsWrap.classList.remove('d-none');
    emptyState.classList.add('d-none');
    diffWrap.classList.add('d-none');

    resultFilename.textContent = result.filename;
    resultMeta.textContent = `${result.file_type.toUpperCase()} \u00b7 ${result.original_length} caracteres`;
    if (result.clean) {
      resultBadge.textContent = 'sin marcas detectadas';
      resultBadge.className = 'wm-tag wm-tag-clean';
    } else {
      resultBadge.textContent = `${result.total_findings} hallazgo(s)`;
      resultBadge.className = 'wm-tag wm-tag-found';
    }

    findingsList.innerHTML = '';
    if (result.total_findings === 0) {
      findingsList.innerHTML = '<p class="wm-muted mb-0">No se encontraron marcas de agua.</p>';
    }
    result.invisible_chars.forEach((m) => {
      findingsList.appendChild(
        findingRow(m.id, 'invisible', `${m.codepoint} \u2014 ${m.name}`, `l\u00ednea ${m.line}, col ${m.column}`)
      );
    });
    result.keyword_matches.forEach((m) => {
      findingsList.appendChild(
        findingRow(m.id, 'keyword', `"${escapeHtml(m.matched_text)}"`, `l\u00ednea ${m.line}, col ${m.column} \u00b7 patr\u00f3n: ${escapeHtml(m.keyword)}`)
      );
    });
  }

  function findingRow(id, kind, label, meta) {
    const row = document.createElement('label');
    row.className = 'wm-finding-item';
    row.innerHTML = `
      <input type="checkbox" class="form-check-input finding-checkbox" data-id="${id}" data-kind="${kind}" checked>
      <span>${label}</span>
      <span class="wm-finding-meta ms-auto">${meta}</span>
    `;
    return row;
  }

  async function clean(removeAll) {
    if (!state.detection) return;
    let invIds = null;
    let kwIds = null;
    if (!removeAll) {
      invIds = [];
      kwIds = [];
      document.querySelectorAll('.finding-checkbox:checked').forEach((cb) => {
        if (cb.dataset.kind === 'invisible') invIds.push(cb.dataset.id);
        else kwIds.push(cb.dataset.id);
      });
    }
    const res = await fetch('/api/clean', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        content: state.content,
        filename: state.filename,
        config: currentConfig(),
        remove_invisible_ids: invIds,
        remove_keyword_ids: kwIds,
      }),
    });
    if (!res.ok) return;
    const result = await res.json();
    state.cleanedContent = result.cleaned_content;
    diffWrap.classList.remove('d-none');
    diffPreview.innerHTML = result.diff_html || '<span class="wm-muted">Sin cambios.</span>';
  }

  btnAnalyze.addEventListener('click', analyze);
  btnRemoveSelected.addEventListener('click', () => clean(false));
  btnRemoveAll.addEventListener('click', () => clean(true));
  btnDownload.addEventListener('click', async () => {
    const res = await fetch('/api/clean/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        content: state.content,
        filename: state.filename,
        config: currentConfig(),
        remove_invisible_ids: null,
        remove_keyword_ids: null,
      }),
    });
    if (!res.ok) return;
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `clean_${state.filename}`;
    a.click();
    URL.revokeObjectURL(url);
  });
})();
