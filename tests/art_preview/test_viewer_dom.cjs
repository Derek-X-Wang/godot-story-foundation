'use strict';
// Controlled DOM/Image scheduling regression, NOT a real-browser/rendering test.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const P = require('../../tools/art/preview/viewer.js');
const source = fs.readFileSync(path.join(__dirname, '../../tools/art/preview/viewer.js'), 'utf8');

function fixture() {
  const elements = {}, handlers = {}, images = [], ticks = [];
  for (const id of ['play', 'output', 'direct', 'canvas', 'position', 'feedback', 'copy',
    'identity', 'assets', 'tags', 'error', 'title', 'scale', 'prev', 'next', 'notes']) {
    elements[id] = {
      value: id === 'scale' ? '1' : '', textContent: '', disabled: false, width: 0, style: {},
      removeAttribute(key) { delete this[key]; }, add() {}, replaceChildren() {},
      getContext() { return {drawImage(image) { elements.canvas.lastDrawn = image.src; }}; },
    };
  }
  const assets = ['a', 'b'].map(asset_id => ({
    asset_id, version: asset_id.repeat(64), kind: 'animation', label: asset_id,
    width: 10, height: 10, image: asset_id + '.png',
    atlas: {tags: [{name: 'idle', start: 0, count: 2, durations_ms: [100, 200], loop: true}],
      frames: [{rect: [0, 0, 10, 10]}, {rect: [0, 0, 10, 10]}]},
  }));
  const context = {
    document: {getElementById: id => elements[id], addEventListener() {}},
    window: {PREVIEW: {title: 'Test', assets}, addEventListener: (name, fn) => { handlers[name] = fn; }},
    location: {hash: ''}, URLSearchParams, Option: class {}, performance: {now: () => 0},
    requestAnimationFrame: fn => ticks.push(fn),
    Image: class { constructor() { images.push(this); this.complete = false; this.naturalWidth = 0; } },
  };
  vm.runInNewContext(source, context);
  return {
    elements, images,
    load(index) { const image = images[index]; image.complete = true; image.naturalWidth = 10; image.onload(); },
    navigate(hash) { context.location.hash = hash; handlers.hashchange(); },
    asset(index) { this.navigate(P.link(assets[index], 'idle', 0, null)); },
    tick(now) { ticks.shift()(now); },
  };
}
function blocked(f) {
  assert.equal(f.elements.canvas.width, 0);
  assert.equal(f.elements.direct.href, undefined);
  for (const id of ['play', 'prev', 'next', 'feedback', 'copy', 'scale']) assert.equal(f.elements[id].disabled, true, id);
}

// A -> pending B must clear A; a failed B must remain blocked.
{
  const f = fixture(); blocked(f); f.load(0);
  assert.equal(f.elements.canvas.lastDrawn, 'a.png');
  f.asset(1); blocked(f); f.images[1].onerror(); blocked(f);
  assert.match(f.elements.error.textContent, /failed to load/);
  f.asset(0); f.load(2);
  assert.equal(f.elements.feedback.disabled, false);
  assert.match(f.elements.direct.href, /asset=a&/);
}
// Rejected navigation invalidates both success and failure callbacks in flight.
{
  const f = fixture(); f.navigate('#asset=missing&version=wrong'); blocked(f);
  const error = f.elements.error.textContent;
  f.load(0); blocked(f); f.images[0].onerror(); blocked(f);
  assert.equal(f.elements.error.textContent, error);
}
// Rapid A -> B -> A selection cannot be overwritten by obsolete image events.
{
  const f = fixture(); f.asset(1); f.asset(0); f.load(1); blocked(f);
  f.load(2); f.images[0].onerror();
  assert.equal(f.elements.feedback.disabled, false);
  assert.equal(f.elements.canvas.lastDrawn, 'a.png');
  assert.equal(f.elements.error.textContent, '');
}
// Preparing feedback freezes playback; future rAF ticks must preserve the snapshot.
{
  const f = fixture(); f.load(0); assert.equal(f.elements.copy.disabled, true);
  f.elements.play.onclick(); f.tick(150);
  f.elements.notes.value = 'Fix contact'; f.elements.feedback.onclick();
  const snapshot = f.elements.output.value;
  assert.match(snapshot, /Frame \(zero-based\): 1/);
  assert.match(snapshot, /Fix contact/);
  assert.equal(f.elements.play.textContent, 'Play');
  assert.equal(f.elements.copy.disabled, false);
  f.tick(400); assert.equal(f.elements.output.value, snapshot);
  f.elements.prev.onclick(); assert.equal(f.elements.output.value, '');
  assert.equal(f.elements.copy.disabled, true);
}
console.log('controlled DOM load/error/rejection/race and feedback snapshot checks passed (not browser QA)');
