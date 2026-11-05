export function slugify(text: string): string {
  const value = text
    .normalize('NFKC')
    .trim()
    .toLowerCase()
    .replace(/[\s/\\]+/g, '-')
    .replace(/[^\p{L}\p{N}._-]+/gu, '');
  return value || 'tag';
}

// Labels come from GitHub issues; show all-caps labels in title case unless the
// label is a common acronym.
const ACRONYMS = new Set([
  'AI', 'API', 'CSS', 'CLI', 'CPU', 'GPU', 'HTML', 'HTTP', 'JSON', 'JS',
  'OS', 'PDF', 'PNG', 'RSS', 'SQL', 'SVG', 'TS', 'UI', 'URL', 'UX', 'YAML',
]);

export function displayTag(name: string): string {
  if (!/^[A-Z]+$/.test(name) || name.length <= 2 || ACRONYMS.has(name)) return name;
  return name.charAt(0) + name.slice(1).toLowerCase();
}

export function plainExcerpt(markdown: string, limit = 160): string {
  if (!markdown) return '';
  let text = markdown
    .replace(/```[\s\S]*?```/g, '')
    .replace(/`[^`]*`/g, '')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '')
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/^\s{0,3}#{1,6}\s*/gm, '')
    .replace(/[>*_~]/g, '');
  const first = text.split(/\n{2,}/).find((part) => part.trim());
  text = (first ?? '').replace(/\s+/g, ' ').trim();
  if (Array.from(text).length > limit) {
    text = Array.from(text).slice(0, limit).join('').trimEnd() + '…';
  }
  return text;
}
