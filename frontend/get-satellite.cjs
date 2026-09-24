const fs = require('fs');
const https = require('https');
const path = require('path');
const sharp = require('sharp'); // already installed

const z = 10;
// Vembanad bbox approx: 9.3 to 10.1 N, 76.1 to 76.7 E
// Center approx: 9.6 N, 76.4 E
function lon2tile(lon, zoom) { return (Math.floor((lon + 180) / 360 * Math.pow(2, zoom))); }
function lat2tile(lat, zoom) { return (Math.floor((1 - Math.log(Math.tan(lat * Math.PI / 180) + 1 / Math.cos(lat * Math.PI / 180)) / Math.PI) / 2 * Math.pow(2, zoom))); }

const x1 = lon2tile(76.1, z);
const x2 = lon2tile(76.7, z);
const y1 = lat2tile(10.1, z);
const y2 = lat2tile(9.3, z);

console.log(`Downloading tiles from x: ${x1}-${x2}, y: ${y1}-${y2}`);

async function downloadTile(x, y) {
    const url = `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${z}/${y}/${x}`;
    return new Promise((resolve, reject) => {
        https.get(url, (res) => {
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
            const buffer = await downloadTile(x, y);
            composites.push({
                input: buffer,
                left: (x - x1) * 256,
                top: (y - y1) * 256
            });
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
    .toFile(path.join(__dirname, 'public', 'vembanad-satellite.jpg'));
    
    console.log('Done creating vembanad-satellite.jpg');
}

stitch().catch(console.error);
