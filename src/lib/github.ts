const API = 'https://api.github.com';

export interface Issue {
  number: number;
  title: string;
  body: string | null;
  created_at: string;
  updated_at: string;
  html_url: string;
  labels: Array<{ name: string }>;
  pull_request?: unknown;
}

function headers(token?: string): HeadersInit {
  const h: Record<string, string> = {
    Accept: 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
    'User-Agent': 'mancuoj-me',
  };
  if (token) h.Authorization = `Bearer ${token}`;
  return h;
}

export async function fetchIssues(repo: string, token?: string): Promise<Issue[]> {
  const issues: Issue[] = [];
  for (let page = 1; ; page += 1) {
    const url = `${API}/repos/${repo}/issues?state=open&sort=created&direction=desc&per_page=100&page=${page}`;
    const res = await fetch(url, { headers: headers(token) });
    if (!res.ok) {
      throw new Error(`GitHub issues ${res.status}: ${await res.text()}`);
    }
    const batch = (await res.json()) as Issue[];
    issues.push(...batch.filter((issue) => !issue.pull_request));
    if (batch.length < 100) break;
  }
  return issues;
}

/** GraphQL pinned issues; the REST list endpoint does not expose them. */
export async function fetchPinned(repo: string, token?: string): Promise<Set<number>> {
  if (!token) return new Set();
  const [owner, name] = repo.split('/');
  const query = `query($owner:String!,$name:String!){repository(owner:$owner,name:$name){pinnedIssues(first:100){nodes{issue{number}}}}}`;
  try {
    const res = await fetch(`${API}/graphql`, {
      method: 'POST',
      headers: { ...headers(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, variables: { owner, name } }),
    });
    if (!res.ok) return new Set();
    const json = (await res.json()) as {
      data?: { repository?: { pinnedIssues?: { nodes?: Array<{ issue: { number: number } }> } } };
    };
    const nodes = json.data?.repository?.pinnedIssues?.nodes ?? [];
    return new Set(nodes.map((node) => node.issue.number));
  } catch {
    return new Set();
  }
}
