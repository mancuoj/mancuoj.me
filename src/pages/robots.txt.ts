import type { APIRoute } from 'astro';

export const GET: APIRoute = () =>
  new Response(
    [
      'User-agent: *',
      'Content-Signal: ai-train=no, search=yes, ai-input=no',
      'Allow: /',
      '',
      'Sitemap: https://mancuoj.me/sitemap-index.xml',
      '',
    ].join('\n'),
    { headers: { 'Content-Type': 'text/plain; charset=utf-8' } },
  );
