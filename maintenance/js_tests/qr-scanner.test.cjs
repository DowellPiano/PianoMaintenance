const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('maintenance/static/js/qr-scanner.js', 'utf8');

function setup(value, getCamera) {
  const elements = {};
  let stops = 0;
  const navigations = [];
  const camera = { getTracks: () => [{ stop: () => stops++ }] };
  for (const id of ['qr-scanner', 'qr-scanner-video', 'qr-scanner-status', 'qr-scanner-retry', 'scan-code', 'qr-scanner-close']) {
    elements[id] = {
      handlers: {}, dataset: {},
      addEventListener(name, fn) { this.handlers[name] = fn; },
      showModal() { this.open = true; },
      close() { this.open = false; this.handlers.close(); },
      play: async () => {}, readyState: 2, videoWidth: 640, videoHeight: 480,
    };
  }
  const document = {
    getElementById: id => elements[id], addEventListener() {},
    createElement: () => ({ getContext: () => ({ drawImage() {}, getImageData: () => ({ data: [], width: 640, height: 480 }) }) }),
    head: { appendChild: script => script.onload() },
  };
  vm.runInNewContext(source, {
    document, URL, setTimeout: () => 1, clearTimeout() {},
    navigator: { mediaDevices: { getUserMedia: getCamera || (async () => camera) } },
    window: { isSecureContext: true, location: { origin: 'https://pianos.example', assign: path => navigations.push(path) },
      jsQR: () => ({ data: value }), addEventListener() {} },
  });
  return { elements, camera, navigations, stops: () => stops,
    open: () => elements['scan-code'].handlers.click(),
    close: () => elements['qr-scanner-close'].handlers.click() };
}
const settle = () => new Promise(resolve => setImmediate(resolve));

test('existing label navigates in the same window and stops camera', async () => {
  const path = '/maintenance_request/12345678-1234-1234-1234-123456789abc/';
  const app = setup('https://pianos.example' + path);
  app.open(); await settle();
  assert.deepEqual(app.navigations, [path]);
  assert.equal(app.stops(), 1);
});

test('unrelated URLs never navigate and scanning can be closed', async () => {
  for (const value of ['https://evil.example/pianos/1/', 'javascript:alert(1)', '/logout/', 'not a URL']) {
    const app = setup(value);
    app.open(); await settle();
    assert.deepEqual(app.navigations, []);
    assert.match(app.elements['qr-scanner-status'].textContent, /not a piano/);
    app.close(); assert.equal(app.stops(), 1);
  }
});

test('closing while permission is pending releases the eventual stream', async () => {
  let resolve;
  const app = setup('/pianos/1/', () => new Promise(r => { resolve = r; }));
  app.open(); app.close(); resolve(app.camera); await settle();
  assert.equal(app.stops(), 1);
  assert.deepEqual(app.navigations, []);
});

test('permission denial offers retry', async () => {
  const app = setup('', async () => { throw Object.assign(new Error(), { name: 'NotAllowedError' }); });
  app.open(); await settle();
  assert.match(app.elements['qr-scanner-status'].textContent, /blocked/);
  assert.equal(app.elements['qr-scanner-retry'].hidden, false);
});
