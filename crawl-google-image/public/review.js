// review.js - Integrated Anki Reviewer & Image Finder

// DOM Elements
const deckSelect = document.getElementById('anki-deck');
const modelSelect = document.getElementById('anki-model');
const vocabFieldSelect = document.getElementById('anki-vocab-field');
const imageFieldSelect = document.getElementById('anki-image-field');
const googleKeyInput = document.getElementById('google-key');
const googleCxInput = document.getElementById('google-cx');

const settingsDrawer = document.getElementById('settings-drawer');
const settingsToggle = document.getElementById('settings-toggle');
const settingsClose = document.getElementById('settings-close');

const cardDisplay = document.getElementById('card-display');
const noCardsMsg = document.getElementById('no-cards-msg');
const vocabWordDisplay = document.getElementById('vocab-word-display');
const quickSearchBtn = document.getElementById('quick-search-btn');

const cardQuestion = document.getElementById('card-question');
const cardDivider = document.getElementById('card-divider');
const cardAnswer = document.getElementById('card-answer');
const showAnswerBtn = document.getElementById('show-answer-btn');
const gradingActions = document.getElementById('grading-actions');

const countNew = document.getElementById('count-new');
const countDue = document.getElementById('count-due');

// Crawler elements
const crawlerModal = document.getElementById('crawler-modal');
const crawlerIframe = document.getElementById('crawler-iframe');
const closeCrawlerBtn = document.getElementById('close-crawler-btn');

const toast = document.getElementById('toast');
const moveLaterBtn = document.getElementById('move-later-btn');
const moveOtherBtn = document.getElementById('move-other-btn');

// Global review state
let activeQueue = [];      // [{ cardId, type }] sorted by Anki due order
let currentCardIndex = -1;
let currentCardInfo = null;
let typeAnswerField = null;
let typedAnswerValue = '';
let isAnkiConnected = false;
let toastTimeout;

// Helper to display Toast
function showToast(message, duration = 3000) {
  clearTimeout(toastTimeout);
  toast.textContent = message;
  toast.classList.remove('hidden');
  if (duration > 0) {
    toastTimeout = setTimeout(() => {
      toast.classList.add('hidden');
    }, duration);
  }
}

// AnkiConnect API Proxy
async function invokeAnkiConnect(action, params = {}) {
  try {
    const response = await fetch('/api/ankiconnect', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ action, version: 6, params })
    });
    const data = await response.json();
    if (data.error) {
      throw new Error(data.error);
    }
    return data.result;
  } catch (err) {
    console.error(`AnkiConnect [${action}] error:`, err);
    throw err;
  }
}

// Check connection and load settings on boot
async function init() {
  // Bind settings drawer events
  if (settingsToggle) settingsToggle.addEventListener('click', () => toggleSettingsDrawer(true));
  settingsClose.addEventListener('click', () => toggleSettingsDrawer(false));
  
  deckSelect.addEventListener('change', () => {
    localStorage.setItem('anki_deck', deckSelect.value);
    loadReviewQueue();
  });
  
  modelSelect.addEventListener('change', async () => {
    const model = modelSelect.value;
    localStorage.setItem('anki_model', model);
    if (model) {
      await loadFieldsForModel(model);
    } else {
      vocabFieldSelect.innerHTML = '<option value="">-- Select Field --</option>';
      imageFieldSelect.innerHTML = '<option value="">-- Select Field --</option>';
    }
  });

  vocabFieldSelect.addEventListener('change', () => {
    localStorage.setItem('anki_vocab_field', vocabFieldSelect.value);
    renderActiveCard(); // Reload card representation if word field changes
  });
  imageFieldSelect.addEventListener('change', () => localStorage.setItem('anki_image_field', imageFieldSelect.value));
  
  googleKeyInput.addEventListener('input', () => localStorage.setItem('google_key', googleKeyInput.value.trim()));
  googleCxInput.addEventListener('input', () => localStorage.setItem('google_cx', googleCxInput.value.trim()));
  
  // Set saved API values
  googleKeyInput.value = localStorage.getItem('google_key') || '';
  googleCxInput.value = localStorage.getItem('google_cx') || '';

  // Anki check
  const statusBadge = document.getElementById('anki-status');
  try {
    await invokeAnkiConnect('version');
    isAnkiConnected = true;
    if (statusBadge) {
      statusBadge.textContent = 'Anki Online';
      statusBadge.className = 'badge badge-online';
    }
    
    // Populate deck lists
    await populateSettingsOptions();
    
    // Initial queue load
    await loadReviewQueue();
  } catch (err) {
    isAnkiConnected = false;
    if (statusBadge) {
      statusBadge.textContent = 'Anki Offline';
      statusBadge.className = 'badge badge-offline';
    }
    showToast("Cannot connect to Desktop Anki. Open it first!");
  }

  // Setup Review actions
  showAnswerBtn.addEventListener('click', showAnswer);
  
  document.getElementById('grade-again').addEventListener('click', () => gradeCard(1));
  document.getElementById('grade-hard').addEventListener('click', () => gradeCard(2));
  document.getElementById('grade-good').addEventListener('click', () => gradeCard(3));
  document.getElementById('grade-easy').addEventListener('click', () => gradeCard(4));
  
  if (quickSearchBtn) quickSearchBtn.addEventListener('click', openImageCrawler);
  closeCrawlerBtn.addEventListener('click', closeImageCrawler);
  if (moveLaterBtn) moveLaterBtn.addEventListener('click', () => moveCurrentCard('English::98_Later'));
  if (moveOtherBtn) moveOtherBtn.addEventListener('click', () => moveCurrentCard('English::99_Other'));

  // Browser modal
  document.getElementById('close-browser-btn').addEventListener('click', closeCardBrowser);
  document.getElementById('browser-search-btn').addEventListener('click', runBrowserSearch);
  document.getElementById('browser-search-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); runBrowserSearch(); }
    if (e.key === 'Escape') { e.preventDefault(); closeCardBrowser(); }
  });
}

// Drawer Open/Close
function toggleSettingsDrawer(open) {
  if (open) {
    settingsDrawer.classList.remove('hidden');
  } else {
    settingsDrawer.classList.add('hidden');
  }
}

// Populate decks and models
async function populateSettingsOptions() {
  try {
    const decks = await invokeAnkiConnect('deckNames');
    const models = await invokeAnkiConnect('modelNames');
    
    const savedDeck = localStorage.getItem('anki_deck');
    deckSelect.innerHTML = '<option value="">-- Select Deck --</option>';
    decks.forEach(deck => {
      const opt = document.createElement('option');
      opt.value = deck;
      opt.textContent = deck;
      if (deck === savedDeck) opt.selected = true;
      deckSelect.appendChild(opt);
    });

    const savedModel = localStorage.getItem('anki_model');
    modelSelect.innerHTML = '<option value="">-- Select Note Type --</option>';
    models.forEach(model => {
      const opt = document.createElement('option');
      opt.value = model;
      opt.textContent = model;
      if (model === savedModel) opt.selected = true;
      modelSelect.appendChild(opt);
    });

    if (savedModel) {
      await loadFieldsForModel(savedModel);
    }
  } catch (err) {
    console.error("Failed to load options from Anki:", err);
  }
}

async function loadFieldsForModel(modelName) {
  try {
    const fields = await invokeAnkiConnect('modelFieldNames', { modelName });
    const savedVocabField = localStorage.getItem('anki_vocab_field');
    const savedImageField = localStorage.getItem('anki_image_field');

    vocabFieldSelect.innerHTML = '<option value="">-- Select Field --</option>';
    imageFieldSelect.innerHTML = '<option value="">-- Select Field --</option>';

    fields.forEach(field => {
      const optVocab = document.createElement('option');
      optVocab.value = field;
      optVocab.textContent = field;
      if (field === savedVocabField) optVocab.selected = true;
      vocabFieldSelect.appendChild(optVocab);

      const optImage = document.createElement('option');
      optImage.value = field;
      optImage.textContent = field;
      if (field === savedImageField) optImage.selected = true;
      imageFieldSelect.appendChild(optImage);
    });
  } catch (err) {
    console.error("Failed to load fields:", err);
  }
}

// Load only NEW cards, shuffled randomly
async function loadReviewQueue() {
  if (!isAnkiConnected) return;
  const deck = deckSelect.value;
  if (!deck) {
    cardDisplay.classList.add('hidden');
    noCardsMsg.classList.remove('hidden');
    noCardsMsg.innerHTML = '<p>Please select a Target Deck in Settings ⚙️ to start reviews.</p>';
    return;
  }

  showToast('Loading new cards...');

  try {
    const newIds = await invokeAnkiConnect('findCards', { query: `deck:"${deck}" is:new -is:suspended` });

    if (!newIds || newIds.length === 0) {
      activeQueue = [];
      currentCardIndex = -1;
      updateStatsDisplay();
      loadActiveCard();
      return;
    }

    // Shuffle for random order
    const shuffled = [...newIds].sort(() => Math.random() - 0.5);
    activeQueue = shuffled.map(id => ({ cardId: id, type: 'new' }));
    currentCardIndex = 0;

    updateStatsDisplay();
    loadActiveCard();
  } catch (err) {
    showToast(`Failed loading queue: ${err.message}`);
  }
}

function updateStatsDisplay() {
  if (countDue) countDue.textContent = 0;
  if (countNew) countNew.textContent = activeQueue.length;
}

// Load details of the current card from our local queue
async function loadActiveCard() {
  if (currentCardIndex === -1 || activeQueue.length === 0) {
    cardDisplay.classList.add('hidden');
    noCardsMsg.classList.remove('hidden');
    noCardsMsg.innerHTML = '<p>No cards due today! 🎉</p>';
    currentCardInfo = null;
    return;
  }

  cardDisplay.classList.remove('hidden');
  noCardsMsg.classList.add('hidden');

  try {
    const { cardId } = activeQueue[currentCardIndex];
    const info = await invokeAnkiConnect('cardsInfo', { cards: [cardId] });
    if (info && info.length > 0 && info[0].fields) {
      currentCardInfo = info[0];
      renderActiveCard();
    } else {
      // Card vanished (deleted/suspended externally) — skip it
      activeQueue.splice(currentCardIndex, 1);
      if (currentCardIndex >= activeQueue.length) currentCardIndex = Math.max(0, activeQueue.length - 1);
      loadActiveCard();
    }
  } catch (err) {
    showToast(`Error loading card: ${err.message}`);
  }
}

// Process Anki HTML media paths to absolute URLs served by Express media proxy
// Replace "[sound:filename.mp3]" with HTML5 audio tags for auto playback
function preprocessAnkiHtml(html) {
  if (!html) return '';
  
  let processed = html.replace(/(?:\[\[|\{\{)type:([^\]}]+)(?:\]\]|\}\})/g, (match, fieldName) => {
    typeAnswerField = fieldName.trim();
    return `<input type="text" id="type-answer-input" class="type-answer-input" autocomplete="off" placeholder="Type answer and press Enter...">`;
  });

  processed = processed.replace(/src="([^"]+)"/g, (match, src) => {
    if (!src.startsWith('http') && !src.startsWith('data:')) {
      return `src="/media/${encodeURIComponent(src)}"`;
    }
    return match;
  });

  processed = processed.replace(/\[sound:([^\]]+)\]/g, (match, filename) => {
    return `<audio src="/media/${encodeURIComponent(filename)}" autoplay controls style="margin: 8px 0; display: inline-block;"></audio>`;
  });

  return processed;
}

function preprocessAnkiAnswerHtml(html) {
  if (!html) return '';
  
  let processed = html;
  
  if (typeAnswerField) {
    const correctValue = (currentCardInfo && currentCardInfo.fields[typeAnswerField] ? currentCardInfo.fields[typeAnswerField].value : '').trim();
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = correctValue;
    const cleanCorrectVal = tempDiv.textContent.trim();

    let diffHtml;
    if (typedAnswerValue.toLowerCase() === cleanCorrectVal.toLowerCase()) {
      diffHtml = `<span style="color:#2dce89;font-weight:600">${typedAnswerValue}</span>`;
    } else {
      diffHtml = `<span style="color:#f5365c;text-decoration:line-through;font-weight:600">${typedAnswerValue || '[empty]'}</span> → <span style="color:#2dce89;font-weight:600">${cleanCorrectVal}</span>`;
    }

    let hasPlaceholder = false;
    processed = processed.replace(/(?:\[\[|\{\{)type:([^\]}]+)(?:\]\]|\}\})/g, () => {
      hasPlaceholder = true;
      return diffHtml;
    });

    if (!hasPlaceholder) {
      processed = diffHtml + processed;
    }
  }
  
  return preprocessAnkiHtml(processed);
}

// Extract word for search
function getVocabWord() {
  if (!currentCardInfo || !currentCardInfo.fields) return '';
  const vocabField = vocabFieldSelect.value || localStorage.getItem('anki_vocab_field') || 'Front';
  
  if (currentCardInfo.fields[vocabField]) {
    const rawVal = currentCardInfo.fields[vocabField].value;
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = rawVal;
    return tempDiv.textContent.trim();
  }
  
  const firstFieldName = Object.keys(currentCardInfo.fields)[0];
  if (firstFieldName && currentCardInfo.fields[firstFieldName]) {
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = currentCardInfo.fields[firstFieldName].value;
    return tempDiv.textContent.trim();
  }
  
  return '';
}

// Render active card content in UI
function renderActiveCard() {
  if (!currentCardInfo) return;

  typeAnswerField = null;
  typedAnswerValue = '';

  const qHtml = preprocessAnkiHtml(currentCardInfo.question);
  cardQuestion.innerHTML = qHtml;
  cardQuestion.classList.remove('hidden');
  
  cardAnswer.innerHTML = '';
  cardAnswer.classList.add('hidden');
  cardDivider.classList.add('hidden');
  
  showAnswerBtn.classList.remove('hidden');
  gradingActions.classList.add('hidden');
  
  const word = getVocabWord();
  if (vocabWordDisplay) vocabWordDisplay.textContent = word || 'No word found';
  
  if (!crawlerModal.classList.contains('hidden') && word) {
    crawlerIframe.src = `/index.html?q=${encodeURIComponent(word)}`;
    setTimeout(() => {
      try {
        crawlerIframe.focus();
      } catch(e) {}
    }, 150);
  }

  const typeInput = document.getElementById('type-answer-input');
  if (typeInput) {
    typeInput.focus();
    typeInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        typedAnswerValue = typeInput.value.trim();
        showAnswer();
      }
    });
  }
}

// Show card answer
function showAnswer() {
  if (!currentCardInfo) return;
  
  const typeInput = document.getElementById('type-answer-input');
  if (typeInput && !typedAnswerValue) {
    typedAnswerValue = typeInput.value.trim();
  }

  const aHtml = preprocessAnkiAnswerHtml(currentCardInfo.answer);
  cardAnswer.innerHTML = aHtml;
  
  cardQuestion.classList.add('hidden');
  cardAnswer.classList.remove('hidden');
  cardDivider.classList.add('hidden');
  
  showAnswerBtn.classList.add('hidden');
  gradingActions.classList.remove('hidden');
}

// Show small ✔/✖ icon at top-right after grading
function showFeedbackFlash(ease) {
  const icon = ease >= 3 ? '✔' : '✖';
  const color = ease >= 3 ? '#2dce89' : '#f5365c';
  // Remove any existing
  const existing = document.querySelector('.feedback-flash');
  if (existing) existing.remove();
  const el = document.createElement('div');
  el.className = 'feedback-flash';
  el.textContent = icon;
  el.style.color = color;
  document.body.appendChild(el);
  setTimeout(() => { el.classList.add('fade-out'); }, 800);
  setTimeout(() => el.remove(), 1100);
}

// Grade card and advance queue
async function gradeCard(ease) {
  if (!currentCardInfo || currentCardIndex === -1) return;

  const cardId = activeQueue[currentCardIndex].cardId;
  showFeedbackFlash(ease);

  try {
    await invokeAnkiConnect('answerCards', { answers: [{ cardId, ease }] });

    const cardData = activeQueue[currentCardIndex];
    activeQueue.splice(currentCardIndex, 1);

    // Ease 1 (Again) — re-queue at end so user sees it again this session
    if (ease === 1) activeQueue.push(cardData);

    if (currentCardIndex >= activeQueue.length) currentCardIndex = 0;
    updateStatsDisplay();
    loadActiveCard();
  } catch (err) {
    showToast(`Error answering card: ${err.message}`);
  }
}

async function buryCurrentCard() {
  if (!currentCardInfo) return;
  const cardId = currentCardInfo.cardId;
  try {
    await invokeAnkiConnect('suspend', { cards: [cardId] });
    showToast('Card suspended');
    activeQueue.splice(currentCardIndex, 1);
    if (currentCardIndex >= activeQueue.length) currentCardIndex = 0;
    updateStatsDisplay();
    loadActiveCard();
  } catch (err) {
    showToast(`Error suspending card: ${err.message}`);
  }
}


async function moveCurrentCard(targetDeck) {
  if (!currentCardInfo) {
    showToast('No active card to move!');
    return;
  }

  const cardId = currentCardInfo.cardId;
  const word = getVocabWord();

  const confirmMove = confirm(`Are you sure you want to move "${word}" to deck "${targetDeck}"?`);
  if (!confirmMove) return;

  try {
    await invokeAnkiConnect('createDeck', { deck: targetDeck });
    await invokeAnkiConnect('changeDeck', { cards: [cardId], deck: targetDeck });
    showToast(`Moved "${word}" to "${targetDeck}"! 🎉`);
    activeQueue.splice(currentCardIndex, 1);
    if (currentCardIndex >= activeQueue.length) currentCardIndex = 0;
    updateStatsDisplay();
    loadActiveCard();
  } catch (err) {
    showToast(`Error moving card: ${err.message || err}`);
  }
}

function openImageCrawler() {
  const word = getVocabWord();
  if (!word) {
    showToast("No vocabulary word found to search images for.");
    return;
  }
  
  crawlerIframe.src = `/index.html?q=${encodeURIComponent(word)}`;
  crawlerModal.classList.remove('hidden');
  
  setTimeout(() => {
    try {
      crawlerIframe.focus();
    } catch(e) {}
  }, 150);
}

function closeImageCrawler() {
  crawlerModal.classList.add('hidden');
  crawlerIframe.src = '';
  window.focus();
}

// Convert image from url (via proxy) to base64
function fetchAndConvertToBase64(url, fallbackUrl = null) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.src = url;

    img.onload = () => {
      try {
        const canvas = document.createElement('canvas');
        canvas.width = img.naturalWidth;
        canvas.height = img.naturalHeight;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0);
        const dataUrl = canvas.toDataURL('image/png');
        resolve(dataUrl.split(',')[1]); // raw base64
      } catch (e) {
        if (fallbackUrl) {
          console.log("Fallback base64 conversion...");
          fetchAndConvertToBase64(`/api/proxy?url=${encodeURIComponent(fallbackUrl)}`, null)
            .then(resolve)
            .catch(reject);
        } else {
          reject(e);
        }
      }
    };

    img.onerror = () => {
      if (fallbackUrl) {
        console.log("Fallback base64 conversion...");
        fetchAndConvertToBase64(`/api/proxy?url=${encodeURIComponent(fallbackUrl)}`, null)
          .then(resolve)
          .catch(reject);
      } else {
        reject(new Error("Failed to load image"));
      }
    };
  });
}

// Link clicked image to current active card note
async function linkImageToCurrentCard(imgObj, cardElement = null) {
  if (!currentCardInfo) {
    showToast("No active card to link image to!");
    return;
  }
  
  const noteId = currentCardInfo.note;
  const cardId = currentCardInfo.cardId;
  const imageField = imageFieldSelect.value || localStorage.getItem('anki_image_field');
  const word = getVocabWord();

  if (!imageField) {
    showToast("Please configure Target Image Field in settings ⚙️");
    toggleSettingsDrawer(true);
    return;
  }

  // Visual feedback: add syncing class
  if (cardElement) cardElement.classList.add('syncing');
  showToast(`Uploading image to Anki for "${word}"...`);

  try {
    const proxyUrl = `/api/proxy?url=${encodeURIComponent(imgObj.url)}`;
    const base64Data = await fetchAndConvertToBase64(proxyUrl, imgObj.thumb);

    const safeWord = word.replace(/[^a-zA-Z0-9]/g, '_');
    const filename = `vocab_finder_${Date.now()}_${safeWord}.png`;
    
    // Store media file in Anki
    await invokeAnkiConnect('storeMediaFile', {
      filename,
      data: base64Data
    });

    // Update note field with the image tag
    await invokeAnkiConnect('updateNoteFields', {
      note: {
        id: noteId,
        fields: {
          [imageField]: `<img src="${filename}">`
        }
      }
    });

    if (cardElement) cardElement.classList.remove('syncing');
    showToast(`Linked image to "${word}" successfully! 🎉`);
    closeImageCrawler();

    // Refresh active card via cardsInfo (consistent with queue-based approach)
    const refreshed = await invokeAnkiConnect('cardsInfo', { cards: [cardId] });
    if (refreshed && refreshed.length > 0 && refreshed[0].fields) {
      currentCardInfo = refreshed[0];
      renderActiveCard();
      // If answer was already visible, keep it shown
      if (!gradingActions.classList.contains('hidden')) {
        showAnswer();
      }
    }
  } catch (err) {
    if (cardElement) cardElement.classList.remove('syncing');
    console.error(err);
    showToast(`Sync failed: ${err.message || err}`);
  }
}

// Keyboard shortcuts handlers
document.addEventListener('keydown', (e) => {
  const activeElement = document.activeElement;
  const isTyping = activeElement.tagName === 'INPUT' || activeElement.tagName === 'SELECT' || activeElement.tagName === 'TEXTAREA';

  if (isTyping) {
    // If pressing ESC in search box, blur it
    if (e.key === 'Escape') {
      activeElement.blur();
    }
    return;
  }

  // Open settings
  if (e.key === ',') {
    e.preventDefault();
    toggleSettingsDrawer(true);
    return;
  }

  // Escape closes drawer + modals
  if (e.key === 'Escape') {
    e.preventDefault();
    toggleSettingsDrawer(false);
    crawlerModal.classList.add('hidden');
    closeCardBrowser();
    return;
  }
  // Space / Enter: show answer
  if (e.key === ' ' || e.key === 'Enter') {
    e.preventDefault();
    if (!showAnswerBtn.classList.contains('hidden')) {
      showAnswer();
    }
    return;
  }

  // Grading card (1, 2, 3, 4)
  if (!gradingActions.classList.contains('hidden')) {
    if (e.key === '1') {
      e.preventDefault();
      gradeCard(1);
      return;
    } else if (e.key === '2') {
      e.preventDefault();
      gradeCard(2);
      return;
    } else if (e.key === '3') {
      e.preventDefault();
      gradeCard(3);
      return;
    } else if (e.key === '4') {
      e.preventDefault();
      gradeCard(4);
      return;
    }
  }

  // Find image keyboard trigger (f or s keys)
  if (e.key === 'f' || e.key === 'F' || e.key === 's' || e.key === 'S') {
    e.preventDefault();
    openImageCrawler();
    return;
  }

  // Move card shortcuts
  if (e.key === 'n' || e.key === 'N') {
    e.preventDefault();
    moveCurrentCard('English::01_Name');
    return;
  }
  if (e.key === 'l' || e.key === 'L') {
    e.preventDefault();
    moveCurrentCard('English::98_Later');
    return;
  }
  if (e.key === 'o' || e.key === 'O') {
    e.preventDefault();
    moveCurrentCard('English::99_Other');
    return;
  }
  // = : suspend/bury card
  if (e.key === '=') {
    e.preventDefault();
    buryCurrentCard();
    return;
  }
  // B : open Anki card browser with search prompt
  if (e.key === 'b' || e.key === 'B') {
    e.preventDefault();
    openCardBrowser();
    return;
  }
  });

async function openCardBrowser() {
  const currentWord = getVocabWord();
  const modal = document.getElementById('browser-modal');
  const input = document.getElementById('browser-search-input');
  const tbody = document.getElementById('browser-tbody');
  const empty = document.getElementById('browser-empty');
  const status = document.getElementById('browser-status');

  // Reset state
  tbody.innerHTML = '';
  empty.classList.add('hidden');
  status.classList.add('hidden');
  input.value = currentWord;

  modal.classList.remove('hidden');
  setTimeout(() => { input.focus(); input.select(); }, 80);

  // Auto-search on open
  if (currentWord) runBrowserSearch();
}

function closeCardBrowser() {
  document.getElementById('browser-modal').classList.add('hidden');
}

async function runBrowserSearch() {
  const input = document.getElementById('browser-search-input');
  const tbody = document.getElementById('browser-tbody');
  const empty = document.getElementById('browser-empty');
  const status = document.getElementById('browser-status');
  const query = input.value.trim();
  if (!query) return;

  tbody.innerHTML = '';
  empty.classList.add('hidden');
  status.textContent = 'Searching...';
  status.classList.remove('hidden');

  try {
    const noteIds = await invokeAnkiConnect('findNotes', { query });

    if (!noteIds || noteIds.length === 0) {
      status.classList.add('hidden');
      empty.classList.remove('hidden');
      return;
    }

    status.textContent = `Loading ${noteIds.length} card(s)...`;

    // Batch fetch note info
    const notes = await invokeAnkiConnect('notesInfo', { notes: noteIds });

    // Fetch card types for status badge
    const allCardIds = notes.flatMap(n => n.cards || []);
    let cardTypeMap = {};
    if (allCardIds.length > 0) {
      const cardsData = await invokeAnkiConnect('cardsInfo', { cards: allCardIds });
      cardsData.forEach(c => { cardTypeMap[c.cardId] = c.type; });
    }

    const vocabField  = vocabFieldSelect.value  || localStorage.getItem('anki_vocab_field')  || 'Word';
    const meaningField = localStorage.getItem('anki_meaning_field') || 'Reference';

    notes.forEach(note => {
      const word    = stripHtml(note.fields[vocabField]?.value   || Object.values(note.fields)[0]?.value || '');
      const meaning = stripHtml(note.fields[meaningField]?.value || Object.values(note.fields)[1]?.value || '');
      const deck    = note.cards?.length ? (note.deckName || '—') : '—';

      // Determine card status from first card
      const firstCardType = note.cards?.length ? cardTypeMap[note.cards[0]] : undefined;
      let badgeClass = 'new', badgeLabel = 'New';
      if (firstCardType === 1)      { badgeClass = 'review'; badgeLabel = 'Learn'; }
      else if (firstCardType === 2) { badgeClass = 'due';    badgeLabel = 'Review'; }
      else if (firstCardType === 3) { badgeClass = 'due';    badgeLabel = 'Due'; }

      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td title="${word}">${word}</td>
        <td title="${meaning}">${meaning || '<span style="opacity:0.4">—</span>'}</td>
        <td title="${deck}" style="color:var(--text-muted);font-size:11px">${deck}</td>
        <td><span class="browser-badge ${badgeClass}">${badgeLabel}</span></td>
      `;
      tbody.appendChild(tr);
    });

    status.textContent = `${notes.length} result${notes.length !== 1 ? 's' : ''} for "${query}"`;
  } catch (err) {
    status.textContent = `Error: ${err.message}`;
  }
}

function stripHtml(html) {
  const d = document.createElement('div');
  d.innerHTML = html;
  return d.textContent.trim();
}

// Run
window.addEventListener('DOMContentLoaded', init);
