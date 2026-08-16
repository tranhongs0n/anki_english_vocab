/**
 * Anki Vocab Porter - Frontend Controller
 */

// Application State
const state = {
  ankiStatus: { connected: false, version: null, decks: [] },
  selectedFile: null,
  analysisResult: null,
  lastPayload: null,
  activeTab: 'uploadPanel',
  logs: []
};

// DOM Element References
const elements = {
  // Header
  ankiStatusPill: document.getElementById('ankiStatusPill'),
  ankiStatusText: document.getElementById('ankiStatusText'),
  btnRefreshStatus: document.getElementById('btnRefreshStatus'),
  targetDeckInput: document.getElementById('targetDeckInput'),

  // Tabs
  tabUploadBtn: document.getElementById('tabUploadBtn'),
  tabPasteBtn: document.getElementById('tabPasteBtn'),
  uploadPanel: document.getElementById('uploadPanel'),
  pastePanel: document.getElementById('pastePanel'),

  // Inputs
  dropzone: document.getElementById('dropzone'),
  fileInput: document.getElementById('fileInput'),
  fileBanner: document.getElementById('fileBanner'),
  selectedFileName: document.getElementById('selectedFileName'),
  selectedFileSize: document.getElementById('selectedFileSize'),
  btnRemoveFile: document.getElementById('btnRemoveFile'),

  rawTextInput: document.getElementById('rawTextInput'),
  charCount: document.getElementById('charCount'),
  btnLoadSample: document.getElementById('btnLoadSample'),

  chkGibberish: document.getElementById('chkGibberish'),
  chkStopwords: document.getElementById('chkStopwords'),
  ocrModeSelect: document.getElementById('ocrModeSelect'),
  pageRangeInput: document.getElementById('pageRangeInput'),
  btnAnalyze: document.getElementById('btnAnalyze'),

  // Results
  metricTotal: document.getElementById('metricTotal'),
  metricMove: document.getElementById('metricMove'),
  metricNew: document.getElementById('metricNew'),
  metricExamples: document.getElementById('metricExamples'),
  
  wordSearchInput: document.getElementById('wordSearchInput'),
  statusFilterSelect: document.getElementById('statusFilterSelect'),
  wordsTableBody: document.getElementById('wordsTableBody'),

  btnDryRun: document.getElementById('btnDryRun'),
  btnSyncAnki: document.getElementById('btnSyncAnki'),
  syncProgressBanner: document.getElementById('syncProgressBanner'),
  syncProgressBar: document.getElementById('syncProgressBar'),
  syncProgressText: document.getElementById('syncProgressText'),

  // Debugger
  debugTabs: document.querySelectorAll('.debug-tab'),
  debugPanes: document.querySelectorAll('.debug-pane'),
  consoleBox: document.getElementById('consoleBox'),
  btnClearLogs: document.getElementById('btnClearLogs'),
  btnCopyLogs: document.getElementById('btnCopyLogs'),
  payloadContent: document.getElementById('payloadContent'),
  btnCopyPayload: document.getElementById('btnCopyPayload'),
  bugDescriptionInput: document.getElementById('bugDescriptionInput'),
  btnCopyDebugBundle: document.getElementById('btnCopyDebugBundle')
};

// Logging Utility
function log(msg, type = 'info') {
  const timestamp = new Date().toLocaleTimeString();
  const line = `[${timestamp}] ${msg}`;
  state.logs.push(line);

  const lineEl = document.createElement('div');
  lineEl.className = `log-line ${type}`;
  lineEl.innerHTML = `<span class="log-time">[${timestamp}]</span> ${escapeHtml(msg)}`;
  
  elements.consoleBox.appendChild(lineEl);
  elements.consoleBox.scrollTop = elements.consoleBox.scrollHeight;
}

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function updatePayloadInspector(data) {
  state.lastPayload = data;
  elements.payloadContent.textContent = JSON.stringify(data, null, 2);
}

// 1. Anki Status Check
async function checkAnkiStatus() {
  elements.ankiStatusText.textContent = 'Checking Anki...';
  elements.ankiStatusPill.className = 'anki-status-pill';

  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    state.ankiStatus = data;
    updatePayloadInspector(data);

    if (data.connected) {
      elements.ankiStatusPill.classList.add('online');
      elements.ankiStatusText.textContent = `Anki v${data.version} Connected`;
      log(`AnkiConnect detected (v${data.version}, ${data.decks.length} decks, ${data.gibberish_count} gibberish entries loaded)`, 'success');
    } else {
      elements.ankiStatusPill.classList.add('offline');
      elements.ankiStatusText.textContent = 'Anki Offline';
      log(`AnkiConnect connection failed: ${data.error || 'Check Anki running on localhost:8765'}`, 'error');
    }
  } catch (err) {
    elements.ankiStatusPill.classList.add('offline');
    elements.ankiStatusText.textContent = 'Backend Offline';
    log(`Backend API unreachable: ${err.message}`, 'error');
  }
}

// 2. Tab Navigation
function setupTabs() {
  elements.tabUploadBtn.addEventListener('click', () => switchTab('uploadPanel'));
  elements.tabPasteBtn.addEventListener('click', () => switchTab('pastePanel'));

  elements.debugTabs.forEach(btn => {
    btn.addEventListener('click', () => {
      elements.debugTabs.forEach(b => b.classList.remove('active'));
      elements.debugPanes.forEach(p => p.classList.remove('active'));

      btn.classList.add('active');
      const targetId = btn.dataset.target;
      document.getElementById(targetId).classList.add('active');
    });
  });
}

function switchTab(tabId) {
  state.activeTab = tabId;
  if (tabId === 'uploadPanel') {
    elements.tabUploadBtn.classList.add('active');
    elements.tabPasteBtn.classList.remove('active');
    elements.uploadPanel.classList.add('active');
    elements.pastePanel.classList.remove('active');
  } else {
    elements.tabPasteBtn.classList.add('active');
    elements.tabUploadBtn.classList.remove('active');
    elements.pastePanel.classList.add('active');
    elements.uploadPanel.classList.remove('active');
  }
}

// 3. File Input & Drag and Drop Handling
function setupFileInput() {
  const dropzone = elements.dropzone;
  const fileInput = elements.fileInput;

  dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('drag-over');
  });

  dropzone.addEventListener('dragleave', () => {
    dropzone.classList.remove('drag-over');
  });

  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('drag-over');
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileSelected(e.dataTransfer.files[0]);
    }
  });

  fileInput.addEventListener('change', (e) => {
    if (e.target.files && e.target.files[0]) {
      handleFileSelected(e.target.files[0]);
    }
  });

  elements.btnRemoveFile.addEventListener('click', () => {
    state.selectedFile = null;
    fileInput.value = '';
    elements.fileBanner.classList.add('hidden');
    elements.dropzone.style.display = 'block';
    log('File selection removed.', 'info');
  });
}

function handleFileSelected(file) {
  state.selectedFile = file;
  elements.selectedFileName.textContent = file.name;
  elements.selectedFileSize.textContent = formatBytes(file.size);
  elements.fileBanner.classList.remove('hidden');
  elements.dropzone.style.display = 'none';
  log(`Selected file: ${file.name} (${formatBytes(file.size)})`, 'info');
}

function formatBytes(bytes) {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

// 4. Raw Text Input Handling
function setupTextInput() {
  elements.rawTextInput.addEventListener('input', () => {
    const text = elements.rawTextInput.value.trim();
    const words = text ? text.split(/\s+/).length : 0;
    elements.charCount.textContent = `${words} words (${text.length} chars)`;
  });

  elements.btnLoadSample.addEventListener('click', () => {
    elements.rawTextInput.value = `The TOEIC Listening and Reading test measures English-language proficiency for everyday business contexts. Admittance to the examination facility requires valid corporate or academic credentials. The marketing department demonstrated substantial resilience while analyzing consumer questionnaires.`;
    elements.rawTextInput.dispatchEvent(new Event('input'));
    log('Loaded sample passage into editor.', 'info');
  });
}

// 5. Extraction & Word Analysis
async function runAnalysis() {
  const targetDeck = elements.targetDeckInput.value.trim() || 'English::toeic';
  const enableGibberish = elements.chkGibberish.checked;
  const enableStopwords = elements.chkStopwords.checked;
  const pageRange = elements.pageRangeInput ? elements.pageRangeInput.value.trim() : '';
  const ocrMode = elements.ocrModeSelect ? elements.ocrModeSelect.value : 'auto';

  elements.btnAnalyze.disabled = true;
  elements.btnAnalyze.innerHTML = `<span class="spinner"></span> <span>Extracting & Analyzing...</span>`;
  elements.syncProgressBanner.classList.remove('hidden');
  elements.syncProgressBar.style.width = '5%';
  elements.syncProgressText.textContent = 'Starting analysis pipeline...';

  try {
    if (state.activeTab === 'uploadPanel') {
      if (!state.selectedFile) {
        alert('Please choose or drag a file first.');
        return;
      }
      log(`Starting analysis: ${state.selectedFile.name}${pageRange ? ` (Pages: ${pageRange})` : ''} [Mode: ${ocrMode}]...`, 'info');

      const formData = new FormData();
      formData.append('file', state.selectedFile);
      formData.append('target_deck', targetDeck);
      formData.append('enable_gibberish', enableGibberish);
      formData.append('enable_stopwords', enableStopwords);
      formData.append('ocr_mode', ocrMode);
      if (pageRange) formData.append('page_range', pageRange);

      const res = await fetch('/api/parse-file-stream', {
        method: 'POST',
        body: formData
      });

      if (!res.ok) {
        throw new Error(`HTTP Error ${res.status}: ${res.statusText}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split('\n\n');
        buffer = chunks.pop(); // keep unfinished trailing chunk

        for (const chunk of chunks) {
          const trimmed = chunk.trim();
          if (trimmed.startsWith('data: ')) {
            try {
              const event = JSON.parse(trimmed.slice(6));
              if (event.event === 'log') {
                log(event.message, event.type || 'info');
              } else if (event.event === 'progress') {
                elements.syncProgressBar.style.width = `${event.percent}%`;
                elements.syncProgressText.textContent = `OCR Progress: ${event.completed} / ${event.total} pages (${event.percent}%)`;
                elements.btnAnalyze.innerHTML = `<span class="spinner"></span> <span>OCR: ${event.completed}/${event.total} (${event.percent}%)</span>`;
              } else if (event.event === 'complete') {
                const data = event.data;
                state.analysisResult = data;
                updatePayloadInspector(data);
                renderResults(data);
                elements.syncProgressBar.style.width = '100%';
                elements.syncProgressText.textContent = `Analysis Complete: Found ${data.stats.total_extracted} unique words.`;
                log(`Analysis complete! Found ${data.stats.total_extracted} words (${data.stats.cards_to_move} to move, ${data.stats.brand_new_words} new, ${data.stats.notes_to_update_example} example updates).`, 'success');
              } else if (event.event === 'error') {
                throw new Error(event.message);
              }
            } catch (jsonErr) {
              console.error('SSE parse error:', jsonErr, trimmed);
            }
          }
        }
      }

    } else {
      const text = elements.rawTextInput.value.trim();
      if (!text) {
        alert('Please paste some text to analyze.');
        return;
      }
      log(`Starting analysis of pasted text (${text.length} chars)...`, 'info');
      elements.syncProgressBar.style.width = '40%';
      elements.syncProgressText.textContent = 'Analyzing text & querying Anki...';

      const res = await fetch('/api/parse-text', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text,
          target_deck: targetDeck,
          enable_gibberish: enableGibberish,
          enable_stopwords: enableStopwords
        })
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Analysis request failed.');
      }

      const data = await res.json();
      state.analysisResult = data;
      updatePayloadInspector(data);
      renderResults(data);
      elements.syncProgressBar.style.width = '100%';
      elements.syncProgressText.textContent = `Analysis Complete: Found ${data.stats.total_extracted} unique words.`;
      log(`Analysis complete! Found ${data.stats.total_extracted} words (${data.stats.cards_to_move} to move, ${data.stats.brand_new_words} new, ${data.stats.notes_to_update_example} example updates).`, 'success');
    }

  } catch (err) {
    log(`Analysis failed: ${err.message}`, 'error');
    elements.syncProgressText.textContent = `Failed: ${err.message}`;
    alert(`Error: ${err.message}`);
  } finally {
    elements.btnAnalyze.disabled = false;
    elements.btnAnalyze.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg> <span>Extract & Analyze</span>`;
  }
}

// 6. Render Results Table & Metrics
function renderResults(data) {
  const stats = data.stats;
  elements.metricTotal.textContent = stats.total_extracted;
  elements.metricMove.textContent = stats.cards_to_move;
  elements.metricNew.textContent = stats.brand_new_words;
  elements.metricExamples.textContent = stats.notes_to_update_example;

  filterAndRenderTable();
}

function filterAndRenderTable() {
  if (!state.analysisResult) return;

  const searchTerm = elements.wordSearchInput.value.trim().toLowerCase();
  const statusFilter = elements.statusFilterSelect.value;
  const items = state.analysisResult.items || [];

  const filtered = items.filter(item => {
    if (searchTerm && !item.word.includes(searchTerm)) return false;
    if (statusFilter !== 'all' && item.status !== statusFilter) return false;
    return true;
  });

  if (filtered.length === 0) {
    elements.wordsTableBody.innerHTML = `
      <tr>
        <td colspan="3" class="empty-state-cell">No matching words found for the current search/filter.</td>
      </tr>`;
    return;
  }

  const rowsHtml = filtered.map(item => {
    let badgeClass = 'badge-already';
    let badgeText = 'Already in Deck';

    if (item.status === 'move_to_deck') {
      badgeClass = 'badge-move';
      badgeText = 'Move to Deck';
    } else if (item.status === 'brand_new') {
      badgeClass = 'badge-new';
      badgeText = 'Brand New';
    }

    const exampleText = item.example ? escapeHtml(item.example) : '<span style="color:var(--text-faint)">No sentence found</span>';

    return `
      <tr>
        <td class="word-cell">${escapeHtml(item.word)}</td>
        <td><span class="status-badge ${badgeClass}">${badgeText}</span></td>
        <td class="example-cell" title="${escapeHtml(item.example || '')}">${exampleText}</td>
      </tr>
    `;
  }).join('');

  elements.wordsTableBody.innerHTML = rowsHtml;
}

// 7. Sync to Anki & Dry Run Execution
async function executeSync(isDryRun = false) {
  if (!state.analysisResult) {
    alert('Please run analysis first.');
    return;
  }

  const targetDeck = elements.targetDeckInput.value.trim() || 'English::toeic';
  const data = state.analysisResult;

  const cardsToMove = data.cards_to_move || [];
  const notesToUpdate = data.notes_to_update_example || [];
  const wordsToAdd = data.new_words_to_add || [];

  if (cardsToMove.length === 0 && notesToUpdate.length === 0 && wordsToAdd.length === 0) {
    alert('No updates needed. Everything is already synced with target deck.');
    return;
  }

  const actionName = isDryRun ? 'Dry Run' : 'Sync to Anki';
  log(`Executing ${actionName} on target deck '${targetDeck}'...`, 'info');

  elements.syncProgressBanner.classList.remove('hidden');
  elements.syncProgressBar.style.width = '30%';
  elements.syncProgressText.textContent = `${actionName} in progress...`;

  try {
    const payload = {
      target_deck: targetDeck,
      cards_to_move: cardsToMove,
      notes_to_update_example: notesToUpdate,
      words_to_add: wordsToAdd,
      dry_run: isDryRun
    };

    const res = await fetch('/api/sync-anki', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const result = await res.json();
    updatePayloadInspector(result);

    elements.syncProgressBar.style.width = '100%';

    if (result.success) {
      if (isDryRun) {
        log(`[DRY-RUN OK] Would move ${result.cards_moved} cards, update ${result.examples_updated} examples, add ${result.words_added} words.`, 'warn');
        elements.syncProgressText.textContent = `Dry Run Complete: Simulation successful.`;
      } else {
        log(`[SYNC SUCCESS] Moved ${result.cards_moved} cards, updated ${result.examples_updated} examples, added ${result.words_added} new notes to '${targetDeck}'.`, 'success');
        elements.syncProgressText.textContent = `Sync Complete! Updated Anki deck successfully.`;
        // Refresh analysis to reflect synced state
        setTimeout(() => runAnalysis(), 1000);
      }
    } else {
      log(`Sync error: ${result.error}`, 'error');
      elements.syncProgressText.textContent = `Error: ${result.error}`;
    }

  } catch (err) {
    log(`Sync call failed: ${err.message}`, 'error');
    elements.syncProgressText.textContent = `Failed: ${err.message}`;
  }
}

// 8. Debugger Actions & AI Bundle Generator
function setupDebugger() {
  elements.btnClearLogs.addEventListener('click', () => {
    elements.consoleBox.innerHTML = '';
    state.logs = [];
    log('Console cleared.', 'info');
  });

  elements.btnCopyLogs.addEventListener('click', () => {
    navigator.clipboard.writeText(state.logs.join('\n'));
    alert('Logs copied to clipboard.');
  });

  elements.btnCopyPayload.addEventListener('click', () => {
    navigator.clipboard.writeText(elements.payloadContent.textContent);
    alert('Payload JSON copied to clipboard.');
  });

  elements.btnCopyDebugBundle.addEventListener('click', () => {
    const userDescription = elements.bugDescriptionInput.value.trim() || 'No description provided';
    const timestamp = new Date().toISOString();
    
    const bundle = `### 🐞 Anki Vocab Porter - Debug Bundle
**Timestamp:** ${timestamp}
**Anki Status:** ${state.ankiStatus.connected ? `Connected (v${state.ankiStatus.version})` : 'Disconnected'}
**Target Deck:** ${elements.targetDeckInput.value}
**Active Tab:** ${state.activeTab}
**Selected File:** ${state.selectedFile ? state.selectedFile.name : 'None (Text Input)'}

#### 📝 User Issue Description / Traceback:
\`\`\`
${userDescription}
\`\`\`

#### 📊 Last Analysis Summary:
\`\`\`json
${JSON.stringify(state.analysisResult ? state.analysisResult.stats : {}, null, 2)}
\`\`\`

#### 📜 Recent System Logs:
\`\`\`
${state.logs.slice(-25).join('\n')}
\`\`\`

#### 📦 Last Anki Payload:
\`\`\`json
${JSON.stringify(state.lastPayload || {}, null, 2)}
\`\`\`
`;

    navigator.clipboard.writeText(bundle);
    log('Generated and copied AI Debug Bundle to clipboard.', 'success');
    alert('AI Debug Bundle copied! Paste it in the chat for immediate debugging.');
  });
}

// Initialize Application
window.addEventListener('DOMContentLoaded', () => {
  setupTabs();
  setupFileInput();
  setupTextInput();
  setupDebugger();

  elements.btnRefreshStatus.addEventListener('click', checkAnkiStatus);
  elements.btnAnalyze.addEventListener('click', runAnalysis);
  elements.btnDryRun.addEventListener('click', () => executeSync(true));
  elements.btnSyncAnki.addEventListener('click', () => executeSync(false));

  elements.wordSearchInput.addEventListener('input', filterAndRenderTable);
  elements.statusFilterSelect.addEventListener('change', filterAndRenderTable);

  checkAnkiStatus();
});
