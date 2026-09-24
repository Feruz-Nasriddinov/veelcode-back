const http = require('http');
const fs = require('fs');
const path = require('path');

const root = path.resolve(process.argv[2]);
const port = Number(process.argv[3]);
const types = {
  '.html': 'text/html',
  '.js': 'text/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
};

function resolve(urlPath) {
  let file = path.join(root, urlPath);
  if (!file.startsWith(root)) return null;
  if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
  if (!fs.existsSync(file)) file = path.join(root, 'index.html');
  return file;
}

http.createServer((req, res) => {
  let file;
  try {
    file = resolve(decodeURIComponent(new URL(req.url, 'http://localhost').pathname));
  } catch {
    file = null;
  }
  if (!file) {
    res.writeHead(400);
    return res.end();
  }
  fs.readFile(file, (err, data) => {
    if (err) {
      res.writeHead(404);
      return res.end();
    }
    res.writeHead(200, { 'Content-Type': types[path.extname(file)] || 'application/octet-stream' });
    res.end(data);
  });
}).listen(port, '0.0.0.0');
