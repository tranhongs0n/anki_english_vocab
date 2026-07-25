// content.js

function findTargetImage() {
  // Heuristic to find the focused image on Google Images
  // Google Images side panel images are usually large and visible
  const imgs = Array.from(document.querySelectorAll('img[src^="http"]'));
  
  // Filter out thumbnails, icons, and small images
  const largeImgs = imgs.filter(img => {
    const rect = img.getBoundingClientRect();
    // Exclude google logos and small thumbnails
    if (img.src.includes('gstatic.com') || img.src.includes('favicon')) return false;
    
    return rect.width > 200 && rect.height > 200 && rect.top >= 0 && window.getComputedStyle(img).display !== 'none';
  });

  // Sort by visible area (width * height)
  largeImgs.sort((a, b) => {
    const aRect = a.getBoundingClientRect();
    const bRect = b.getBoundingClientRect();
    return (bRect.width * bRect.height) - (aRect.width * aRect.height);
  });

  if (largeImgs.length > 0) {
    return largeImgs[0].src;
  }
  return null;
}

document.addEventListener('keydown', (e) => {
  if (e.key === 'F8') {
    e.preventDefault();
    
    const imageUrl = findTargetImage();
    if (!imageUrl) {
      alert("No suitable large image found. Please click an image to preview it in the side panel first.");
      return;
    }

    // Request current vocab from Anki via background script
    chrome.runtime.sendMessage({ type: 'GET_CURRENT_CARD' }, (response) => {
      let defaultVocab = '';
      if (response && response.vocab) {
        defaultVocab = response.vocab;
      }
      
      const vocab = window.prompt("Enter vocab to link image to:", defaultVocab);
      if (!vocab) return; // user cancelled or entered empty string

      // Show a loading indication
      document.body.style.cursor = 'wait';

      chrome.runtime.sendMessage({ type: 'PUSH_TO_ANKI', vocab, imageUrl }, (res) => {
        document.body.style.cursor = 'default';
        if (res && res.success) {
          // Visual feedback
          const banner = document.createElement('div');
          banner.textContent = '✅ Image pushed to Anki!';
          banner.style.position = 'fixed';
          banner.style.top = '20px';
          banner.style.left = '50%';
          banner.style.transform = 'translateX(-50%)';
          banner.style.background = '#4CAF50';
          banner.style.color = 'white';
          banner.style.padding = '10px 20px';
          banner.style.borderRadius = '5px';
          banner.style.zIndex = '999999';
          banner.style.fontFamily = 'sans-serif';
          document.body.appendChild(banner);
          setTimeout(() => banner.remove(), 3000);
        } else {
          alert('Failed to push to Anki: ' + (res ? res.error : 'Unknown error'));
        }
      });
    });
  }
});
