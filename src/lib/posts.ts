import { site } from './site';
import { fetchIssues, fetchPinned } from './github';
import { renderMarkdown } from './markdown';
import { plainExcerpt, slugify } from './text';
import { isoDate, localDate, yearOf } from './dates';

export interface Tag {
  name: string;
  slug: string;
}

export interface Post {
  number: number;
  title: string;
  raw: string;
  html: string;
  excerpt: string;
  created: Date;
  updated: Date;
  date: string;
  year: string;
  url: string;
  source: string;
  pinned: boolean;
  tags: Tag[];
}

export interface YearGroup {
  year: string;
  posts: Post[];
}

let postsPromise: Promise<Post[]> | undefined;

export function getPosts(): Promise<Post[]> {
  postsPromise ??= loadPosts();
  return postsPromise;
}

async function loadPosts(): Promise<Post[]> {
  const token = process.env.GITHUB_TOKEN || process.env.GH_TOKEN;
  const [issues, pinned] = await Promise.all([
    fetchIssues(site.repo, token),
    fetchPinned(site.repo, token),
  ]);
  const excluded = new Set(site.excludeLabels);

  const posts = await Promise.all(
    issues.map(async (issue): Promise<Post> => {
      const raw = issue.body ?? '';
      const names = issue.labels.map((label) => label.name);
      const created = localDate(issue.created_at, site.timezone);
      return {
        number: issue.number,
        title: issue.title,
        raw,
        html: await renderMarkdown(raw),
        excerpt: plainExcerpt(raw),
        created,
        updated: localDate(issue.updated_at, site.timezone),
        date: isoDate(created),
        year: yearOf(created),
        url: `/post/${issue.number}/`,
        source: issue.html_url,
        pinned:
          pinned.has(issue.number) ||
          (Boolean(site.pinLabel) && names.includes(site.pinLabel as string)),
        tags: names
          .filter((name) => !excluded.has(name))
          .map((name) => ({ name, slug: slugify(name) })),
      };
    }),
  );

  posts.sort(
    (a, b) => Number(b.pinned) - Number(a.pinned) || b.created.getTime() - a.created.getTime(),
  );
  return posts;
}

export function groupByYear(posts: Post[]): YearGroup[] {
  const groups: YearGroup[] = [];
  for (const post of posts) {
    const last = groups.at(-1);
    if (!last || last.year !== post.year) {
      groups.push({ year: post.year, posts: [post] });
    } else {
      last.posts.push(post);
    }
  }
  return groups;
}

export function tagsIndex(posts: Post[]): Tag[] {
  const counts = new Map<string, { tag: Tag; count: number }>();
  for (const post of posts) {
    for (const tag of post.tags) {
      const hit = counts.get(tag.slug);
      if (hit) hit.count += 1;
      else counts.set(tag.slug, { tag, count: 1 });
    }
  }
  return [...counts.values()]
    .sort((a, b) => b.count - a.count || a.tag.name.localeCompare(b.tag.name))
    .map((entry) => entry.tag);
}
