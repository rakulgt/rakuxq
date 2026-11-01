#!/usr/bin/env node
/** Read-only analytics delivery gate. Does not send traffic, access secrets or change manifests. */
import { readFile, realpath } from 'node:fs/promises';
import { resolve, relative, isAbsolute, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const slug = /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/;
const statuses = new Set(['planned', 'configured', 'verified', 'suspended', 'exception', 'not-applicable']);
const sensitive = /password|secret|token|cookie|authorization|email|phone|content|body|text|prompt|stack/i;
function inside(root, path) {
  const rel = relative(root, path);
  return !isAbsolute(rel) && rel !== '..' && !rel.startsWith('../') && !rel.startsWith('..\\');
}
export function registeredEntries(text) {
  // Only read the documented registry id/path keys at their exact indentation.
  // Nested routing, deployment and protocol paths are deliberately ignored.
  const entries = [];
  let entry, domains = false;
  for (const line of text.split(/\r?\n/)) {
    const id = line.match(/^  - id:\s*([a-z0-9-]+)\s*$/);
    if (id) { entry = { id: id[1], domains: [] }; entries.push(entry); domains = false; }
    if (/^    \S/.test(line)) domains = /^    domains:\s*$/.test(line);
    const domain = domains && line.match(/^      -\s+([a-z0-9.-]+)\s*$/);
    if (domain && entry) entry.domains.push(domain[1]);
    const path = line.match(/^    path:\s*([^#]+?)\s*$/);
    if (path && entry) entry.path = path[1].replace(/^['"]|['"]$/g, '');
  }
  return entries.filter(entry => entry.path);
}
export function validateManifest(m, id, policy, now = Date.now()) {
  const issues = [];
  const issue = message => issues.push(message);
  if (!m || typeof m !== 'object' || Array.isArray(m)) return ['manifest must be an object'];
  if (m.schemaVersion !== 1 || !['1.0.0', '1.1.0'].includes(m.protocolVersion)) issue('unsupported manifest/protocol version');
  if (m.projectId !== id || !slug.test(m.projectId || '')) issue('project identity mismatch');
  if (!statuses.has(m.status)) issue('invalid integration status');
  if (m.environment !== 'production') issue('delivery evidence must describe production');
  if (!['basic', 'business'].includes(m.level)) issue('invalid integration level');
  if (typeof m.owner !== 'string' || !m.owner.trim() || m.owner.includes('<')) issue('metric owner required');
  if (!Array.isArray(m.sites) || !Array.isArray(m.events)) return [...issues, 'sites/events must be arrays'];
  const hosts = new Set();
  for (const site of m.sites) {
    const host = site?.hostname?.toLowerCase();
    if (typeof host !== 'string' || !/^(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}$/.test(host)) { issue('invalid hostname'); continue; }
    if ((policy.excludedHostnames || []).some(excluded => host === excluded || host.endsWith('.' + excluded))) issue('isolated hostname is excluded');
    if (Array.isArray(policy.allowedHostnames) && !policy.allowedHostnames.includes(host)) issue('hostname outside assigned project scope');
    const prefix = site.pathPrefix;
    if (typeof prefix !== 'string' || !prefix.startsWith('/') || prefix.startsWith('//') || /[?#\\\s]|(?:^|\/)\.\.?(?:\/|$)/.test(prefix)) issue('invalid path scope');
    if (hosts.has(host + prefix)) issue('duplicate site scope');
    hosts.add(host + prefix);
  }
  const names = new Set();
  for (const event of m.events) {
    if (!/^[a-z][a-z0-9_]{0,49}$/.test(event?.name || '') || names.has(event.name)) issue('invalid or duplicate event name');
    names.add(event?.name);
    if (!Number.isInteger(event?.version) || event.version < 1) issue('event version required');
    if (typeof event?.definition !== 'string' || !event.definition.trim()) issue('event definition required');
    if (!['browser', 'server', 'client'].includes(event?.source)) issue('event source required');
    if (!Array.isArray(event?.allowedProperties) || event.allowedProperties.some(key => typeof key !== 'string' || !/^[a-z][a-z0-9_]*$/.test(key) || sensitive.test(key))) issue('unsafe event property allowlist');
  }
  if (['exception', 'not-applicable'].includes(m.status)) {
    const ex = m.exception;
    if (!ex || !['approvedBy', 'approvalReference', 'reason', 'owner'].every(key => typeof ex[key] === 'string' && ex[key].trim() && !ex[key].includes('<'))) issue('explicit human exception approval required');
    if (!ex || !Number.isFinite(Date.parse(ex.reviewAt)) || Date.parse(ex.reviewAt) <= now) issue('exception review missing or expired');
  }
  if (m.status === 'verified') {
    const v = m.verification;
    const observed = Date.parse(v?.observedAt);
    if (!v || !['release', 'evidenceFile'].every(key => typeof v[key] === 'string' && v[key].trim() && !v[key].includes('<'))) issue('release and evidence file required');
    if (!Number.isFinite(observed) || observed > now + 300_000 || now - observed > policy.maxVerificationAgeDays * 86_400_000) issue('verification date missing, future or stale');
    if (v?.received !== true || v?.testTrafficExcluded !== true || v?.privacyChecked !== true || v?.accessControlChecked !== true) issue('receipt, filtering, privacy and access evidence required');
    if (!m.sites.length && !m.events.length) issue('verified integration has no measurement scope');
    if (m.level === 'business' && !m.events.length) issue('business integration has no event contract');
  }
  return issues;
}
export async function audit(root, { project, strict = false, design = false } = {}) {
  root = await realpath(root);
  const policy = JSON.parse(await readFile(resolve(root, 'registry/analytics-policy.json'), 'utf8'));
  const entries = (await Promise.all(['projects', 'services'].map(async name => registeredEntries(await readFile(resolve(root, `registry/${name}.yaml`), 'utf8'))))).flat();
  const rows = [];
  if (project && !entries.some(entry => entry.id === project)) throw new Error('unknown project id');
  for (const entry of entries.filter(entry => !project || entry.id === project)) {
    const row = { projectId: entry.id, status: 'missing', issues: [], deliveryReady: false };
    let projectRoot = resolve(root, entry.path);
    if (!inside(root, projectRoot)) throw new Error('registered project escapes workspace');
    try {
      projectRoot = await realpath(projectRoot);
      if (!inside(root, projectRoot)) throw new Error('project symlink escapes workspace');
      const path = resolve(projectRoot, policy.manifestName);
      const manifestPath = await realpath(path);
      if (!inside(projectRoot, manifestPath)) throw new Error('manifest symlink escapes project');
      const m = JSON.parse(await readFile(manifestPath, 'utf8'));
      row.status = m.status;
      row.issues = validateManifest(m, entry.id, policy);
      if (m.status === 'verified' && m.verification?.evidenceFile) {
        const evidence = await realpath(resolve(projectRoot, m.verification.evidenceFile));
        if (!inside(projectRoot, evidence)) row.issues.push('evidence escapes project');
        else if (!(await readFile(evidence, 'utf8')).trim()) row.issues.push('evidence file empty');
      }
      row.deliveryReady = !row.issues.length && ['verified', 'exception', 'not-applicable'].includes(m.status);
    } catch (error) {
      // Never print arbitrary error paths, document contents or payloads.
      row.issues.push(error.code === 'ENOENT' ? 'manifest/project/evidence missing' : 'manifest or evidence invalid');
    }
    if (strict && !design && !row.deliveryReady) row.issues.push('production delivery gate not satisfied');
    rows.push(row);
  }
  return { mode: design ? 'design-validation-only' : strict ? 'production-gate' : 'migration-audit', total: rows.length, ready: rows.filter(row => row.deliveryReady).length, rows,
    passed: strict ? rows.every(row => !row.issues.length) : true };
}
async function main() {
  const args = process.argv.slice(2);
  const options = { root: resolve(dirname(fileURLToPath(import.meta.url)), '..') };
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--project' && slug.test(args[i + 1] || '')) options.project = args[++i];
    else if (args[i] === '--strict') options.strict = true;
    else if (args[i] === '--design') options.design = true;
    else throw new Error('invalid arguments');
  }
  const result = await audit(options.root, options);
  console.log(JSON.stringify(result, null, 2));
  if (!result.passed) process.exitCode = 1;
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main().catch(() => { console.error('Analytics audit failed. Check registry, policy and arguments; details suppressed.'); process.exitCode = 1; });
