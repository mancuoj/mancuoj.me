export function slugify(text: string): string {
  const value = text
    .normalize('NFKC')
    .trim()
    .toLowerCase()
    .replace(/[\s/\\]+/g, '-')
    .replace(/[^\p{L}\p{N}._-]+/gu, '');
  return value || 'tag';
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
