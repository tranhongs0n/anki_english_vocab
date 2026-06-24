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

// Global review state
let dueQueue = []; // array of { cardId, type: 'due' }
let newQueue = []; // array of { cardId, type: 'new' }
let activeQueue = []; // merged queue of current session
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
  settingsToggle.addEventListener('click', () => toggleSettingsDrawer(true));
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
    statusBadge.textContent = 'Anki Online';
    statusBadge.className = 'badge badge-online';
    
    // Populate deck lists
    await populateSettingsOptions();
    
    // Initial queue load
    await loadReviewQueue();
  } catch (err) {
    isAnkiConnected = false;
    statusBadge.textContent = 'Anki Offline';
    statusBadge.className = 'badge badge-offline';
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

// Load current review cards list
async function loadReviewQueue() {
  if (!isAnkiConnected) return;
  const deck = deckSelect.value;
  if (!deck) {
    cardDisplay.classList.add('hidden');
    noCardsMsg.classList.remove('hidden');
    noCardsMsg.innerHTML = '<p>Please select a Target Deck in Settings ⚙️ to start reviews.</p>';
    return;
  }

  showToast("Loading cards...");

  try {
    // Fetch due and new card IDs
    const dueIds = await invokeAnkiConnect('findCards', { query: `deck:"${deck}" is:due -is:suspended` });
    const newIds = await invokeAnkiConnect('findCards', { query: `deck:"${deck}" is:new -is:suspended` });

    dueQueue = dueIds.map(id => ({ cardId: id, type: 'due' }));
    newQueue = newIds.map(id => ({ cardId: id, type: 'new' }));
    
    // Sort and interleave: show all dues first, then news.
    // In Anki, cards are usually served in order.
    activeQueue = [...dueQueue, ...newQueue];
    currentCardIndex = activeQueue.length > 0 ? 0 : -1;
    
    updateStatsDisplay();
    loadActiveCard();
  } catch (err) {
    showToast(`Failed loading queue: ${err.message}`);
  }
}

function updateStatsDisplay() {
  const dues = activeQueue.filter(c => c.type === 'due').length;
  const news = activeQueue.filter(c => c.type === 'new').length;
  countDue.textContent = dues;
  countNew.textContent = news;
}

// Load details of current active card
async function loadActiveCard() {
  if (currentCardIndex === -1 || activeQueue.length === 0) {
    cardDisplay.classList.add('hidden');
    noCardsMsg.classList.remove('hidden');
    noCardsMsg.innerHTML = '<p>No cards due today! Select another deck or enjoy your day. 🎉</p>';
    currentCardInfo = null;
    return;
  }

  cardDisplay.classList.remove('hidden');
  noCardsMsg.classList.add('hidden');

  try {
    const cardData = activeQueue[currentCardIndex];
    const info = await invokeAnkiConnect('cardsInfo', { cards: [cardData.cardId] });
    
    if (info && info.length > 0 && info[0].fields) {
      currentCardInfo = info[0];
      renderActiveCard();
    } else {
      activeQueue.splice(currentCardIndex, 1);
      if (activeQueue.length > 0) {
        if (currentCardIndex >= activeQueue.length) {
          currentCardIndex = 0;
        }
        loadActiveCard();
      } else {
        currentCardIndex = -1;
        loadActiveCard();
      }
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
    
    let diffHtml = '';
    if (typedAnswerValue.toLowerCase() === cleanCorrectVal.toLowerCase()) {
      diffHtml = `<div class="type-compare-box correct"><span class="type-label">Typed:</span> <span class="type-val-correct">${typedAnswerValue}</span> (Correct!)</div>`;
    } else {
      diffHtml = `<div class="type-compare-box incorrect"><span class="type-label">Typed:</span> <span class="type-val-incorrect">${typedAnswerValue || '[empty]'}</span> &rarr; <span class="type-val-correct">${cleanCorrectVal}</span></div>`;
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

// Answer card grading and advance
async function gradeCard(ease) {
  if (!currentCardInfo || currentCardIndex === -1 || !activeQueue[currentCardIndex]) return;
  
  const cardId = activeQueue[currentCardIndex].cardId;
  const word = getVocabWord();
  
  try {
    // Call answerCards
    await invokeAnkiConnect('answerCards', {
      answers: [{ cardId, ease }]
    });
    
    // Remove from active queue
    const cardData = activeQueue[currentCardIndex];
    activeQueue.splice(currentCardIndex, 1);
    
    // If user failed the card (Again), push to the end of review queue so they see it again this session
    if (ease === 1) {
      activeQueue.push(cardData);
      showToast(`Review failed. Word "${word}" sent to back of queue.`);
    } else {
      showToast(`Card answered!`);
    }
    
    updateStatsDisplay();
    
    // Load next card
    if (activeQueue.length > 0) {
      // Don't increment index, because we removed the element at current index (it shifted left)
      if (currentCardIndex >= activeQueue.length) {
        currentCardIndex = 0;
      }
      loadActiveCard();
    } else {
      currentCardIndex = -1;
      loadActiveCard();
    }
  } catch (err) {
    showToast(`Error answering card: ${err.message}`);
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

    // Refresh active card immediately to show the newly linked image
    const updatedInfo = await invokeAnkiConnect('cardsInfo', { cards: [currentCardInfo.cardId] });
    if (updatedInfo && updatedInfo.length > 0) {
      currentCardInfo = updatedInfo[0];
      renderActiveCard();
      
      // If answer was shown when we linked the image, keep answer shown
      if (gradingActions.classList.contains('hidden') === false) {
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

  // Escape closes drawer
  if (e.key === 'Escape') {
    e.preventDefault();
    toggleSettingsDrawer(false);
    crawlerModal.classList.add('hidden');
    return;
  }

  // Spacebar to show answer
  if (e.key === ' ' || e.key === 'Enter') {
    e.preventDefault();
    if (showAnswerBtn.classList.contains('hidden')) {
      // Already showing answer, do nothing (user must press 1-4)
    } else {
      showAnswer();
    }
    return;
  }

  // Grading card (1, 2, 3, 4)
  if (!gradingActions.classList.contains('hidden')) {
    if (e.key === '1') {
      e.preventDefault();
      gradeCard(1);
    } else if (e.key === '2') {
      e.preventDefault();
      gradeCard(2);
    } else if (e.key === '3') {
      e.preventDefault();
      gradeCard(3);
    } else if (e.key === '4') {
      e.preventDefault();
      gradeCard(4);
    }
    return;
  }

  // Find image keyboard trigger (f or s keys)
  if (e.key === 'f' || e.key === 'F' || e.key === 's' || e.key === 'S') {
    e.preventDefault();
    openImageCrawler();
    return;
  }
});

// Run
window.addEventListener('DOMContentLoaded', init);
