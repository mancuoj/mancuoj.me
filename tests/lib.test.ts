import { describe, expect, it } from 'vitest';
import { fullDate, isoDate, listDate } from '../src/lib/dates';
import type { Post, Tag } from '../src/lib/posts';
import { groupByYear, tagsIndex } from '../src/lib/posts';
import { plainExcerpt, slugify } from '../src/lib/text';

function post(number: number, year = '2026', tags: Tag[] = []): Post {
  const created = new Date(Date.UTC(Number(year), 0, number));
  return {
    number,
    title: `文章 ${number}`,
    raw: '',
    html: '',
    excerpt: '',
    created,
    updated: created,
    date: isoDate(created),
    year,
    url: `/post/${number}/`,
    source: '',
    pinned: false,
    tags,
  };
}

describe('slugify', () => {
  it('keeps Chinese and lowercases Latin', () => {
    expect(slugify('Hello World')).toBe('hello-world');
    expect(slugify('随笔 Notes')).toBe('随笔-notes');
    expect(slugify('a/b\\c')).toBe('a-b-c');
    expect(slugify('  ')).toBe('tag');
  });
});

describe('plainExcerpt', () => {
  it('drops markup and takes the first paragraph', () => {
    const md = '这是**第一**段，带[链接](https://a.example)。\n\n第二段';
    expect(plainExcerpt(md)).toBe('这是第一段，带链接。');
    expect(plainExcerpt('前 `code` 后')).not.toContain('code');
  });

  it('truncates with an ellipsis', () => {
    const out = plainExcerpt('字'.repeat(200));
    expect(out.endsWith('…')).toBe(true);
    expect(Array.from(out)).toHaveLength(161);
  });
});

describe('dates', () => {
  const date = new Date(Date.UTC(2026, 10, 1));
  it('formats list, full and iso dates', () => {
    expect(listDate(date)).toBe('Nov 1');
    expect(fullDate(date)).toBe('2026 年 11 月 1 日');
    expect(isoDate(date)).toBe('2026-11-01');
  });
});

describe('groupByYear', () => {
  it('splits consecutive years', () => {
    const groups = groupByYear([post(1, '2026'), post(2, '2026'), post(3, '2025')]);
    expect(groups.map((group) => group.year)).toEqual(['2026', '2025']);
    expect(groups.map((group) => group.posts.length)).toEqual([2, 1]);
  });
});

describe('tagsIndex', () => {
  it('sorts by count then name', () => {
    const posts = [
      post(1, '2026', [
        { name: 'b', slug: 'b' },
        { name: 'a', slug: 'a' },
      ]),
      post(2, '2026', [{ name: 'a', slug: 'a' }]),
    ];
    expect(tagsIndex(posts).map((tag) => tag.slug)).toEqual(['a', 'b']);
  });
});
