const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '../contact.html'), 'utf8');
const code = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].at(-1)[1];
function setup(fetchImpl, valid = true, bot = false) {
  let handler, resets = 0, calls = 0;
  const button = { disabled: false, textContent: '送信する' };
  const result = { hidden: true, textContent: '' };
  const values = { name: '送信テスト', email: 'test@example.com', message: '検証用入力', privacy_agree: 'yes' };
  const form = { action: 'https://api.web3forms.com/submit', elements: { botcheck: { checked: bot } },
    querySelector: () => button, reportValidity: () => valid,
    addEventListener: (_, fn) => handler = fn, setAttribute() {}, removeAttribute() {},
    reset() { resets++; for (const k of Object.keys(values)) values[k] = ''; } };
  const timers = new Set();
  vm.runInNewContext(code, {
    document: { forms: { 'influenza-radar-contact': form }, getElementById: () => result },
    FormData: class { constructor() { return Object.entries(values); } }, AbortController,
    setTimeout: (fn) => { timers.add(fn); return fn; }, clearTimeout: (fn) => timers.delete(fn),
    fetch: async (...args) => { calls++; return fetchImpl(...args); }
  });
  return { submit: () => handler({ preventDefault() {} }), button, result, values,
    get resets() { return resets; }, get calls() { return calls; }, timers };
}
test('success resets only after a successful API response', async () => {
  const s = setup(async (url, options) => { assert.equal(url, 'https://api.web3forms.com/submit'); assert.equal(options.method, 'POST'); assert.equal(JSON.parse(options.body).message, '検証用入力'); return { ok: true, json: async () => ({ success: true }) }; });
  await s.submit(); assert.equal(s.resets, 1); assert.match(s.result.textContent, /送信しました/); assert.equal(s.button.disabled, false); assert.equal(s.timers.size, 0);
});
for (const [name, response] of [
  ['HTTP error', async () => ({ ok: false, json: async () => ({ success: false }) })],
  ['API rejection', async () => ({ ok: true, json: async () => ({ success: false }) })],
  ['network failure', async () => { throw new TypeError('offline'); }],
  ['invalid JSON', async () => ({ ok: true, json: async () => { throw new SyntaxError(); } })],
  ['missing success flag', async () => ({ ok: true, json: async () => ({}) })]
]) test(name + ' preserves inputs', async () => { const s = setup(response); await s.submit(); assert.equal(s.resets, 0); assert.equal(s.values.message, '検証用入力'); assert.equal(s.values.privacy_agree, 'yes'); assert.equal(s.button.disabled, false); assert.match(s.result.textContent, /保持/); });
test('invalid input and honeypot prevent requests', async () => {
  for (const [valid, bot] of [[false, false], [true, true]]) { const s = setup(async () => { throw Error(); }, valid, bot); await s.submit(); assert.equal(s.calls, 0); assert.equal(s.resets, 0); }
});
test('double submission sends only one request', async () => {
  let release; const s = setup(() => new Promise(resolve => release = resolve)); const pending = s.submit(); await s.submit(); assert.equal(s.calls, 1); assert.equal(s.button.disabled, true); release({ok:true,json:async()=>({success:true})}); await pending;
});
test('timeout aborts and preserves input', async () => {
  const s = setup((url, options) => new Promise((resolve, reject) => options.signal.addEventListener('abort', () => reject(Error('timeout')))));
  const pending = s.submit(); for (const timer of s.timers) timer(); await pending; assert.equal(s.resets,0); assert.equal(s.values.message,'検証用入力'); assert.equal(s.button.disabled,false);
});
