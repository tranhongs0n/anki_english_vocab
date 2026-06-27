const express = require('express');
const cors = require('cors');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;

app.use(cors());
app.use(express.static(path.join(__dirname, 'public')));

// API Endpoint to search images using Bing / Google
app.get('/api/search', async (req, res) => {
  const query = req.query.q;
  const quick = req.query.quick === 'true';

  if (!query) {
    return res.status(400).json({ error: 'Query parameter "q" is required' });
  }

  try {
    const queries = quick ? [query] : [query, `${query} photo`, `${query} material`].slice(0, 3);
    const scrapeRequests = queries.map(async (q) => {
      const url = `https://www.bing.com/images/search?q=${encodeURIComponent(q)}&first=1&count=20`;
      try {
        const response = await fetch(url, {
          headers: {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9'
          },
          signal: AbortSignal.timeout(10000)
        });
        const data = await response.text();
        
        const pageImages = [];
        const mRegex = /m="({[^"]+})"/g;
        let match;
        
        while ((match = mRegex.exec(data)) !== null) {
          try {
            const jsonStr = match[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&');
            const mData = JSON.parse(jsonStr);
            
            if (mData.murl) {
              let domain = '';
              try { domain = new URL(mData.murl).hostname; } catch (e) {}

              pageImages.push({
                title: mData.title || '',
                url: mData.murl,
                thumb: mData.turl,
                source: domain || mData.pubDomain || 'external'
              });
            }
          } catch (e) {}
        }
        return pageImages;
      } catch (err) {
        console.error(`Bing scrape error for subquery "${q}":`, err.message);
        return [];
      }
    });

    const resultsArray = await Promise.all(scrapeRequests);
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
    let referer = 'https://duckduckgo.com/';
    try { referer = new URL(imageUrl).origin; } catch (e) {}

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

    const { Readable } = require('stream');
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
