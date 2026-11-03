import { createReadStream, existsSync, statSync } from 'node:fs';
import { createServer } from 'node:http';
import { extname, join, normalize, resolve } from 'node:path';

const root = resolve(import.meta.dirname, '../dist');
const port = Number(process.env.PORT || process.argv[2] || 4321);

const types = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.txt': 'text/plain; charset=utf-8',
  '.woff2': 'font/woff2',
  '.xml': 'application/xml; charset=utf-8',
};

function fileFor(pathname) {
  const clean = normalize(decodeURIComponent(pathname)).replace(/^(\.\.[/\\])+/, '');
  const base = resolve(root, '.' + clean);
  if (!base.startsWith(root)) return null;
  if (pathname === '/') return join(root, 'index.html');
  if (existsSync(base) && statSync(base).isFile()) return base;
  if (existsSync(`${base}.html`)) return `${base}.html`;
  if (existsSync(join(base, 'index.html'))) return join(base, 'index.html');
  return null;
}

createServer((request, response) => {
  const pathname = new URL(request.url ?? '/', 'http://localhost').pathname;
  const file = fileFor(pathname);
  if (!file) {
    const notFound = join(root, '404.html');
    response.writeHead(404, { 'Content-Type': types['.html'] });
    if (existsSync(notFound)) createReadStream(notFound).pipe(response);
    else response.end('Not found');
    return;
  }
  response.writeHead(200, {
    'Content-Type': types[extname(file)] ?? 'application/octet-stream',
    'Cache-Control': 'no-store',
  });
  if (request.method === 'HEAD') response.end();
  else createReadStream(file).pipe(response);
}).listen(port, '127.0.0.1', () => {
  console.log(`http://127.0.0.1:${port}/`);
});
