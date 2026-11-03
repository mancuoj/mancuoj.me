import { mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');
const config = JSON.parse(await readFile(join(root, 'config.json'), 'utf8'));
const token = process.env.GITHUB_TOKEN || process.env.GH_TOKEN;
const out = join(root, 'backup');
const postsDir = join(out, 'posts');

const headers = {
  Accept: 'application/vnd.github+json',
  'X-GitHub-Api-Version': '2022-11-28',
  'User-Agent': 'mancuoj-me-backup',
};
if (token) headers.Authorization = `Bearer ${token}`;

const issues = [];
for (let page = 1; ; page += 1) {
  const response = await fetch(
    `https://api.github.com/repos/${config.repo}/issues?state=open&sort=created&direction=desc&per_page=100&page=${page}`,
    { headers },
  );
  if (!response.ok) throw new Error(`GitHub issues ${response.status}: ${await response.text()}`);
  const batch = await response.json();
  issues.push(...batch.filter((issue) => !issue.pull_request));
  if (batch.length < 100) break;
}

function slugify(text) {
  const value = text
    .normalize('NFKC')
    .trim()
    .toLowerCase()
    .replace(/[\s/\\]+/g, '-')
    .replace(/[^\p{L}\p{N}._-]+/gu, '');
  return value || 'tag';
}

function localDate(iso) {
  const date = new Date(Date.parse(iso) + config.timezone * 3600 * 1000);
  return [
    date.getUTCFullYear(),
    String(date.getUTCMonth() + 1).padStart(2, '0'),
    String(date.getUTCDate()).padStart(2, '0'),
  ].join('-');
}

await rm(postsDir, { recursive: true, force: true });
await mkdir(postsDir, { recursive: true });

const index = [];
for (const issue of issues) {
  const tags = issue.labels.map((label) => label.name).filter((name) => !config.excludeLabels.includes(name));
  const date = localDate(issue.created_at);
  const updated = localDate(issue.updated_at);
  const filename = `${String(issue.number).padStart(4, '0')}-${slugify(issue.title)}.md`;
  const frontmatter = [
    '---',
    `number: ${issue.number}`,
    `title: ${JSON.stringify(issue.title)}`,
    `date: "${date}"`,
    `updated: "${updated}"`,
    `tags: ${JSON.stringify(tags)}`,
    `source: ${JSON.stringify(issue.html_url)}`,
    '---',
    '',
    '',
  ].join('\n');
  await writeFile(join(postsDir, filename), frontmatter + (issue.body ?? '').trimEnd() + '\n', 'utf8');
  index.push({ number: issue.number, title: issue.title, date, updated, tags, source: issue.html_url });
}

await writeFile(join(out, 'index.json'), JSON.stringify(index, null, 2) + '\n', 'utf8');
console.log(`backup: ${index.length} posts`);
