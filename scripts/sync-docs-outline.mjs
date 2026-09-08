import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';

const DOCS_DIR = path.resolve('docs');
const DOCS_JSON = path.join(DOCS_DIR, 'docs.json');

const { OUTLINE_API_TOKEN, OUTLINE_API_URL } = process.env;
if (!OUTLINE_API_TOKEN || !OUTLINE_API_URL) {
  console.error('OUTLINE_API_TOKEN and OUTLINE_API_URL required');
  process.exit(1);
}

const HEADERS = {
  Authorization: `Bearer ${OUTLINE_API_TOKEN}`,
  'Content-Type': 'application/json',
};

async function outlineFetch(endpoint, options = {}) {
  const url = `${OUTLINE_API_URL}${endpoint}`;
  let lastError;
  for (let attempt = 0; attempt < 5; attempt++) {
    await new Promise((r) => setTimeout(r, 800));
    try {
      const res = await fetch(url, { ...options, headers: { ...HEADERS, ...(options.headers || {}) } });
      if (!res.ok) {
        const text = await res.text();
        if (res.status === 429 && attempt < 4) {
          const wait = Math.min(3000 * (attempt + 1), 30000);
          console.log(`  rate limited, waiting ${wait}ms...`);
          await new Promise((r) => setTimeout(r, wait));
          continue;
        }
        throw new Error(`Outline API ${res.status}: ${text}`);
      }
      if (res.status === 204) return null;
      return await res.json();
    } catch (err) {
      lastError = err;
      if (err.message?.includes('429') && attempt < 4) {
        const wait = Math.min(3000 * (attempt + 1), 30000);
        await new Promise((r) => setTimeout(r, wait));
        continue;
      }
      throw err;
    }
  }
  throw lastError;
}

async function getCollection() {
  const result = await outlineFetch('/api/collections.list', { method: 'POST', body: '{}' });
  const collections = result.data || [];
  return (
    collections.find((c) => c.name === 'Paperclip' || c.name === 'AutoBrain') ||
    collections.find((c) => c.name.toLowerCase().includes('autobrain')) ||
    collections[0]
  );
}

async function listExistingDocs(collectionId) {
  const result = await outlineFetch('/api/documents.list', {
    method: 'POST',
    body: JSON.stringify({ collectionId, limit: 100 }),
  });
  const all = result.data || [];
  let offset = 100;
  while (offset < (result.total || all.length)) {
    const r2 = await outlineFetch('/api/documents.list', {
      method: 'POST',
      body: JSON.stringify({ collectionId, limit: 100, offset }),
    });
    if (r2.data && r2.data.length) {
      all.push(...r2.data);
      offset += r2.data.length;
    } else {
      break;
    }
  }
  return all;
}

function buildMaps(docs) {
  const parentIdMap = {};
  const docKeyMap = {};

  for (const d of docs) {
    if (!d.parentDocumentId) {
      parentIdMap[d.title] = d.id;
    } else {
      const key = `${d.parentDocumentId}:${d.title}`;
      docKeyMap[key] = d.id;
    }
  }
  return { parentIdMap, docKeyMap };
}

function truncateTitle(title, maxLen = 95) {
  if (title.length <= maxLen) return title;
  return title.substring(0, maxLen - 3) + '...';
}

async function upsertDoc(
  collectionId,
  title,
  markdown,
  parentTitle = null,
  parentIdMap = {},
  docKeyMap = {}
) {
  const docTitle = truncateTitle(title);
  const parentId = parentTitle ? parentIdMap[parentTitle] || null : null;
  const docKey = `${parentId}:${docTitle}`;
  const docId = docKeyMap[docKey] || null;

  const payload = { title: docTitle, text: markdown, collectionId };
  if (parentId) {
    payload.parentDocumentId = parentId;
  }

  if (docId) {
    payload.id = docId;
    await outlineFetch('/api/documents.update', { method: 'POST', body: JSON.stringify(payload) });
    console.log(`  updated: ${docTitle}`);
    return docId;
  }

  const result = await outlineFetch('/api/documents.create', { method: 'POST', body: JSON.stringify(payload) });
  const newId = result?.data?.id;
  if (newId) {
    docKeyMap[docKey] = newId;
  }
  console.log(`  created: ${docTitle}`);
  return newId;
}

async function docsJsonToPages() {
  const raw = await fsp.readFile(DOCS_JSON, 'utf8');
  const config = JSON.parse(raw);
  const pages = [];
  for (const tab of config.navigation?.tabs || []) {
    for (const group of tab.groups || []) {
      for (const pageRef of group.pages || []) {
        const mdPath = path.join(DOCS_DIR, pageRef + '.md');
        pages.push({ tab: tab.tab, group: group.group, ref: pageRef, path: mdPath });
      }
    }
  }
  return pages;
}

function parseFrontmatter(content) {
  if (!content.startsWith('---')) return null;
  const closeIdx = content.indexOf('---', 3);
  if (closeIdx <= 0) return null;
  const fmText = content.slice(3, closeIdx);
  const body = content.slice(closeIdx + 3).trim();
  const titleMatch = fmText.match(/^title:\s*(.+)$/m);
  const title = titleMatch ? titleMatch[1].trim().replace(/^['"]|['"]$/g, '') : null;
  return { title, body };
}

async function syncFile(mdPath) {
  const content = await fsp.readFile(mdPath, 'utf8');
  let title = null;
  let body = content;

  const fm = parseFrontmatter(content);
  if (fm) {
    title = fm.title;
    body = fm.body;
  }

  if (!title) {
    const headingMatch = body.match(/^#\s+(.+)$/m);
    if (headingMatch) title = headingMatch[1].trim();
  }

  if (!title) {
    title = path.basename(mdPath, '.md')
      .replace(/-/g, ' ')
      .replace(/\b\w/g, (c) => c.toUpperCase());
  }

  return { title, body: body.trim() };
}

async function main() {
  console.log('Loading docs map...');
  const pages = await docsJsonToPages();
  console.log(`Found ${pages.length} pages in docs.json`);

  const collection = await getCollection();
  console.log(`Outline collection: ${collection.name} (${collection.id})`);

  const existingDocs = await listExistingDocs(collection.id);
  const { parentIdMap, docKeyMap } = buildMaps(existingDocs);

  const tabParentMap = { Testing: 'Testing & QA' };
  const synced = [];
  const failed = [];

  for (const page of pages) {
    try {
      const { title, body } = await syncFile(page.path);
      const intendedParent = tabParentMap[page.tab] || page.tab;
      await upsertDoc(collection.id, title, body, intendedParent, parentIdMap, docKeyMap);
      synced.push({ ref: page.ref, title });
    } catch (err) {
      console.error(`  FAILED ${page.ref}: ${err.message}`);
      failed.push(page.ref);
    }
  }

  console.log(`\nSynced ${synced.length}/${pages.length} pages`);
  if (failed.length > 0) {
    console.log(`Failed pages: ${failed.join(', ')}`);
    process.exit(1);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
