// background.js

async function invokeAnki(action, params = {}) {
  try {
    const response = await fetch('http://127.0.0.1:8765', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, version: 6, params })
    });
    const result = await response.json();
    if (result.error) throw new Error(result.error);
    return result.result;
  } catch (err) {
    console.error('AnkiConnect error:', err);
    throw err;
  }
}

async function fetchImageAsBase64(url) {
  const response = await fetch(url);
  const buffer = await response.arrayBuffer();
  // base64 encode buffer
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.type === 'GET_CURRENT_CARD') {
    invokeAnki('guiCurrentCard')
      .then(card => {
        if (!card || !card.fields) return sendResponse({ vocab: '' });
        // Try to find a field that looks like a vocab
        const fields = Object.keys(card.fields);
        let vocab = '';
        for (const f of ['Vocab', 'Word', 'Front', 'Expression', 'Text']) {
          if (card.fields[f]) {
            vocab = card.fields[f].value;
            break;
          }
        }
        if (!vocab && fields.length > 0) {
          vocab = card.fields[fields[0]].value;
        }
        // strip html
        vocab = vocab.replace(/<[^>]+>/g, '').trim();
        sendResponse({ vocab });
      })
      .catch(() => sendResponse({ vocab: '' }));
    return true;
  }

  if (request.type === 'PUSH_TO_ANKI') {
    (async () => {
      try {
        const { vocab, imageUrl } = request;
        
        // 1. Fetch Image as Base64
        const base64 = await fetchImageAsBase64(imageUrl);
        const ext = imageUrl.split('.').pop().split(/[#?]/)[0] || 'jpg';
        const filename = `anki_push_${Date.now()}.${ext.length > 4 ? 'jpg' : ext}`;

        // 2. Upload to Anki
        await invokeAnki('storeMediaFile', { filename, data: base64 });

        // 3. Find note by vocab
        const notes = await invokeAnki('findNotes', { query: `"${vocab}"` });
        if (!notes || notes.length === 0) {
          throw new Error('Note not found for vocab: ' + vocab);
        }
        
        const notesInfo = await invokeAnki('notesInfo', { notes });
        let note = notesInfo[0];

        // Find exact match to prevent getting a different word (e.g. 'intrigued' definition containing 'intrigue')
        for (const n of notesInfo) {
          let exactMatch = false;
          for (const key in n.fields) {
            const val = n.fields[key].value.replace(/<[^>]+>/g, '').trim();
            if (val.toLowerCase() === vocab.toLowerCase()) {
              exactMatch = true;
              break;
            }
          }
          if (exactMatch) {
            note = n;
            break;
          }
        }

        const noteId = note.noteId;

        // 4. Update Note
        // Try to find Image field
        const fields = Object.keys(note.fields);
        let imgField = '';
        for (const f of ['Image', 'Picture', 'Img', 'Back']) {
          if (fields.includes(f)) {
            imgField = f;
            break;
          }
        }
        if (!imgField) imgField = fields[fields.length - 1]; // fallback to last field

        const currentVal = note.fields[imgField].value;
        const imgTag = `<img src="${filename}">`;
        
        await invokeAnki('updateNoteFields', {
          note: {
            id: noteId,
            fields: {
              [imgField]: currentVal + (currentVal ? '<br>' : '') + imgTag
            }
          }
        });

        // 5. Check if card is new and schedule (Removed setSpecificDueDate as it's unsupported)
        const cards = note.cards; // array of card IDs
        if (cards && cards.length > 0) {
          const cardsInfo = await invokeAnki('cardsInfo', { cards });
          for (const card of cardsInfo) {
            // queue 0 means new
            if (card.queue === 0) {
              // Usually people want to move it to the front, but setSpecificDueDate is unsupported in standard AnkiConnect.
              // Skipping this step to prevent errors.
              console.log('Card is new, skipping schedule modification');
            }
          }
        }

        sendResponse({ success: true });
      } catch (err) {
        sendResponse({ success: false, error: err.message });
      }
    })();
    return true;
  }
});
