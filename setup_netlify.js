/**
 * Netlify Build & Preparation Script
 * Copies static assets, stylesheets, scripts, and sample images to the public publish directory.
 */
const fs = require('fs');
const path = require('path');

function copyRecursive(src, dest) {
  if (!fs.existsSync(src)) return;
  fs.mkdirSync(dest, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const srcPath = path.join(src, entry.name);
    const destPath = path.join(dest, entry.name);
    if (entry.isDirectory()) {
      copyRecursive(srcPath, destPath);
    } else {
      fs.copyFileSync(srcPath, destPath);
    }
  }
}

const publicDir = path.join(__dirname, 'public');
fs.mkdirSync(publicDir, { recursive: true });

// 1. Copy web/static contents into public root
const webStatic = path.join(__dirname, 'web', 'static');
copyRecursive(webStatic, publicDir);

// 2. Also keep a copy inside public/static for /static/* references
const publicStatic = path.join(publicDir, 'static');
copyRecursive(webStatic, publicStatic);

// 3. Copy sample_images into public/sample_images
const sampleImages = path.join(__dirname, 'sample_images');
const publicSample = path.join(publicDir, 'sample_images');
copyRecursive(sampleImages, publicSample);

// 4. Create _redirects file for SPA / fallback routing
const redirectsContent = `
/static/*  /:splat  200
/*  /index.html  200
`;
fs.writeFileSync(path.join(publicDir, '_redirects'), redirectsContent.trim());

console.log('✅ Netlify public build directory prepared successfully!');
