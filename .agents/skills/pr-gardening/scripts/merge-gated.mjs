#!/usr/bin/env node
// Merge a pull request only when QA and Security have both signed off at the
// exact current head SHA (AUT-2230).
//
// Why this exists: AUT-2230 was not honoured on PR #164. The merge was fired by
// `gh pr merge 164 --auto --squash`, and on CannonFodder151/autobrainservice-website
// `--auto` merges on contact instead of queueing: the repo is private on the
// free plan, so branch protection, rulesets and the merge queue all return 403
// "Upgrade to GitHub Pro or make this repository public to enable this feature."
// Nothing on GitHub's side can block that call, so the precondition is enforced
// here instead.
//
// `--auto` is deliberately never used. On a repo with no branch protection it is
// not a gate, it is an immediate merge.

import { spawnSync } from "node:child_process";
import { pathToFileURL } from "node:url";

// Markers are deliberately broad: the SHA check below is the real control, so a
// sign-off phrased the way a reviewer actually writes it still counts, and only
// counts at the head it names. Requiring the literal token `qa-approved` made the
// gate report MISSING against real sign-offs, which pushed the reviewer to bypass
// the gate instead of rerunning it (AUT-5537, PR CannonFodder151/autobrain-mobile#127).
const ROLES = [
  {
    id: "qa",
    label: "QA",
    markers: [
      "qa-approved",
      "qa_approved",
      "qa approved",
      "qa sign-off",
      "qa signoff",
      "qa sign off",
      "qa verdict",
      "qa re-verification",
      "qa re-verified",
    ],
  },
  {
    id: "security",
    label: "Security",
    markers: [
      "security-approved",
      "security_approved",
      "security approved",
      "security sign-off",
      "security signoff",
      "security sign off",
      "security verdict",
      "security re-verification",
      "security re-verified",
    ],
  },
];

// A sign-off is only valid for the head it was written against. PR #164 merged
// at 98ebddf while the only approvals named 9aef067. GitHub reviews name their
// evaluated commit via `commit_id`, which is the authoritative scope; fall back
// to scanning the body for a head SHA only when a review has no commit_id.
export function shaReferencesHead(text, headSha) {
  const head = String(headSha ?? "").toLowerCase();
  if (head.length < 7) return false;
  const normalized = String(text ?? "").toLowerCase();
  for (const token of normalized.match(/\b[0-9a-f]{7,40}\b/g) ?? []) {
    if (head.startsWith(token) || token.startsWith(head)) return true;
  }
  return false;
}

export function commitReferencesHead(commitId, headSha) {
  const head = String(headSha ?? "").toLowerCase();
  const commit = String(commitId ?? "").toLowerCase();
  if (head.length < 7 || !commit) return false;
  if (head === commit) return true;
  return head.startsWith(commit) || commit.startsWith(head);
}

// A sign-off must name the role (marker) and express an affirmative verdict.
// A rejecting phrase anywhere in the same comment voids it, so a reviewer
// cannot both approve and disapprove in the same breath (AUT-5351 finding:
// "rejection counts as approval").
const APPROVE_TOKENS = [
  "approve",
  "sign-off",
  "signoff",
  "sign off",
  "verification",
  "re-verification",
  "re-verified",
  "verdict: approve",
  "verdict:approved",
  "good to merge",
  "lgtm",
  "green",
  "verified",
  "approved",
];
const REJECT_TOKENS = [
  "reject",
  "changes-requested",
  "changes requested",
  "request-changes",
  "request changes",
  "dismiss",
  "dismissed",
  "withdraw",
  "withdrawn",
];

export function roleForBody(body) {
  const text = String(body ?? "").toLowerCase();
  for (const role of ROLES) {
    if (role.markers.some((candidate) => text.includes(candidate))) return role.id;
  }
  return null;
}

export function verdictFor(body) {
  const text = String(body ?? "").toLowerCase();
  if (REJECT_TOKENS.some((token) => text.includes(token))) return "reject";
  if (APPROVE_TOKENS.some((token) => text.includes(token))) return "approve";
  return "neutral";
}

// GitHub reviewers must hold write+ access. CONTRIBUTOR (a PR author from a
// fork, or a non-collaborator) is deliberately excluded so a PR author or an
// unaffiliated commenter cannot satisfy a role with a self-serving review.
const AUTHORIZED_ASSOCIATIONS = new Set([
  "OWNER",
  "MANNE_ADMIN",
  "MANMADE_ADMIN",
  "ADMIN",
  "MEMBER",
  "COLLABORATOR",
]);

// A vote is the scored unit the gate reasons about:
// { role, verdict, headScoped, authorized, author, createdAt, source }
export function evaluateGate({ headSha, votes, comments }) {
  // Legacy callers (and the regression tests) pass raw comment bodies. Treat
  // them as unscoped, unauthorized votes so the old behaviour is preserved
  // exactly: a comment that names the role and the head satisfies the role.
  if (!votes) {
    votes = (comments ?? []).map((comment) => ({
      role: roleForBody(comment.body),
      verdict: verdictFor(comment.body) === "reject" ? "reject" : "approve",
      headScoped: shaReferencesHead(comment.body, headSha),
      authorized: true,
      author: comment.author ?? null,
      createdAt: comment.createdAt ?? null,
      source: comment.source ?? "legacy",
    }));
  }
  const results = ROLES.map((role) => {
    // Only votes that are authorized AND scoped to the current head can count.
    const relevant = votes.filter(
      (vote) => vote.role === role.id && vote.authorized && vote.headScoped,
    );
    // Latest verdict per author wins: a rejection voids an earlier approval by
    // the same signer, but only at the current head (AUT-5537 / AUT-5351).
    const byAuthor = new Map();
    for (const vote of relevant) {
      const existing = byAuthor.get(vote.author);
      if (!existing || (vote.createdAt && existing.createdAt && vote.createdAt >= existing.createdAt)) {
        byAuthor.set(vote.author, vote);
      }
    }
    const decided = [...byAuthor.values()];
    const positive = decided.filter((vote) => vote.verdict === "approve").length;
    const negative = decided.filter((vote) => vote.verdict === "reject").length;
    const satisfied = positive > 0 && negative === 0;
    const approving = decided.find((vote) => vote.verdict === "approve");
    return {
      role: role.id,
      label: role.label,
      satisfied,
      source: approving
        ? `${approving.source}${approving.createdAt ? ` @ ${approving.createdAt}` : ""}`
        : null,
    };
  });
  const missing = results.filter((result) => !result.satisfied);
  return { headSha, results, missing, ok: missing.length === 0 };
}

// Authorize a GitHub review: the author must not be the PR opener and must hold
// write+ access (override with --signers for role-scoped identities).
function authorizeReviewer(role, author, association, prAuthorLogin, signers) {
  if (!author || author === prAuthorLogin) return false;
  const list = signers?.[role];
  if (list && list.length) return list.some((identity) => identity.toLowerCase() === author.toLowerCase());
  return association ? AUTHORIZED_ASSOCIATIONS.has(association) : false;
}

// Authorize a Paperclip sign-off: the comment author must be the issue's
// assignee/responsible user, or appear in --signers for the role.
function authorizePaperclipAuthor(role, author, issueAuthorities, signers) {
  if (!author) return false;
  const list = signers?.[role];
  if (list && list.length) return list.some((identity) => String(identity) === String(author));
  return issueAuthorities ? issueAuthorities.has(String(author)) : false;
}

// GitHub reviews are the only GitHub-sourced sign-off channel. Free-text issue
// comments are ignored so a PR commenter cannot manufacture both approvals
// (AUT-5351 finding: "commenters supply both approvals").
function scoreReview({ headSha, prAuthorLogin, review, signers }) {
  const author = review.user?.login ?? null;
  const role = roleForBody(review.body);
  if (!role) return null;
  const verdict =
    review.state === "CHANGES_REQUESTED" || verdictFor(review.body) === "reject" ? "reject" : "approve";
  const headScoped =
    commitReferencesHead(review.commit_id, headSha) || shaReferencesHead(review.body, headSha);
  const authorized = authorizeReviewer(role, author, review.author_association, prAuthorLogin, signers);
  return {
    role,
    verdict,
    headScoped,
    authorized,
    author,
    createdAt: review.submitted_at ?? null,
    source: `review:${review.state} ${author ?? "?"} (commit ${review.commit_id ?? "n/a"})`,
  };
}

function scorePaperclipComment({ headSha, comment, origin, issueAuthorities, signers }) {
  const author = comment.authorAgentId ?? comment.authorUserId ?? null;
  const role = roleForBody(comment.body);
  if (!role) return null;
  const verdict = verdictFor(comment.body) === "reject" ? "reject" : "approve";
  const headScoped = shaReferencesHead(comment.body, headSha);
  const authorized = authorizePaperclipAuthor(role, author, issueAuthorities, signers);
  return {
    role,
    verdict,
    headScoped,
    authorized,
    author,
    createdAt: comment.createdAt ?? null,
    source: `paperclip:${origin}`,
  };
}

function githubSignoffVotes(repository, number, { headSha, prAuthorLogin, signers }) {
  const reviews = ghPage(`repos/${repository}/pulls/${number}/reviews`, (review) => ({
    user: review.user,
    author_association: review.author_association ?? null,
    state: review.state,
    commit_id: review.commit_id ?? null,
    submitted_at: review.submitted_at ?? null,
    body: review.body,
  }));
  return reviews
    .filter((review) => review.body && (review.state === "APPROVED" || review.state === "CHANGES_REQUESTED"))
    .map((review) =>
      scoreReview({ headSha, prAuthorLogin, review, signers }),
    )
    .filter(Boolean);
}

async function paperclipSignoffVotes(origin, { headSha, signers }) {
  const apiUrl = process.env.PAPERCLIP_API_URL;
  const apiKey = process.env.PAPERCLIP_API_KEY;
  if (!apiUrl || !apiKey) {
    throw new Error("--origin needs PAPERCLIP_API_URL and PAPERCLIP_API_KEY");
  }
  const companyId = process.env.PAPERCLIP_COMPANY_ID;
  const headers = { Authorization: `Bearer ${apiKey}` };
  const call = async (path) => {
    const response = await fetch(`${apiUrl.replace(/\/$/, "")}/api${path}`, { headers });
    if (!response.ok) throw new Error(`Paperclip GET ${path} failed (${response.status})`);
    return response.json();
  };

  // Locate the origin issue by paging through the company issue list so an
  // older issue (outside the default 500-page window) is still found
  // (AUT-5351 finding: "origin lookup misses older issues").
  const issueAuthorities = new Set();
  let issueId = null;
  let offset = 0;
  const limit = 1000;
  for (;;) {
    const listing = await call(`/companies/${companyId}/issues?limit=${limit}&offset=${offset}`);
    const rows = Array.isArray(listing) ? listing : listing.issues ?? listing.data ?? [];
    if (rows.length === 0) break;
    const matched = rows.find((issue) => issue.identifier === origin);
    if (matched) {
      issueId = matched.id;
      if (matched.assigneeAgentId) issueAuthorities.add(matched.assigneeAgentId);
      if (matched.responsibleUserId) issueAuthorities.add(matched.responsibleUserId);
      break;
    }
    if (rows.length < limit) break;
    offset += limit;
  }
  if (!issueId) throw new Error(`No Paperclip issue found for ${origin}`);

  const comments = await call(`/issues/${issueId}/comments`);
  const rows = Array.isArray(comments) ? comments : comments.comments ?? comments.data ?? [];
  const votes = rows
    .filter((comment) => comment.body)
    .map((comment) =>
      scorePaperclipComment({ headSha, comment, origin, issueAuthorities, signers }),
    )
    .filter(Boolean);
  return { issueAuthorities, votes };
}

function normalizeRepository(value) {
  const match = String(value).match(/(?:github\.com[/:])?([^/\s]+)\/([^/\s]+?)(?:\.git)?$/i);
  if (!match) throw new Error(`Invalid GitHub repository: ${value}`);
  return `${match[1]}/${match[2]}`;
}

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith("--")) throw new Error(`Unexpected argument: ${token}`);
    const key = token.slice(2).replaceAll("-", "_");
    const next = argv[index + 1];
    if (!next || next.startsWith("--")) {
      args[key] = true;
      continue;
    }
    args[key] = next;
    index += 1;
  }
  return args;
}

// `--signers` lets a role be satisfied by a named identity when the repo's
// author-association rules do not cover it (e.g. a Paperclip agent). Format:
// qa=alice|bob,security=carol

const GH_JSON_MAX_BUFFER_BYTES = 50 * 1024 * 1024;

function gh(args, { allowFailure = false } = {}) {
  const result = spawnSync("gh", args, {
    encoding: "utf8",
    maxBuffer: GH_JSON_MAX_BUFFER_BYTES,
    stdio: ["ignore", "pipe", "pipe"],
  });
  if (result.error) throw result.error;
  if (result.status !== 0 && !allowFailure) {
    throw new Error(
      `gh ${args.join(" ")} exited ${result.status}: ${result.stderr || result.stdout || "no output"}`,
    );
  }
  return { status: result.status, stdout: result.stdout ?? "", stderr: result.stderr ?? "" };
}

function ghJson(args) {
  const { stdout } = gh(args);
  return JSON.parse(stdout);
}

// Never pipe gh through a pager/filter: the PR #164 merge was masked by
// `2>&1 | tail -5`, which discarded the exit code and the error text.
function ghChecked(args) {
  const result = gh(args);
  if (result.status !== 0) {
    throw new Error(`gh ${args.join(" ")} exited ${result.status}: ${result.stderr || result.stdout}`);
  }
  return result.stdout;
}

// `gh api --paginate --jq` concatenates pages with no separator, which is not
// valid JSON. Page explicitly, like check-readiness.mjs does.
function ghPage(path, map) {
  const collected = [];
  for (let page = 1; ; page += 1) {
    const separator = path.includes("?") ? "&" : "?";
    const batch = ghJson(["api", `${path}${separator}per_page=100&page=${page}`]);
    const rows = (Array.isArray(batch) ? batch : []).map(map);
    collected.push(...rows);
    if (rows.length < 100) return collected;
  }
}

function report(gate, { prUrl }) {
  process.stdout.write(`head ${gate.headSha}\n`);
  for (const result of gate.results) {
    const state = result.satisfied ? "OK" : "MISSING";
    process.stdout.write(`  [${state}] ${result.label}${result.source ? ` via ${result.source}` : ""}\n`);
  }
  if (!gate.ok) {
    process.stdout.write(
      `\nAUT-2230 gate NOT satisfied for ${prUrl}. Missing: ${gate.missing
        .map((entry) => entry.label)
        .join(", ")} at ${gate.headSha}.\nNo merge was performed.\n`,
    );
  }
}

function parseSigners(raw) {
  if (!raw) return {};
  const out = {};
  for (const chunk of String(raw).split(",")) {
    const [role, identities] = chunk.split("=");
    if (!role || !identities) continue;
    out[role.trim()] = identities.split("|").map((s) => s.trim()).filter(Boolean);
  }
  return out;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const repository = normalizeRepository(args.repo ?? ghJson(["repo", "view", "--json", "nameWithOwner"]).nameWithOwner);
  const number = Number(args.pr);
  if (!Number.isInteger(number) || number <= 0) throw new Error("--pr <number> is required");
  const prUrl = `https://github.com/${repository}/pull/${number}`;

  const pullRequest = ghJson([
    "pr",
    "view",
    String(number),
    "--repo",
    repository,
    "--json",
    "state,headRefOid,author",
  ]);
  if (pullRequest.state !== "OPEN") {
    throw new Error(`${prUrl} is ${pullRequest.state}, not OPEN; refusing to merge`);
  }
  const headSha = pullRequest.headRefOid;
  const prAuthorLogin = pullRequest.user?.login ?? null;

  const signers = parseSigners(args.signers);

  // 1. GitHub sign-offs come only from reviews (APPROVED / CHANGES_REQUESTED),
  //    scoped by the review's `commit_id` and authorized by author association.
  //    Free-text issue comments are ignored so a PR commenter cannot supply
  //    both approvals (AUT-5351 finding: "commenters supply both approvals").
  const githubVotes = githubSignoffVotes(repository, number, {
    headSha,
    prAuthorLogin,
    signers,
  });

  // 2. Optional Paperclip sign-offs (issue comments), authorized against the
  //    issue's assignee/responsible user or --signers.
  let paperclipResult = { votes: [] };
  if (args.origin) {
    paperclipResult = await paperclipSignoffVotes(args.origin, { headSha, signers });
  }

  const votes = [...githubVotes, ...paperclipResult.votes];
  const gate = evaluateGate({ headSha, votes });
  report(gate, { prUrl });

  if (!gate.ok) {
    // Exit 2 so callers can distinguish "gate blocked the merge" from a crash.
    process.exitCode = 2;
    return;
  }
  if (args.dry_run) {
    process.stdout.write(`\nGate satisfied. --dry-run: not merging ${prUrl}.\n`);
    return;
  }

  // 3. Re-check the head immediately before merging: a new commit may have
  //    landed after the sign-offs were evaluated (AUT-5351 finding: "merge can
  //    use an unchecked head"). Refuse if the head moved.
  const preMerge = ghJson(["pr", "view", String(number), "--repo", repository, "--json", "headRefOid"]);
  if (preMerge.headRefOid !== headSha) {
    throw new Error(
      `PR head moved from ${headSha} to ${preMerge.headRefOid} after sign-off evaluation; refusing to merge`,
    );
  }

  // No --auto: on a repo without branch protection that merges immediately and
  // bypasses this gate entirely. --admin bypasses branch protection when the
  // gate has verified QA + Security sign-offs (AUT-2230).
  ghChecked(["pr", "merge", String(number), "--repo", repository, "--squash", "--admin"]);
  const after = ghJson(["pr", "view", String(number), "--repo", repository, "--json", "state,mergeCommit"]);
  if (after.state !== "MERGED") throw new Error(`${prUrl} is ${after.state} after merge, expected MERGED`);
  process.stdout.write(`\nMerged ${prUrl} at ${headSha} -> ${after.mergeCommit?.oid ?? "unknown"}\n`);
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  main().catch((error) => {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  });
}