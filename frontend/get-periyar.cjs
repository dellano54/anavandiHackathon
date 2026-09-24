const path = require('path');
const sharp = require('sharp'); // already installed
const https = require('https');

const z = 13;
// Periyar River approximate bounds (around 10.02 N, 76.31 E)
function lon2tile(lon, zoom) { return (Math.floor((lon + 180) / 360 * Math.pow(2, zoom))); }
function lat2tile(lat, zoom) { return (Math.floor((1 - Math.log(Math.tan(lat * Math.PI / 180) + 1 / Math.cos(lat * Math.PI / 180)) / Math.PI) / 2 * Math.pow(2, zoom))); }

// Let's get a 3x2 grid of tiles around this point
const center_x = lon2tile(76.31, z);
const center_y = lat2tile(10.02, z);

const x1 = center_x - 1;
const x2 = center_x + 1;
const y1 = center_y - 1;
const y2 = center_y;

console.log(`Downloading tiles from x: ${x1}-${x2}, y: ${y1}-${y2}`);

async function downloadTile(x, y) {
    const url = `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${z}/${y}/${x}`;
    return new Promise((resolve, reject) => {
        https.get(url, { headers: { 'User-Agent': 'Mozilla/5.0' } }, (res) => {
            if (res.statusCode !== 200) {
                reject(new Error(`Failed to download ${url}: ${res.statusCode}`));
                return;
            }
            const data = [];
            res.on('data', chunk => data.push(chunk));
            res.on('end', () => resolve(Buffer.concat(data)));
            res.on('error', reject);
        }).on('error', reject);
    });
}

async function stitch() {
    const width = (x2 - x1 + 1) * 256;
    const height = (y2 - y1 + 1) * 256;
    
    console.log(`Final image size: ${width}x${height}`);
    
    const composites = [];
    for (let x = x1; x <= x2; x++) {
        for (let y = y1; y <= y2; y++) {
            console.log(`Fetching tile ${x}, ${y}`);
            try {
                const buffer = await downloadTile(x, y);
                composites.push({
                    input: buffer,
                    left: (x - x1) * 256,
                    top: (y - y1) * 256
                });
            } catch (e) {
                console.error(e);
            }
        }
    }
    
    await sharp({
        create: {
            width: width,
            height: height,
            channels: 3,
            background: { r: 0, g: 0, b: 0 }
        }
    })
    .composite(composites)
    .jpeg()
    .toFile(path.join(__dirname, 'public', 'periyar-satellite.jpg'));
    
    console.log('Done creating periyar-satellite.jpg');
}

stitch().catch(console.error);
