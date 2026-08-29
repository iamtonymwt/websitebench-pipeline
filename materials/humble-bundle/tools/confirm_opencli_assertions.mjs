/**
 * Independent confirmation that the derived OpenCLI contract's assertions hold
 * against the running clone.
 *
 * The official replay path (`websitebench-harbor run-opencli`) records
 * `opencli-unavailable` on this machine because the `opencli` binary is not
 * installed. That is a sanctioned outcome, but it leaves the derived
 * assertions unconfirmed. This script evaluates each step's `required_state`
 * directly over plain HTTP with the same matching rules the adapters use
 * (`visible` / `list_contains` / `link_text` / `text_absent` compare rendered
 * text with tags stripped and entities decoded; `body_contains` compares raw
 * markup minus script and style bodies). Diagnostic only.
 *
 * Usage: node confirm_opencli_assertions.mjs [baseUrl]
 */
import { readFileSync } from 'node:fs';

const BASE = process.argv[2] || 'http://127.0.0.1:8098';
const CONTRACT = 'harbor/sites/humble-bundle/interactions/opencli-interaction-contract.json';
const TEXT_KEYS = new Set(['visible', 'list_contains', 'link_text', 'text_absent']);

const ENTITIES = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ', '#39': "'" };

function decodeEntities(value) {
  return value.replace(/&(#?\w+);/g, (whole, name) =>
    Object.prototype.hasOwnProperty.call(ENTITIES, name) ? ENTITIES[name] : whole);
}

function stripScriptsAndStyles(html) {
  return html
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '<script></script>')
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, '<style></style>');
}

function renderedText(html) {
  return decodeEntities(stripScriptsAndStyles(html).replace(/<[^>]+>/g, ' '))
    .replace(/\s+/g, ' ')
    .trim();
}

const contract = JSON.parse(readFileSync(CONTRACT, 'utf8'));
const routes = contract.routes || {};
let checked = 0;
let failed = 0;
const failures = [];

for (const [profileId, profile] of Object.entries(contract.profiles)) {
  for (const step of profile.steps || []) {
    const route = routes[step.route] ?? `/${step.route}`;
    const url = BASE + (typeof route === 'string' ? route : route.path);
    const response = await fetch(url, { redirect: 'manual' });
    const body = await response.text();
    const text = renderedText(body);
    const markup = stripScriptsAndStyles(body);
    for (const [key, expected] of Object.entries(step.required_state || {})) {
      checked += 1;
      let ok;
      if (key === 'text_absent') ok = !text.includes(expected);
      else if (TEXT_KEYS.has(key)) ok = text.includes(expected);
      else if (key === 'body_contains') ok = markup.includes(expected);
      else if (key === 'title') ok = renderedText((body.match(/<title[^>]*>([\s\S]*?)<\/title>/i) || [, ''])[1]).includes(expected);
      else { ok = null; }
      if (ok === false) {
        failed += 1;
        failures.push(`${profileId}/${step.id} ${key}: ${JSON.stringify(expected)} (status ${response.status})`);
      }
    }
  }
}

console.log(JSON.stringify({
  authority: 'diagnostic-only',
  base_url: BASE,
  assertions_checked: checked,
  assertions_failed: failed,
  failures,
}, null, 1));
process.exit(0);
