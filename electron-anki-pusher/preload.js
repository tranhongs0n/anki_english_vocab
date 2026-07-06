const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('ankiAPI', {
  getCurrentVocab: () => ipcRenderer.invoke('get-current-vocab'),
  pushAnki: (vocab, url) => ipcRenderer.invoke('push-anki', vocab, url)
});

let hintMode = false;
let hintString = '';
let hints = [];

function generateHints(count) {
  const chars = 'asdfjklweruio'.split('');
  const result = [];
  let numChars = 1;
  while (Math.pow(chars.length, numChars) < count) numChars++;
  
  for (let i = 0; i < count; i++) {
    let hint = '';
    let val = i;
    for (let j = 0; j < numChars; j++) {
      hint = chars[val % chars.length] + hint;
      val = Math.floor(val / chars.length);
    }
    result.push(hint);
  }
  return result;
}

function clearHints() {
  document.querySelectorAll('.anki-hint').forEach(el => el.remove());
  hints = [];
  hintMode = false;
  hintString = '';
}

function showAnkiPrompt(imageUrl) {
  window.ankiAPI.getCurrentVocab().then(defaultVocab => {
    const overlay = document.createElement('div');
    overlay.innerHTML = `
      <div style="position:fixed; top:50%; left:50%; transform:translate(-50%,-50%); background:white; color:black; padding:20px; border-radius:10px; z-index:999999; box-shadow: 0 4px 10px rgba(0,0,0,0.5); font-family:sans-serif;">
        <h3 style="margin-top:0">Push to Anki</h3>
        <p>Vocab word:</p>
        <input type="text" id="anki-vocab-input" value="${defaultVocab}" style="width:200px; padding:5px; border:1px solid #ccc; color:black; background:white;">
        <div style="margin-top:15px; text-align:right;">
          <button id="anki-cancel" style="padding:5px 10px; cursor:pointer;">Cancel</button>
          <button id="anki-ok" style="padding:5px 10px; background:#4CAF50; color:white; border:none; cursor:pointer;">Push</button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);
    const input = document.getElementById('anki-vocab-input');
    input.focus();
    input.select();

    const close = () => overlay.remove();
    input.addEventListener('keydown', (ev) => {
      if(ev.key === 'Enter') document.getElementById('anki-ok').click();
      if(ev.key === 'Escape') close();
    });
    document.getElementById('anki-cancel').onclick = close;
    document.getElementById('anki-ok').onclick = async () => {
      const vocab = input.value.trim();
      if(!vocab) return;
      close();
      document.body.style.cursor = 'wait';
      const fb = document.createElement('div');
      fb.textContent = 'Syncing to Anki...';
      fb.style.cssText = 'position:fixed; bottom:20px; right:20px; background:#333; color:#fff; padding:10px; border-radius:5px; z-index:999999;';
      document.body.appendChild(fb);
      const res = await window.ankiAPI.pushAnki(vocab, imageUrl);
      document.body.style.cursor = 'default';
      if(res.success) { fb.style.background = '#4CAF50'; fb.textContent = '✅ Success!'; }
      else { fb.style.background = '#f44336'; fb.textContent = '❌ Failed: ' + res.error; }
      setTimeout(() => fb.remove(), 3000);
    };
  });
}

window.addEventListener('keydown', (e) => {
    // Ignore if typing in search box
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable) {
      if (e.key === 'Escape') { e.target.blur(); clearHints(); }
      return;
    }

    if (e.key === 'Escape') { clearHints(); return; }

    // Start Vimium mode
    if (!hintMode && e.key === 'f') {
      e.preventDefault();
      setTimeout(() => {
        const imgs = Array.from(document.querySelectorAll('img[src^="http"]'))
          .filter(img => {
            const r = img.getBoundingClientRect();
            return !img.src.includes('gstatic.com') && !img.src.includes('favicon') && r.width > 50 && r.height > 50 && window.getComputedStyle(img).display !== 'none';
          });
          
        if (imgs.length === 0) return;
        
        const generated = generateHints(imgs.length);
        imgs.forEach((img, i) => {
          const r = img.getBoundingClientRect();
          const hintEl = document.createElement('div');
          hintEl.className = 'anki-hint';
          hintEl.textContent = generated[i].toUpperCase();
          hintEl.style.cssText = `position:absolute; top:${r.top + window.scrollY}px; left:${r.left + window.scrollX}px; background:#ffeb3b; color:black; font-weight:bold; padding:2px 4px; border:1px solid #000; border-radius:3px; z-index:999998; font-size:12px; font-family:sans-serif; pointer-events:none;`;
          document.body.appendChild(hintEl);
          hints.push({ hint: generated[i], url: img.src, el: hintEl });
        });
        hintMode = true;
        hintString = '';
      }, 0);
      return;
    }

    // Process Vimium keys
    if (hintMode) {
      e.preventDefault();
      // Ignore modifier keys
      if (e.ctrlKey || e.altKey || e.metaKey || e.key.length > 1) return;
      
      hintString += e.key.toLowerCase();
      setTimeout(() => {
        let match = false;
        hints.forEach(h => {
          if (h.hint === hintString) {
            clearHints();
            match = true;
            showAnkiPrompt(h.url);
          } else if (!h.hint.startsWith(hintString)) {
            h.el.style.opacity = '0.3';
          } else {
            h.el.style.opacity = '1';
          }
        });
        if (!match && !hints.some(h => h.hint.startsWith(hintString))) {
          clearHints(); // invalid sequence
        }
      }, 0);
    }
  });
