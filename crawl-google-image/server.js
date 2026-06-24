const express = require('express');
const cors = require('cors');
const axios = require('axios');
const cheerio = require('cheerio');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;

app.use(cors());
app.use(express.static(path.join(__dirname, 'public')));

// API Endpoint to search images using Bing / Google
app.get('/api/search', async (req, res) => {
  const query = req.query.q;
  const googleKey = req.query.googleKey;
  const googleCx = req.query.googleCx;

  if (!query) {
    return res.status(400).json({ error: 'Query parameter "q" is required' });
  }

  // If Google keys are provided, use Google Custom Search API
  if (googleKey && googleCx) {
    try {
      const url = `https://www.googleapis.com/customsearch/v1`;
      // Fetch 3 pages of results (30 images) in parallel
      const startIndices = [1, 11, 21];
      const requests = startIndices.map(start => 
        axios.get(url, {
          params: {
            key: googleKey,
            cx: googleCx,
            q: query,
            searchType: 'image',
            num: 10,
            start: start
          },
          timeout: 10000
        }).catch(err => {
          console.error(`Google CSE page start=${start} error:`, err.message);
          return null; // gracefully ignore failed pages
        })
      );

      const responses = await Promise.all(requests);
      const images = [];
      const seenUrls = new Set();

      for (const response of responses) {
        if (!response || !response.data) continue;
        const items = response.data.items || [];
        for (const item of items) {
          if (!item.link || seenUrls.has(item.link)) continue;
          seenUrls.add(item.link);

          let domain = '';
          try {
            domain = new URL(item.image.contextLink).hostname;
          } catch (e) {}

          images.push({
            title: item.title || '',
            url: item.link,
            thumb: item.image.thumbnailLink,
            source: domain || 'google'
          });
        }
      }

      if (images.length > 0) {
        return res.json({ results: images });
      }
      console.log('Google search returned no results, falling back to Bing...');
    } catch (err) {
      console.error('Google Search error:', err.message);
      console.log('Falling back to Bing search...');
    }
  }

  // Otherwise, fallback to Bing Images scraping
  // Fetch multiple queries in parallel to bypass pagination limitations and get ~80-100 unique images
  try {
    const queries = [query, `${query} photo`, `${query} material`].slice(0, 3);
    const scrapeRequests = queries.map(async (q) => {
      const url = `https://www.bing.com/images/search?q=${encodeURIComponent(q)}`;
      try {
        const { data } = await axios.get(url, {
          headers: {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9'
          },
          timeout: 10000
        });
        const $ = cheerio.load(data);
        const pageImages = [];
        $('.iusc').each((i, el) => {
          const mAttr = $(el).attr('m');
          if (mAttr) {
            try {
              const mData = JSON.parse(mAttr);
              if (mData.murl) {
                let domain = '';
                try {
                  domain = new URL(mData.murl).hostname;
                } catch (e) {}

                pageImages.push({
                  title: mData.title || '',
                  url: mData.murl,
                  thumb: mData.turl,
                  source: domain || mData.pubDomain || 'external'
                });
              }
            } catch (e) {}
          }
        });
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
    try {
      referer = new URL(imageUrl).origin;
    } catch (e) {}

    const response = await axios({
      method: 'get',
      url: imageUrl,
      responseType: 'stream',
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': referer
      },
      timeout: 10000
    });

    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET');
    
    if (response.headers['content-type']) {
      res.setHeader('Content-Type', response.headers['content-type']);
    }
    if (response.headers['content-length']) {
      res.setHeader('Content-Length', response.headers['content-length']);
    }

    response.data.pipe(res);
  } catch (err) {
    console.error('Proxy error for:', imageUrl, err.message);
    res.status(500).send('Error loading image');
  }
});

// Endpoint to serve media files directly from Anki via retrieveMediaFile
app.get('/media/:filename', async (req, res) => {
  const filename = req.params.filename;
  try {
    const response = await axios.post('http://127.0.0.1:8765', {
      action: 'retrieveMediaFile',
      version: 6,
      params: { filename }
    }, { timeout: 15000 });

    const base64Data = response.data.result;
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
    const response = await axios.post('http://127.0.0.1:8765', req.body, {
      timeout: 60000
    });
    res.json(response.data);
  } catch (err) {
    console.error('AnkiConnect proxy error:', err.message);
    res.status(500).json({ error: 'AnkiConnect is offline or unreachable' });
  }
});

app.listen(PORT, () => {
  console.log(`Server is running at http://localhost:${PORT}`);
});
