(async function () {
  'use strict';
  var results = [];
  var content = document.getElementById('mw-content-text');
  var fixture = '<div class="mw-parser-output"><div class="td2-brand"><div class="td2-brand-top"><div class="td2-brand-bonus-header"><div class="identity">Identity</div><h2><span class="mw-headline" id="bonus">Bonus</span></h2></div><div class="td2-brand-bonuses"><div class="td2-brand-panel td2-brand-pve"><sup id="cite-pve"><a href="#note">[1]</a></sup>PvE</div><div class="td2-brand-panel td2-brand-pvp"><sup id="cite-pvp"><a href="#note">[1]</a></sup>PvP</div></div></div><h2><span class="mw-headline" id="gear">Gear</span><a href="#other" class="edit">Edit</a></h2><div class="grid"><h3 id="child">Child</h3><input value="unchanged"><details><summary>Models</summary>Model</details></div><h2 id="other">Other</h2>Plain text<div>Other body</div></div><div class="td2-brand td2-gear-footer"><h2 id="expertise">Expertise</h2><div class="expertise">Expertise body</div><div class="mw-references-wrap"><ol class="references"><li id="note"><a href="#cite-pvp">Back</a>Note text</li></ol></div></div><div class="td2-navbox"><section class="td2-navbox-panel" data-section="all"><h2>Navigation</h2><div>Navigation body</div></section></div></div>';
  function assert(name, value) { results.push({name: name, pass: !!value}); if (!value) throw new Error(name); }
  function tick() { return new Promise(function (resolve) { setTimeout(resolve, 40); }); }
  function button(id) { return document.getElementById(id).closest('h2').querySelector('.td2-section-toggle'); }
  function visible(selector) { return !!document.querySelector(selector).getClientRects().length; }
  try {
    content.innerHTML = fixture;
    var original = content.textContent;
    var script = document.createElement('script');
    script.src = 'reader.js';
    await new Promise(function (resolve, reject) { script.onload = resolve; script.onerror = reject; document.body.appendChild(script); });
    await tick();
    assert('all five main sections default open', document.querySelectorAll('.td2-section-toggle[aria-expanded="true"]').length === 5);
    assert('note heading added once without moving references', document.querySelectorAll('#注释').length === 1 && document.querySelector('.mw-references-wrap').previousElementSibling.contains(document.getElementById('注释')) && document.querySelector('.td2-gear-footer').nextElementSibling.matches('.td2-navbox'));
    assert('original text preserved', content.textContent.replace('注释', '') === original);
    button('bonus').click();
    assert('identity remains visible while bonuses fold', visible('.identity') && !visible('.td2-brand-bonuses'));
    document.querySelector('.td2-brand-mode-controls button:last-child').click();
    assert('mode does not unfold section', !visible('.td2-brand-bonuses'));
    button('bonus').click();
    assert('opening section preserves mode', !visible('.td2-brand-pve') && visible('.td2-brand-pvp'));
    button('gear').click();
    assert('child and input follow parent', !visible('.grid') && document.querySelector('input').value === 'unchanged');
    document.querySelector('#toc a[href="#child"]').click();
    await tick();
    assert('TOC opens child target', visible('.grid'));
    button('gear').click();
    document.querySelector('#toc a[href="#child"]').click();
    await tick();
    assert('same hash opens again', visible('.grid'));
    button('注释').click();
    document.querySelector('#cite-pvp a').click();
    await tick();
    assert('citation reveals note', visible('.mw-references-wrap'));
    button('bonus').click();
    document.querySelector('.td2-brand-mode-controls button:first-child').click();
    document.querySelector('#note a').click();
    await tick();
    assert('backlink opens section and correct mode', visible('.td2-brand-pvp') && !visible('.td2-brand-pve'));
    button('gear').click();
    for (var i = 0; i < 5; i++) document._td2BrandSetsRuntime.init(document);
    assert('reinit preserves collapse and unique controls', !visible('.grid') && document.querySelectorAll('.td2-section-toggle').length === 5 && document.querySelectorAll('#toc a[href="#注释"]').length === 1);
    var duplicate = document.createElement('script'); duplicate.src = 'reader.js';
    await new Promise(function (resolve) { duplicate.onload = resolve; document.body.appendChild(duplicate); });
    button('gear').click();
    assert('duplicate runtime does not double toggle', visible('.grid'));
    button('other').click();
    assert('plain text also folds', document.getElementById('other').nextElementSibling.classList.contains('td2-section-hidden'));
    assert('Navbox has independent controller', document.querySelector('.td2-navbox button') && !document.querySelector('.td2-navbox .td2-section-toggle'));
    var notes = document.getElementById('注释').parentElement;
    var refs = notes.nextElementSibling;
    var skin = document.createElement('div'); skin.id = 'collapse_7'; skin.className = 'collapse';
    refs.before(skin); skin.appendChild(refs);
    var arrow = document.createElement('span'); arrow.className = 'collapse_arrow'; notes.appendChild(arrow);
    notes.setAttribute('href', '#collapse_7'); notes.setAttribute('data-toggle', 'collapse');
    await tick();
    assert('late mobile collapse removed locally', !notes.hasAttribute('data-toggle') && !document.getElementById('collapse_7') && notes.nextElementSibling === refs);
    content.innerHTML = '<div class="mw-parser-output"><div class="td2-brand"><div class="mw-heading mw-heading2"><h2 id="wrapped">Wrapped</h2></div><p>Body</p><div class="mw-heading mw-heading2"><h2 id="empty">Empty</h2></div></div></div>';
    await tick();
    assert('replacement content initializes with wrapper support', !!button('wrapped') && !button('empty'));
    assert('no empty notes section', !document.getElementById('注释'));
    assert('replacement removes stale notes TOC link', !document.querySelector('#toc a[href="#注释"]'));
    button('wrapped').click();
    location.hash = '#wrapped'; await tick();
    assert('hashchange reveals heading contents', visible('.td2-brand p'));
    content.innerHTML = '<div class="mw-parser-output"><h2>Ordinary page</h2><p>Body</p></div>';
    await tick();
    assert('ordinary pages excluded', !content.querySelector('.td2-section-toggle'));
    content.innerHTML = '<div data-td2-js-editor><div class="td2-brand"><h2>Editor control</h2><p>Body</p></div></div>';
    await tick();
    assert('editor controls excluded', !content.querySelector('.td2-section-toggle'));
  } catch (error) { results.push({error: error.stack}); }
  document.getElementById('results').textContent = JSON.stringify(results, null, 2);
})();
