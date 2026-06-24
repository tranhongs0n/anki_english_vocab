const axios = require('axios');
const cheerio = require('cheerio');

async function test() {
  const searchTerm = 'apple';
  const url = `https://www.bing.com/images/search?q=${encodeURIComponent(searchTerm)}`;
  
  try {
    console.log("Fetching Bing Images page...");
    const { data } = await axios.get(url, {
      headers: {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
      }
    });

    const $ = cheerio.load(data);
    const images = [];

    // Bing Images HTML contains image links in elements, often inside <a> tags or <img> tags
    // Typically, image data is stored as a JSON string in the 'm' attribute of 'iusc' class elements:
    // <a class="iusc" m='{"murl":"https://example.com/image.jpg", "turl":"..."}'>
    console.log("Finding class iusc...");
    $('.iusc').each((i, el) => {
      const mAttr = $(el).attr('m');
      if (mAttr) {
        try {
          const mData = JSON.parse(mAttr);
          if (mData.murl) {
            images.push({
              title: mData.title || '',
              url: mData.murl,
              thumb: mData.turl
            });
          }
        } catch (e) {
          // ignore parsing error
        }
      }
    });

    console.log(`Found ${images.length} images.`);
    if (images.length > 0) {
      console.log("First 3 images:");
      console.log(images.slice(0, 3));
    }
  } catch (err) {
    console.error("Error scraping Bing:", err.message);
  }
}

test();
