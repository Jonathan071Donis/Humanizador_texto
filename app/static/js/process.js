(() => {
  let state = {
    filename: 'pasted_text.txt',
    content: '',
    detection: null,
  };
  let humanizedText = '';

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
  const btnAnalyzeSpinner = document.getElementById('btnAnalyzeSpinner');
  const btnAnalyzeLabel = document.getElementById('btnAnalyzeLabel');
  const analyzeError = document.getElementById('analyzeError');

  const loadingSkeleton = document.getElementById('loadingSkeleton');
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

  const aiScoreValue = document.getElementById('aiScoreValue');
  const aiScoreMeter = document.getElementById('aiScoreMeter');
  const aiScoreSignals = document.getElementById('aiScoreSignals');

  const humanizeToggle = document.getElementById('humanizeToggle');
  const humanizeIntensity = document.getElementById('humanizeIntensity');
  const humanizeWrap = document.getElementById('humanizeWrap');
  const humanizeLoading = document.getElementById('humanizeLoading');
  const humanizeOriginal = document.getElementById('humanizeOriginal');
  const humanizeResult = document.getElementById('humanizeResult');
  const humanizeChanges = document.getElementById('humanizeChanges');
  const humanizeScoreCompare = document.getElementById('humanizeScoreCompare');
  const btnCopyHumanized = document.getElementById('btnCopyHumanized');

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

  // Editing the source text invalidates any humanized preview - reset it
  // so the user never sees a humanized version out of sync with the input.
  pasteArea.addEventListener('input', resetHumanizeState);

  function resetHumanizeState() {
    humanizeToggle.checked = false;
    humanizeIntensity.disabled = true;
    humanizeWrap.classList.add('d-none');
    humanizeLoading.classList.add('d-none');
    humanizedText = '';
  }

  function currentConfig() {
    return {
      keywords: keywordsInput.value.split(',').map((k) => k.trim()).filter(Boolean),
      use_regex: useRegex.checked,
      case_sensitive: caseSensitive.checked,
      detect_invisible_unicode: detectInvisible.checked,
    };
  }

  function setAnalyzing(isAnalyzing) {
    btnAnalyze.disabled = isAnalyzing;
    btnAnalyzeSpinner.classList.toggle('d-none', !isAnalyzing);
    btnAnalyzeLabel.innerHTML = isAnalyzing
      ? 'Analizando&hellip;'
      : '<i class="bi bi-search me-1"></i>Analizar';
    if (isAnalyzing) {
      emptyState.classList.add('d-none');
      resultsWrap.classList.add('d-none');
      loadingSkeleton.classList.remove('d-none');
    } else {
      loadingSkeleton.classList.add('d-none');
    }
  }

  async function analyze() {
    analyzeError.classList.add('d-none');
    setAnalyzing(true);
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
      resetHumanizeState();
      renderResults(result);
    } catch (err) {
      loadingSkeleton.classList.add('d-none');
      emptyState.classList.remove('d-none');
      analyzeError.textContent = err.message || 'Error inesperado';
      analyzeError.classList.remove('d-none');
    } finally {
      setAnalyzing(false);
    }
  }

  function renderResults(result) {
    resultsWrap.classList.remove('d-none');
    emptyState.classList.add('d-none');
    diffWrap.classList.add('d-none');

    resultFilename.textContent = result.filename;
    resultMeta.textContent = `${result.file_type.toUpperCase()} · ${result.original_length} caracteres`;
    if (result.clean) {
      resultBadge.innerHTML = '<i class="bi bi-check-circle"></i> sin marcas detectadas';
      resultBadge.className = 'wm-tag wm-tag-clean';
    } else {
      resultBadge.innerHTML = `<i class="bi bi-exclamation-triangle"></i> ${result.total_findings} hallazgo(s)`;
      resultBadge.className = 'wm-tag wm-tag-found';
    }

    renderAiScore(result.ai_score);

    findingsList.innerHTML = '';
    if (result.total_findings === 0) {
      findingsList.innerHTML = '<p class="wm-muted mb-0">No se encontraron marcas de agua.</p>';
    }
    result.invisible_chars.forEach((m) => {
      findingsList.appendChild(
        findingRow(m.id, 'invisible', `${m.codepoint} — ${m.name}`, `línea ${m.line}, col ${m.column}`)
      );
    });
    result.keyword_matches.forEach((m) => {
      findingsList.appendChild(
        findingRow(m.id, 'keyword', `"${escapeHtml(m.matched_text)}"`, `línea ${m.line}, col ${m.column} · patrón: ${escapeHtml(m.keyword)}`)
      );
    });
  }

  function riskClassFor(score) {
    if (score >= 65) return 'wm-risk-high';
    if (score >= 35) return 'wm-risk-mid';
    return 'wm-risk-low';
  }

  function setRiskClass(el, score) {
    el.classList.remove('wm-risk-low', 'wm-risk-mid', 'wm-risk-high');
    el.classList.add(riskClassFor(score));
  }

  function renderAiScore(aiScore) {
    if (!aiScore) {
      aiScoreValue.textContent = '—';
      aiScoreValue.classList.remove('wm-risk-low', 'wm-risk-mid', 'wm-risk-high');
      aiScoreMeter.style.width = '0%';
      aiScoreMeter.classList.remove('wm-risk-low', 'wm-risk-mid', 'wm-risk-high');
      aiScoreSignals.innerHTML = '';
      return;
    }
    const score = Math.min(100, Math.max(0, aiScore.score));
    aiScoreValue.textContent = `${aiScore.score}%`;
    aiScoreMeter.style.width = `${score}%`;
    setRiskClass(aiScoreValue, score);
    setRiskClass(aiScoreMeter, score);
    aiScoreSignals.innerHTML = '';
    aiScore.signals.forEach((signal) => {
      const li = document.createElement('li');
      li.innerHTML = `<i class="bi bi-dot"></i><span>${escapeHtml(signal)}</span>`;
      aiScoreSignals.appendChild(li);
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

  function renderScoreCompare(before, after) {
    if (!before || !after) {
      humanizeScoreCompare.innerHTML = '';
      return;
    }
    const delta = Math.round((after.score - before.score) * 10) / 10;
    let deltaClass = 'wm-delta-flat';
    let deltaLabel = 'sin cambio';
    if (delta < 0) { deltaClass = 'wm-delta-down'; deltaLabel = `${delta}%`; }
    else if (delta > 0) { deltaClass = 'wm-delta-up'; deltaLabel = `+${delta}%`; }
    humanizeScoreCompare.innerHTML = `
      <span class="wm-score-compare-label">Score de IA (nuestro heurístico local):</span>
      <span class="wm-score-compare-value ${riskClassFor(before.score)}">${before.score}%</span>
      <i class="bi bi-arrow-right wm-score-compare-arrow"></i>
      <span class="wm-score-compare-value ${riskClassFor(after.score)}">${after.score}%</span>
      <span class="wm-score-compare-delta ${deltaClass}">${deltaLabel}</span>
    `;
  }

  async function runHumanize() {
    if (!state.content.trim()) return;
    humanizeWrap.classList.add('d-none');
    humanizeLoading.classList.remove('d-none');
    try {
      const res = await fetch('/api/humanize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: state.content, intensity: humanizeIntensity.value }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || 'Error al generar la versión humanizada');
      const data = await res.json();
      humanizedText = data.humanized;
      humanizeOriginal.textContent = data.original;
      humanizeResult.textContent = data.humanized;
      humanizeChanges.innerHTML = '';
      data.changes.forEach((c) => {
        const li = document.createElement('li');
        li.innerHTML = `<i class="bi bi-arrow-right-short"></i><span>${escapeHtml(c)}</span>`;
        humanizeChanges.appendChild(li);
      });
      renderScoreCompare(data.score_before, data.score_after);
      humanizeWrap.classList.remove('d-none');
    } catch (err) {
      humanizeToggle.checked = false;
      humanizeIntensity.disabled = true;
      analyzeError.textContent = err.message || 'Error inesperado al humanizar el texto';
      analyzeError.classList.remove('d-none');
    } finally {
      humanizeLoading.classList.add('d-none');
    }
  }

  humanizeToggle.addEventListener('change', () => {
    humanizeIntensity.disabled = !humanizeToggle.checked;
    if (humanizeToggle.checked) {
      runHumanize();
    } else {
      humanizeWrap.classList.add('d-none');
    }
  });
  humanizeIntensity.addEventListener('change', () => {
    if (humanizeToggle.checked) runHumanize();
  });
  btnCopyHumanized.addEventListener('click', async () => {
    if (!humanizedText) return;
    try {
      await navigator.clipboard.writeText(humanizedText);
      const original = btnCopyHumanized.innerHTML;
      btnCopyHumanized.innerHTML = '<i class="bi bi-check2 me-1"></i>Copiado';
      setTimeout(() => { btnCopyHumanized.innerHTML = original; }, 1500);
    } catch (err) {
      // clipboard API unavailable/denied - nothing else we can do here
    }
  });

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
