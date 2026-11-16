#!/usr/bin/env node
// verify:all 的最后一步：带 token 跑 build。
// build 会拉 GitHub issues，没有 token 就会 403——那个报错指向 API，不指向解决办法，
// 所以这里先把 token 找出来：环境变量优先，其次 `gh auth token`。
import { execSync, spawnSync } from 'node:child_process';

function ghToken() {
  try {
    return execSync('gh auth token', { stdio: ['ignore', 'pipe', 'ignore'] })
      .toString()
      .trim();
  } catch {
    return '';
  }
}

const token = process.env.GITHUB_TOKEN || ghToken();
if (!token) {
  console.error(
    [
      'error: 这一步要拉 GitHub issues，需要一个 token。',
      '  任选一种：',
      '    GITHUB_TOKEN=xxx pnpm run verify:all    # 直接给',
      '    gh auth login                           # 之后会自动取用 gh 的 token',
    ].join('\n'),
  );
  process.exit(1);
}

const r = spawnSync('pnpm', ['build'], {
  stdio: 'inherit',
  env: { ...process.env, GITHUB_TOKEN: token },
});
process.exit(r.status ?? 1);
