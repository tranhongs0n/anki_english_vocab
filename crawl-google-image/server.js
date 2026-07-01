const express = require('express');
const cors = require('cors');
const path = require('path');
const { Readable } = require('stream');

const app = express();
const PORT = process.env.PORT || 3000;

app.use(cors());
app.use(express.static(path.join(__dirname, 'public')));

const SEARCH_HEADERS = {
  'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
  'Accept-Language': 'en-US,en;q=0.9',
  'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
};

async function fetchBing(q) {
  const url = `https://www.bing.com/images/search?q=${encodeURIComponent(q)}&first=1&count=20&adlt=strict`;
  try {
    const response = await fetch(url, { headers: SEARCH_HEADERS, signal: AbortSignal.timeout(5000) });
    const data = await response.text();
    const images = [];
    const mRegex = /m="({[^"]+})"/g;
    let match;
    while ((match = mRegex.exec(data)) !== null) {
      try {
        const jsonStr = match[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&');
        const mData = JSON.parse(jsonStr);
        if (mData.murl) images.push({ title: mData.title || '', url: mData.murl, thumb: mData.turl, source: 'bing' });
      } catch (e) {}
    }
    return images;
  } catch (err) { return []; }
}

async function fetchYahoo(q) {
  try {
    const url = `https://images.search.yahoo.com/search/images?p=${encodeURIComponent(q)}&b=1`;
    const response = await fetch(url, { headers: SEARCH_HEADERS, signal: AbortSignal.timeout(5000) });
    const data = await response.text();
    const images = [];
    const r1 = /imgurl=(https?(?::\/\/|%3A%2F%2F)[^&"']+)/gi;
    let match;
    while ((match = r1.exec(data)) !== null) {
      const u = decodeURIComponent(match[1]);
      images.push({ title: '', url: u, thumb: u, source: 'yahoo' });
    }
    const r2 = /src=["'](https:\/\/tse\d+\.mm\.bing\.net\/th\?id=[^"']+)["']/gi;
    let i = 0;
    while ((match = r2.exec(data)) !== null && i < images.length) {
      images[i].thumb = match[1].replace(/&amp;/g, '&');
      i++;
    }
    return images;
  } catch (err) { return []; }
}

async function fetchGoogle(q) {
  try {
    const url = `https://www.google.com/search?q=${encodeURIComponent(q)}&tbm=isch`;
    const response = await fetch(url, { headers: SEARCH_HEADERS, signal: AbortSignal.timeout(5000) });
    let html = await response.text();
    html = html.replace(/\\u003d/g, '=').replace(/\\u0026/g, '&').replace(/\\\//g, '/');
    
    const images = [];
    const tbnRegex = /(https?:\/\/encrypted-tbn[0-9]\.gstatic\.com\/images\?q=tbn:[^"'\s\\]+)/gi;
    const highRegex = /\[\s*"([^"]+)"\s*,\s*\d+\s*,\s*\d+/g;
    
    let thumbs = [];
    let match;
    while((match = tbnRegex.exec(html)) !== null) thumbs.push(match[1]);
    
    let highs = [];
    while((match = highRegex.exec(html)) !== null) {
      if (match[1].startsWith('http') && !match[1].includes('gstatic.com') && !match[1].includes('x-raw-image')) {
        highs.push(match[1]);
      }
    }
    
    for(let i=0; i < Math.min(thumbs.length, highs.length); i++) {
       images.push({ title: '', url: highs[i], thumb: thumbs[i], source: 'google' });
    }
    return images;
  } catch (err) { return []; }
}

async function fetchDDG(q) {
  try {
    const url = "https://html.duckduckgo.com/html/";
    const formData = new URLSearchParams();
    formData.append('q', q);
    const response = await fetch(url, { 
       method: 'POST', 
       headers: { ...SEARCH_HEADERS, 'Content-Type': 'application/x-www-form-urlencoded', 'Referer': 'https://duckduckgo.com/' },
       body: formData,
       signal: AbortSignal.timeout(5000)
    });
    const data = await response.text();
    const images = [];
    const regex = /src=["'](\/\/external-content\.duckduckgo\.com\/iu\/\?u=[^"']+)["']/gi;
    let match;
    while((match = regex.exec(data)) !== null) {
       let u = "https:" + match[1];
       try {
           const parsed = new URL(u);
           const actual = parsed.searchParams.get('u');
           if (actual) images.push({ title: '', url: actual, thumb: u, source: 'ddg' });
       } catch(e) {}
    }
    return images;
  } catch (err) { return []; }
}

// API Endpoint to search images using multiplexed sources
app.get('/api/search', async (req, res) => {
  const query = req.query.q;
  const quick = req.query.quick === 'true';

  if (!query) {
    return res.status(400).json({ error: 'Query parameter "q" is required' });
  }

  try {
    const queries = quick ? [query] : [query, `${query} photo`, `${query} material`].slice(0, 3);
    
    let allPromises = [];
    for (const q of queries) {
      allPromises.push(fetchBing(q));
      allPromises.push(fetchYahoo(q));
      allPromises.push(fetchDDG(q));
      if (quick) allPromises.push(fetchGoogle(q)); // Google can be slow/block, do mainly on quick
    }

    const resultsArray = await Promise.all(allPromises);
    const mergedResults = [];
    const seenUrls = new Set();

    for (const results of resultsArray) {
      for (const img of results) {
        if (!seenUrls.has(img.url)) {
          seenUrls.add(img.url);
          mergedResults.push(img);
        }
      }
    }

    res.json({ results: mergedResults });
  } catch (err) {
    console.error('Search error for:', query, err.message);
    res.status(500).json({ error: 'Failed to fetch search results' });
  }
});

// Proxy endpoint to bypass CORS and copy images directly to clipboard
app.get('/api/proxy', async (req, res) => {
  const imageUrl = req.query.url;
  if (!imageUrl) {
    return res.status(400).send('URL is required');
  }

  try {
    let parsedUrl;
    try {
      parsedUrl = new URL(imageUrl);
    } catch (e) {
      return res.status(400).send('Invalid URL format');
    }

    if (parsedUrl.protocol !== 'http:' && parsedUrl.protocol !== 'https:') {
      return res.status(400).send('Invalid URL scheme');
    }

    let referer = 'https://duckduckgo.com/';
    try { referer = parsedUrl.origin; } catch (e) {}

    const response = await fetch(imageUrl, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': referer
      },
      signal: AbortSignal.timeout(10000)
    });

    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET');
    
    if (response.headers.get('content-type')) {
      res.setHeader('Content-Type', response.headers.get('content-type'));
    }
    if (response.headers.get('content-length')) {
      res.setHeader('Content-Length', response.headers.get('content-length'));
    }

    if (!response.body) {
      return res.status(204).send();
    }
    Readable.fromWeb(response.body).pipe(res);
  } catch (err) {
    console.error('Proxy error for:', imageUrl, err.message);
    res.status(500).send('Error loading image');
  }
});

// Endpoint to serve media files directly from Anki via retrieveMediaFile
app.get('/media/:filename', async (req, res) => {
  const filename = req.params.filename;
  try {
    const response = await fetch('http://127.0.0.1:8765', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action: 'retrieveMediaFile',
        version: 6,
        params: { filename }
      }),
      signal: AbortSignal.timeout(15000)
    });
    
    const data = await response.json();
    const base64Data = data.result;
    
    if (!base64Data) {
      return res.status(404).send('File not found');
    }

    const buffer = Buffer.from(base64Data, 'base64');
    const ext = path.extname(filename).toLowerCase();
    let contentType = 'application/octet-stream';
    if (ext === '.jpg' || ext === '.jpeg') contentType = 'image/jpeg';
    else if (ext === '.png') contentType = 'image/png';
    else if (ext === '.gif') contentType = 'image/gif';
    else if (ext === '.svg') contentType = 'image/svg+xml';
    else if (ext === '.mp3') contentType = 'audio/mpeg';
    else if (ext === '.wav') contentType = 'audio/wav';
    else if (ext === '.ogg') contentType = 'audio/ogg';

    res.setHeader('Content-Type', contentType);
    res.send(buffer);
  } catch (err) {
    console.error('Error serving media file:', filename, err.message);
    res.status(500).send('Error retrieving media file');
  }
});

// Proxy endpoint to AnkiConnect to bypass CORS issues
app.post('/api/ankiconnect', express.json({ limit: '50mb' }), async (req, res) => {
  try {
    const response = await fetch('http://127.0.0.1:8765', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req.body),
      signal: AbortSignal.timeout(60000)
    });
    const data = await response.json();
    res.json(data);
  } catch (err) {
    console.error('AnkiConnect proxy error:', err.message);
    res.status(500).json({ error: 'AnkiConnect is offline or unreachable' });
  }
});

app.listen(PORT, () => {
  console.log(`Server is running at http://localhost:${PORT}`);
});
