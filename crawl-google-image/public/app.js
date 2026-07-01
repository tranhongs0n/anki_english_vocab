const searchInput = document.getElementById('search-input');
const imageGrid = document.getElementById('image-grid');
const loading = document.getElementById('loading');
const infoMessage = document.getElementById('info-message');
const toast = document.getElementById('toast');

// Modal DOM references
const promptModal = document.getElementById('prompt-modal');
const modalImagePreview = document.getElementById('modal-image-preview');
const modalVocabInput = document.getElementById('modal-vocab-input');
const modalStatus = document.getElementById('modal-status');
const modalConfirmBtn = document.getElementById('modal-confirm-btn');
const modalCancelBtn = document.getElementById('modal-cancel-btn');
const modalCloseBtn = document.getElementById('modal-close');

let images = [];
let selectedIndex = -1;
let toastTimeout;

// Reviewer iframe integration helpers
function isReviewerIframe() {
  return window.parent && typeof window.parent.linkImageToCurrentCard === 'function';
}

function linkImageIfIframe(index) {
  if (isReviewerIframe() && index >= 0 && index < images.length) {
    window.parent.linkImageToCurrentCard(images[index]);
    return true;
  }
  return false;
}

// Toast Notification helper
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

function hideToast() {
  toast.classList.add('hidden');
}

// Expose a function to search from parent window
window.triggerSearch = function(query) {
  if (searchInput) {
    searchInput.value = query;
    performSearch();
  }
};

// Perform Image Search
async function performSearch() {
  const query = searchInput.value.trim();
  if (!query) return;

  // Show loading
  loading.classList.remove('hidden');
  infoMessage.classList.add('hidden');
  imageGrid.innerHTML = '';
  images = [];
  selectedIndex = -1;

  try {
    const quickMode = localStorage.getItem('quick_search') !== 'false';
    const response = await fetch(`/api/search?q=${encodeURIComponent(query)}&quick=${quickMode}`);
    const data = await response.json();

    loading.classList.add('hidden');

    if (data.results && data.results.length > 0) {
      images = data.results;
      renderGrid();
      // Select first image automatically
      selectImage(0);
      searchInput.blur(); // Blur search so keyboard controls navigate cards
    } else {
      infoMessage.textContent = 'No images found. Try another term.';
      infoMessage.classList.remove('hidden');
    }
  } catch (err) {
    console.error(err);
    loading.classList.add('hidden');
    infoMessage.textContent = 'Error fetching images. Please try again.';
    infoMessage.classList.remove('hidden');
  }
}

// Render the grid of images
function renderGrid() {
  images.forEach((img, idx) => {
    const card = document.createElement('div');
    card.className = 'image-card';
    card.dataset.index = idx;

    const imageEl = document.createElement('img');
    imageEl.src = img.thumb;
    imageEl.alt = img.title;
    imageEl.loading = 'lazy';

    card.appendChild(imageEl);

    // Mouse selection / copy
    card.addEventListener('click', () => {
      selectImage(idx);
    });
    
    card.addEventListener('dblclick', () => {
      if (linkImageIfIframe(idx)) {
        return;
      }
      triggerCopy(idx);
    });

    imageGrid.appendChild(card);
  });
}

// Select an image by index
function selectImage(index) {
  if (images.length === 0) return;

  // Clamp index
  if (index < 0) index = 0;
  if (index >= images.length) index = images.length - 1;

  // Remove previous selection
  const previousSelected = document.querySelector('.image-card.selected');
  if (previousSelected) {
    previousSelected.classList.remove('selected');
  }

  selectedIndex = index;
  const currentSelected = document.querySelector(`.image-card[data-index="${selectedIndex}"]`);
  if (currentSelected) {
    currentSelected.classList.add('selected');
    currentSelected.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
}

// Copy selected image
async function triggerCopy(index) {
  if (index < 0 || index >= images.length) return;
  const targetImage = images[index];
  
  showToast("Downloading and converting image...", 0); // Keep open
  copyImageByUrl(targetImage.url, targetImage.thumb, "Original failed. Copying thumbnail...");
}

// Copy helper with automatic fallback
async function copyImageByUrl(srcUrl, fallbackUrl = null, fallbackMessage = "") {
  try {
    const proxyUrl = `/api/proxy?url=${encodeURIComponent(srcUrl)}`;
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.src = proxyUrl;

    img.onload = () => {
      try {
        let w = img.naturalWidth;
        let h = img.naturalHeight;
        const maxDim = 600;
        if (w > maxDim || h > maxDim) {
          if (w > h) { h = Math.round(h * (maxDim / w)); w = maxDim; }
          else { w = Math.round(w * (maxDim / h)); h = maxDim; }
        }
        
        const canvas = document.createElement('canvas');
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0, w, h);

        canvas.toBlob(async (blob) => {
          if (!blob) {
            if (fallbackUrl) {
              showToast(fallbackMessage, 0);
              copyImageByUrl(fallbackUrl);
            } else {
              showToast("Failed to process image format.");
            }
            return;
          }
          try {
            await navigator.clipboard.write([
              new ClipboardItem({ 'image/png': blob })
            ]);
            showToast(fallbackUrl ? "Original image copied!" : "Thumbnail copied!");
          } catch (err) {
            console.error(err);
            showToast("Failed to copy: Clipboard write blocked. Try clicking the app first.");
          }
        }, 'image/png');
      } catch (err) {
        console.error(err);
        if (fallbackUrl) {
          showToast(fallbackMessage, 0);
          copyImageByUrl(fallbackUrl);
        } else {
          showToast("Error processing image on canvas.");
        }
      }
    };

    img.onerror = () => {
      if (fallbackUrl) {
        showToast(fallbackMessage, 0);
        copyImageByUrl(fallbackUrl);
      } else {
        showToast("Failed to download image.");
      }
    };

  } catch (err) {
    console.error(err);
    if (fallbackUrl) {
      showToast(fallbackMessage, 0);
      copyImageByUrl(fallbackUrl);
    } else {
      showToast("Failed to retrieve image through proxy.");
    }
  }
}

// Drawer open/close helper
function toggleSettingsDrawer(forceOpen = null) {
  const drawer = document.getElementById('settings-drawer');
  const isOpen = drawer.classList.contains('open');
  const shouldOpen = forceOpen !== null ? forceOpen : !isOpen;
  
  if (shouldOpen) {
    drawer.classList.add('open');
    drawer.classList.remove('hidden');
    // Focus the first setting select
    document.getElementById('anki-deck').focus();
  } else {
    drawer.classList.remove('open');
    // Hide after transition
    setTimeout(() => {
      if (!drawer.classList.contains('open')) {
        drawer.classList.add('hidden');
      }
    }, 300);
  }
}

let isAnkiConnected = false;

// AnkiConnect API caller
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
    console.error("AnkiConnect error:", err);
    throw err;
  }
}

// Check if Anki is online
async function checkAnkiStatus() {
  const statusBadge = document.getElementById('anki-status');
  try {
    await invokeAnkiConnect('version');
    isAnkiConnected = true;
    statusBadge.textContent = 'Anki Connected';
    statusBadge.className = 'badge badge-online';
    await loadAnkiSettingsOptions();
  } catch (err) {
    isAnkiConnected = false;
    statusBadge.textContent = 'Anki Offline';
    statusBadge.className = 'badge badge-offline';
  }

  // Check URL params for search query
  const urlParams = new URLSearchParams(window.location.search);
  const query = urlParams.get('q') || urlParams.get('vocab');
  if (query) {
    searchInput.value = query;
    performSearch();
  }

  // If running inside reviewer iframe, add class and hide navigation link
  if (isReviewerIframe()) {
    document.body.classList.add('is-iframe');
    const navLink = document.querySelector('.nav-link');
    if (navLink) navLink.style.display = 'none';
  }
}

// Load choices into dropdown selectors
const deckSelect = document.getElementById('anki-deck');
const modelSelect = document.getElementById('anki-model');
const vocabFieldSelect = document.getElementById('anki-vocab-field');
const imageFieldSelect = document.getElementById('anki-image-field');

const quickSearchCheckbox = document.getElementById('quick-search');

if (quickSearchCheckbox) {
  const saved = localStorage.getItem('quick_search');
  quickSearchCheckbox.checked = saved !== 'false'; // defaults to true
  quickSearchCheckbox.addEventListener('change', () => {
    localStorage.setItem('quick_search', quickSearchCheckbox.checked);
  });
}

async function loadAnkiSettingsOptions() {
  try {
    const decks = await invokeAnkiConnect('deckNames');
    const models = await invokeAnkiConnect('modelNames');
    
    // Populate Decks
    const savedDeck = localStorage.getItem('anki_deck');
    deckSelect.innerHTML = '<option value="">-- Select Deck --</option>';
    decks.forEach(deck => {
      const opt = document.createElement('option');
      opt.value = deck;
      opt.textContent = deck;
      if (deck === savedDeck) opt.selected = true;
      deckSelect.appendChild(opt);
    });

    // Populate Models
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

// Convert image to base64 via canvas with fallback
function fetchAndConvertToBase64(url, fallbackUrl = null) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.src = url;

    img.onload = () => {
      try {
        let w = img.naturalWidth;
        let h = img.naturalHeight;
        const maxDim = 600;
        if (w > maxDim || h > maxDim) {
          if (w > h) { h = Math.round(h * (maxDim / w)); w = maxDim; }
          else { w = Math.round(w * (maxDim / h)); h = maxDim; }
        }
        
        const canvas = document.createElement('canvas');
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0, w, h);
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

// Add directly to Anki
async function addNoteToAnki(index) {
  if (!isAnkiConnected) {
    showToast("Anki is offline. Please open Anki first!");
    return;
  }

  const deck = deckSelect.value;
  const model = modelSelect.value;
  const vocabField = vocabFieldSelect.value;
  const imageField = imageFieldSelect.value;
  const vocabWord = searchInput.value.trim();

  if (!deck || !model || !vocabField || !imageField || !vocabWord) {
    showToast("Please configure Anki settings first!");
    toggleSettingsDrawer(true);
    return;
  }

  if (index < 0 || index >= images.length) return;
  const targetImage = images[index];

  showToast(`Syncing "${vocabWord}" to Anki...`, 0);

  try {
    const proxyUrl = `/api/proxy?url=${encodeURIComponent(targetImage.url)}`;
    const base64Data = await fetchAndConvertToBase64(proxyUrl, targetImage.thumb);

    const safeWord = vocabWord.replace(/[^a-zA-Z0-9]/g, '_');
    const filename = `vocab_finder_${Date.now()}_${safeWord}.png`;
    
    // Store image
    await invokeAnkiConnect('storeMediaFile', {
      filename,
      data: base64Data
    });

    // Add note
    await invokeAnkiConnect('addNote', {
      note: {
        deckName: deck,
        modelName: model,
        fields: {
          [vocabField]: vocabWord,
          [imageField]: `<img src="${filename}">`
        },
        tags: ["vocab_image_finder"]
      }
    });

    showToast(`Added "${vocabWord}" to Anki! 🎉`);
  } catch (err) {
    console.error("Sync failed:", err);
    showToast(`Failed: ${err.message || err}`);
  }
}

// UI Event Listeners for settings
document.getElementById('settings-toggle').addEventListener('click', () => toggleSettingsDrawer());
document.getElementById('settings-close').addEventListener('click', () => toggleSettingsDrawer(false));

deckSelect.addEventListener('change', () => localStorage.setItem('anki_deck', deckSelect.value));
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
vocabFieldSelect.addEventListener('change', () => localStorage.setItem('anki_vocab_field', vocabFieldSelect.value));
imageFieldSelect.addEventListener('change', () => localStorage.setItem('anki_image_field', imageFieldSelect.value));
// Modal Functions
function showPromptModal(index) {
  if (index < 0 || index >= images.length) return;
  const targetImage = images[index];
  
  modalImagePreview.src = targetImage.thumb;
  modalVocabInput.value = searchInput.value.trim(); // pre-fill with current search term
  modalStatus.className = 'modal-status hidden';
  modalStatus.textContent = '';
  
  promptModal.classList.remove('hidden');
  setTimeout(() => modalVocabInput.focus(), 50);
}

function hidePromptModal() {
  promptModal.classList.add('hidden');
  modalVocabInput.blur();
}

function setModalStatus(msg, type) {
  modalStatus.textContent = msg;
  modalStatus.className = `modal-status ${type}`;
}

async function linkImageToAnkiCard() {
  const deck = deckSelect.value;
  const model = modelSelect.value;
  const vocabField = vocabFieldSelect.value;
  const imageField = imageFieldSelect.value;
  const vocabWord = modalVocabInput.value.trim();

  if (!deck || !model || !vocabField || !imageField || !vocabWord) {
    setModalStatus("Please configure Anki settings (deck, note type, fields) first!", "error");
    return;
  }

  setModalStatus("Searching card in Anki...", "info");

  try {
    // Search broadly for notes containing the word text inside the deck & model type
    const query = `deck:"${deck}" note:"${model}" "${vocabWord}"`;
    const noteIds = await invokeAnkiConnect('findNotes', { query });

    if (!noteIds || noteIds.length === 0) {
      setModalStatus(`No matching card found for "${vocabWord}" in deck "${deck}".`, "error");
      return;
    }

    setModalStatus("Filtering cards by exact word value...", "info");
    const notes = await invokeAnkiConnect('notesInfo', { notes: noteIds });
    
    let matchedNote = null;
    for (const note of notes) {
      const fieldValue = (note.fields[vocabField]?.value || '').trim().toLowerCase();
      if (fieldValue === vocabWord.toLowerCase()) {
        matchedNote = note;
        break;
      }
    }

    if (!matchedNote) {
      setModalStatus(`No exact matching card found for "${vocabWord}" (after trimming spaces).`, "error");
      return;
    }

    const noteId = matchedNote.noteId;
    setModalStatus("Checking card queue status...", "info");

    const cardIds = matchedNote.cards;
    let isNewCard = false;
    if (cardIds && cardIds.length > 0) {
      const cards = await invokeAnkiConnect('cardsInfo', { cards: cardIds });
      isNewCard = cards.some(c => c.type === 0);
    }

    setModalStatus("Uploading image to Anki...", "info");
    const targetImage = images[selectedIndex];
    const proxyUrl = `/api/proxy?url=${encodeURIComponent(targetImage.url)}`;
    const base64Data = await fetchAndConvertToBase64(proxyUrl, targetImage.thumb);

    const safeWord = vocabWord.replace(/[^a-zA-Z0-9]/g, '_');
    const filename = `vocab_finder_${Date.now()}_${safeWord}.png`;
    
    await invokeAnkiConnect('storeMediaFile', {
      filename,
      data: base64Data
    });

    setModalStatus("Inserting image into card field...", "info");
    await invokeAnkiConnect('updateNoteFields', {
      note: {
        id: noteId,
        fields: {
          [imageField]: `<img src="${filename}">`
        }
      }
    });

    let rescheduleMsg = "";
    if (isNewCard) {
      setModalStatus("Rescheduling new card to today...", "info");
      await invokeAnkiConnect('setDueDate', {
        cards: cardIds,
        days: "0"
      });
      rescheduleMsg = " and rescheduled to today";
    }

    hidePromptModal();
    showToast(`Linked image to "${vocabWord}"${rescheduleMsg}! 🎉`);

    // If inside reviewer iframe: close the crawler and refresh parent's card view
    if (isReviewerIframe()) {
      setTimeout(() => {
        window.parent.closeImageCrawler();
        window.parent.loadActiveCard();
      }, 800); // short delay so toast is visible first
    }
  } catch (err) {
    console.error(err);
    setModalStatus(`Error: ${err.message || err}`, "error");
  }
}

// Modal Event Listeners
modalCloseBtn.addEventListener('click', hidePromptModal);
modalCancelBtn.addEventListener('click', hidePromptModal);
modalConfirmBtn.addEventListener('click', linkImageToAnkiCard);
document.querySelector('.modal-backdrop').addEventListener('click', hidePromptModal);
// Compute dynamic column count in CSS grid
function getColumnsCount() {
  const cards = Array.from(document.querySelectorAll('.image-card'));
  if (cards.length < 2) return 1;
  
  let cols = 1;
  const firstOffsetTop = cards[0].offsetTop;
  while (cols < cards.length && cards[cols].offsetTop === firstOffsetTop) {
    cols++;
  }
  return cols;
}

// Keyboard Event Handlers
document.addEventListener('keydown', (e) => {
  const isModalOpen = !promptModal.classList.contains('hidden');
  const activeElement = document.activeElement;
  const isTyping = activeElement.tagName === 'INPUT' || activeElement.tagName === 'SELECT' || activeElement.tagName === 'TEXTAREA';

  // If linking modal is open
  if (isModalOpen) {
    if (e.key === 'Enter') {
      e.preventDefault();
      linkImageToAnkiCard();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      hidePromptModal();
    }
    return;
  }

  // Suspend keyboard shortcuts if typing in any search or select box (when modal is closed)
  if (isTyping) {
    if (activeElement === searchInput) {
      if (e.key === 'Enter') {
        performSearch();
      } else if (e.key === 'Escape') {
        searchInput.blur();
      }
    } else {
      if (e.key === 'Escape') {
        activeElement.blur();
        toggleSettingsDrawer(false);
      }
    }
    return;
  }

  // Settings toggle shortcut
  if (e.key === ',') {
    e.preventDefault();
    toggleSettingsDrawer();
    return;
  }

  // Key navigation when search is not focused
  if (images.length === 0) {
    if (e.key === '/') {
      e.preventDefault();
      searchInput.focus();
      searchInput.select();
    }
    return;
  }

  const columns = getColumnsCount();

  switch (e.key) {
    // Left
    case 'ArrowLeft':
    case 'r':
    case 'R':
      e.preventDefault();
      selectImage(selectedIndex - 1);
      break;

    // Right
    case 'ArrowRight':
    case 't':
    case 'T':
      e.preventDefault();
      selectImage(selectedIndex + 1);
      break;

    // Up
    case 'ArrowUp':
    case 'f':
    case 'F':
      e.preventDefault();
      selectImage(selectedIndex - columns);
      break;

    // Down
    case 'ArrowDown':
    case 's':
    case 'S':
      e.preventDefault();
      selectImage(selectedIndex + columns);
      break;

    // Enter: in iframe mode, show word prompt; standalone, copy to clipboard
    case 'Enter':
    case 'c':
    case 'C':
      e.preventDefault();
      if (isReviewerIframe()) {
        showPromptModal(selectedIndex);
        break;
      }
      triggerCopy(selectedIndex);
      break;

    // Spacebar: show link-to-card prompt (both iframe and standalone)
    case ' ':
      e.preventDefault();
      showPromptModal(selectedIndex);
      break;

    // Sync directly to Anki as new note
    case 'a':
    case 'A':
      e.preventDefault();
      if (linkImageIfIframe(selectedIndex)) {
        break;
      }
      addNoteToAnki(selectedIndex);
      break;

    // Focus search
    case '/':
      e.preventDefault();
      searchInput.focus();
      searchInput.select();
      break;

    // Escape hides settings or closes iframe modal
    case 'Escape':
      e.preventDefault();
      const drawer = document.getElementById('settings-drawer');
      if (drawer && drawer.classList.contains('open')) {
        toggleSettingsDrawer(false);
      } else if (isReviewerIframe()) {
        window.parent.closeImageCrawler();
      }
      break;

    default:
      break;
  }
});

// Run Anki status check on startup
checkAnkiStatus();
