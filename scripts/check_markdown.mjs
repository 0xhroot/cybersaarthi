#!/usr/bin/env node
/* Validate Markdown hygiene across the repository (read-only).
 *
 * Checks, for every tracked *.md file:
 *   1. relative links resolve to an existing path (files and directories)
 *   2. intra-file #anchors match a real heading in the target document
 *   3. no accidental absolute local paths (e.g. /home/...) in links
 *   4. fenced ```mermaid blocks are balanced and non-empty
 *
 * Run:  node scripts/check_markdown.mjs   (or: node docs/scripts/…)
 * Exit 0 = clean; 1 = problems, each printed with file:line.
 */
import { execFileSync } from "node:child_process";
import { readFileSync, existsSync, statSync } from "node:fs";
import path from "node:path";

const ROOT = path.resolve(import.meta.dirname, "..");

let files;
try {
  files = execFileSync("git", ["ls-files", "*.md"], { cwd: ROOT, encoding: "utf8" })
    .split("\n")
    .filter(Boolean);
} catch {
  console.error("git ls-files failed — run inside a git repository");
  process.exit(1);
}

const problems = [];

function slugify(heading) {
  // Match GitHub's algorithm: lowercase, strip punctuation (keeping letters,
  // numbers, spaces, hyphens, underscores), then map EACH space to a hyphen
  // without collapsing — "Tests & evaluation" -> "tests--evaluation".
  return heading
    .trim()
    .toLowerCase()
    .replace(/[`*~]/g, "")
    .replace(/[^\p{L}\p{N}\s\-_]/gu, "")
    .replace(/ /g, "-");
}

// Collect heading slugs (including explicit {#id} and duplicate counters).
function headingSlugs(markdown) {
  const slugs = new Set();
  const seen = new Map();
  let inFence = false;
  for (const line of markdown.split("\n")) {
    if (/^\s*```/.test(line)) inFence = !inFence;
    if (inFence) continue;
    const m = /^#{1,6}\s+(.*)$/.exec(line);
    if (!m) continue;
    const explicit = /\{#([^}]+)\}\s*$/.exec(m[1]);
    if (explicit) {
      slugs.add(explicit[1]);
      continue;
    }
    const base = slugify(m[1]);
    const count = seen.get(base) ?? 0;
    seen.set(base, count + 1);
    slugs.add(count === 0 ? base : `${base}-${count}`);
  }
  return slugs;
}

const slugCache = new Map();
function slugsFor(absPath) {
  if (!slugCache.has(absPath)) {
    slugCache.set(absPath, headingSlugs(readFileSync(absPath, "utf8")));
  }
  return slugCache.get(absPath);
}

const LINK_RE = /\[[^\]]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g;

for (const rel of files) {
  const abs = path.join(ROOT, rel);
  let text;
  try {
    text = readFileSync(abs, "utf8");
  } catch {
    problems.push(`${rel}:1 unreadable file`);
    continue;
  }
  const lines = text.split("\n");

  // --- mermaid fence balance -------------------------------------------
  const fenceCount = (text.match(/```mermaid\b/g) ?? []).length;
  const closeCount = (text.match(/```\s*$/gm) ?? []).length;
  if (fenceCount > 0 && closeCount < 2 * fenceCount) {
    problems.push(`${rel}: unbalanced or unclosed \`\`\`mermaid fence(s)`);
  }
  let mermaidOpen = false;
  for (let i = 0; i < lines.length; i++) {
    if (/^\s*```mermaid\b/.test(lines[i])) {
      if (mermaidOpen) problems.push(`${rel}:${i + 1} nested \`\`\`mermaid fence`);
      mermaidOpen = true;
      const next = lines[i + 1] ?? "";
      if (/^\s*```/.test(next.trim()) || next.trim() === "") {
        problems.push(`${rel}:${i + 1} empty mermaid block`);
      }
    } else if (mermaidOpen && /^\s*```\s*$/.test(lines[i])) {
      mermaidOpen = false;
    }
  }

  // --- links ------------------------------------------------------------
  lines.forEach((line, idx) => {
    // skip fenced code so example links are not checked
    // (checked per-line is cheap and fences are tracked)
    if (/^\s*```/.test(line)) return;

    for (const m of line.matchAll(LINK_RE)) {
      const raw = m[1];
      const lineNo = idx + 1;

      if (/^(https?:|mailto:|tel:)/i.test(raw)) continue; // external: not fetched
      if (raw.startsWith("#")) {
        // intra-document anchor
        if (!slugsFor(abs).has(raw.slice(1).toLowerCase())) {
          problems.push(`${rel}:${lineNo} broken intra-doc anchor ${raw}`);
        }
        continue;
      }
      if (raw.startsWith("/home/") || raw.startsWith("file:")) {
        problems.push(`${rel}:${lineNo} absolute local path in link: ${raw}`);
        continue;
      }

      const [target, anchor] = raw.split("#");
      const targetAbs = path.resolve(path.dirname(abs), decodeURIComponent(target));

      if (target === "") continue; // pure anchor handled above
      if (!existsSync(targetAbs)) {
        problems.push(`${rel}:${lineNo} missing target: ${raw}`);
        continue;
      }
      if (anchor && statSync(targetAbs).isFile() && targetAbs.endsWith(".md")) {
        if (!slugsFor(targetAbs).has(anchor.toLowerCase())) {
          problems.push(`${rel}:${lineNo} broken anchor: ${raw}`);
        }
      }
      if (anchor && statSync(targetAbs).isDirectory()) {
        const readme = path.join(targetAbs, "README.md");
        if (!existsSync(readme)) {
          problems.push(`${rel}:${lineNo} directory link with anchor but no README.md: ${raw}`);
        } else if (!slugsFor(readme).has(anchor.toLowerCase())) {
          problems.push(`${rel}:${lineNo} broken anchor: ${raw}`);
        }
      }
    }
  });
}

console.log(`checked ${files.length} markdown files`);
if (problems.length) {
  console.log(`\n${problems.length} problem(s):`);
  for (const p of problems) console.log(`  ${p}`);
  process.exit(1);
}
console.log("links, anchors and mermaid fences: OK");
