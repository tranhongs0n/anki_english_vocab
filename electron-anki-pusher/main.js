const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const http = require('http');

async function invokeAnki(action, params = {}) {
  const data = JSON.stringify({ action, version: 6, params });
  return new Promise((resolve, reject) => {
    const req = http.request({
      hostname: '127.0.0.1',
      port: 8765,
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    }, (res) => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        try {
          const result = JSON.parse(body);
          if (result.error) reject(new Error(result.error));
          else resolve(result.result);
        } catch(e) { reject(e); }
      });
    });
    req.on('error', reject);
    req.write(data);
    req.end();
  });
}

function createWindow () {
  const win = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  win.loadURL('https://images.google.com');
  // win.webContents.openDevTools(); // Uncomment to debug
}

app.whenReady().then(() => {
  createWindow();
  
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

ipcMain.handle('get-current-vocab', async () => {
  try {
    const card = await invokeAnki('guiCurrentCard');
    if (!card || !card.fields) return '';
    const fields = Object.keys(card.fields);
    let vocab = '';
    for (const f of ['Vocab', 'Word', 'Front', 'Expression', 'Text']) {
      if (card.fields[f]) { vocab = card.fields[f].value; break; }
    }
    if (!vocab && fields.length > 0) vocab = card.fields[fields[0]].value;
    return vocab.replace(/<[^>]+>/g, '').trim();
  } catch(e) {
    return '';
  }
});

ipcMain.handle('push-anki', async (event, vocab, imageUrl) => {
  try {
    // Fetch image
    const res = await fetch(imageUrl);
    const buffer = await res.arrayBuffer();
    const base64 = Buffer.from(buffer).toString('base64');
    const ext = imageUrl.split('.').pop().split(/[#?]/)[0] || 'jpg';
    const filename = `anki_push_${Date.now()}.${ext.substring(0,4)}`;

    // 1. Upload media
    await invokeAnki('storeMediaFile', { filename, data: base64 });

    // 2. Find note
    const notes = await invokeAnki('findNotes', { query: `Word:"${vocab}"` });
    if (!notes || notes.length === 0) throw new Error('Note not found for vocab: ' + vocab);
    
    // 3. Find exact match
    const notesInfo = await invokeAnki('notesInfo', { notes });
    let note = notesInfo[0];
    for (const n of notesInfo) {
      let exact = false;
      for (const k in n.fields) {
        if (n.fields[k].value.replace(/<[^>]+>/g,'').trim().toLowerCase() === vocab.toLowerCase()) {
          exact = true; break;
        }
      }
      if(exact) { note = n; break; }
    }

    // 4. Update fields
    const fields = Object.keys(note.fields);
    let imgField = fields.find(f => ['Image','Picture','Img','Back'].includes(f)) || fields[fields.length-1];
    const currentVal = note.fields[imgField].value;
    const imgTag = `<img src="${filename}">`;

    await invokeAnki('updateNoteFields', { 
      note: { id: note.noteId, fields: { [imgField]: currentVal + (currentVal?'<br>':'') + imgTag } } 
    });

    // 5. Unsuspend / set due today if new
    if (note.cards && note.cards.length > 0) {
      const cardsInfo = await invokeAnki('cardsInfo', { cards: note.cards });
      for (const c of cardsInfo) {
        if (c.queue === 0) await invokeAnki('setSpecificDueDate', { cards: [c.cardId], due: "0" });
      }
    }
    return { success: true };
  } catch(e) {
    return { success: false, error: e.message };
  }
});
