// Run with NODE_PATH pointing to a jsdom installation.
const { JSDOM } = require('jsdom');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const data = JSON.parse(fs.readFileSync(path.join(root, 'docs/data/data.json')));
const dom = new JSDOM(fs.readFileSync(path.join(root, 'docs/index.html'), 'utf8'), {
  url: 'https://example.test/', runScripts: 'outside-only', pretendToBeVisual: true,
});
const { window: w } = dom;
const errors = [];
w.addEventListener("error", e => { errors.push(e.error); e.preventDefault(); });
w.fetch = async url => ({ ok: true, json: async () => JSON.parse(fs.readFileSync(path.join(root, 'docs', url.split('?')[0]))) });
w.eval(fs.readFileSync(path.join(root, 'docs/app.js'), 'utf8'));
const $ = s => w.document.querySelector(s);
const all = s => [...w.document.querySelectorAll(s)];
const order = () => all('.mover-entry [data-favorite]').map(b => b.dataset.favorite.slice(7));
function source(value) {
  const input = $(`input[value="${value}"]`);
  input.checked = true;
  input.dispatchEvent(new w.Event('change', { bubbles: true }));
}
setTimeout(() => {
  try {
    assert.match($('#movers-summary').textContent, /ordered by Average absolute change/);
    const initial = order();
    assert.equal(initial.length, data.markets.length);
    const from = +$('#from-select').value, to = +$('#to-select').value;
    const avg = (m,i) => m.prices.polymarket[i] == null || m.prices.kalshi[i] == null ? null : (m.prices.polymarket[i]+m.prices.kalshi[i])/2;
    let previous = Infinity;
    for (const id of initial) {
      const m = data.markets.find(m=>m.id===id), a=avg(m,from), b=avg(m,to);
      const delta = a == null || b == null ? -1 : Math.abs(b-a);
      assert(delta <= previous); previous = delta;
    }
    for (const value of ['kalshi','polymarket','average']) {
      source(value); assert.deepEqual(order(), initial);
      const m=data.markets.find(m=>m.id===initial[0]);
      const expected=value==='average'?avg(m,to):m.prices[value][to];
      assert.equal(all('.mover-entry')[0].querySelectorAll('.price')[1].textContent, expected==null?'—':expected.toFixed(1));
    }
    source('kalshi');
    $('[data-sort="to"]').click();
    assert.match($('#movers-summary').textContent,/ordered by Kalshi To price/);
    const sorted=order(); source('average'); assert.deepEqual(order(),sorted);
    $('.mover-entry button').click();
    assert($('#ts-table-wrap').textContent.length>20);
    source('polymarket'); assert.match($('#chart-range').textContent,/Polymarket/);
    // A Kalshi-only market remains selectable with an entirely missing average history.
    source('kalshi');
    $('#search-input').value='Tie/Co-Winners';
    $('#search-input').dispatchEvent(new w.Event('input'));
    $('.mover-entry button').click(); source('average');
    assert(!$('#ts-chart').outerHTML.includes('NaN'));
    $('#team-select').value='boston-celtics';
    $('#team-select').dispatchEvent(new w.Event('change'));
    const teamOrder=()=>all('#team-content [data-favorite]').map(b=>b.dataset.favorite);
    const teamBefore=teamOrder(); source('kalshi'); assert.deepEqual(teamOrder(),teamBefore);
    $('#team-content [data-favorite^="team:"]').click();
    $('#tab-favorites').click();
    assert($('#favorites-content .market-card'));
    const favoritesBefore=all('#favorites-content [data-favorite]').map(b=>b.dataset.favorite);
    source('polymarket');
    assert.deepEqual(all('#favorites-content [data-favorite]').map(b=>b.dataset.favorite),favoritesBefore);
    assert.deepEqual(errors, []);
    console.log('PASS: average/delta default, stable source switching, explicit sorting, charts, missing history, teams and favorites');
  } catch(e) { console.error(e); process.exitCode=1; }
  finally { w.close(); }
}, 100);
