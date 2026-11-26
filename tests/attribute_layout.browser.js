(function () {
  'use strict';
  function check() {
    const results = [], grids = Array.from(document.querySelectorAll('.td2-attribute-grid'));
    function assert(name, pass, actual) { results.push({name, pass: !!pass, actual}); }
    grids.forEach((grid, index) => {
      if (!grid.getClientRects().length) return;
      const rows = Array.from(grid.children).filter(r => r.matches('.td2-equipment-row'));
      const cores = rows.filter(r => r.querySelector('.td2-major-value'));
      if (!cores.length) return;
      const prefix = 'grid ' + index + ': ';
      assert(prefix + 'one core group and label', cores.length === 1 && cores[0].querySelectorAll('.td2-row-label').length === 1, cores.length);
      const values = Array.from(cores[0].querySelectorAll('.td2-major-option'));
      values.forEach((value, i) => {
        const rect = value.getBoundingClientRect(), icon = value.querySelector('.td2-icon').getBoundingClientRect();
        assert(prefix + 'core icon stays on value line ' + i, icon.top >= rect.top - 2 && icon.bottom <= rect.bottom + 2, {value: rect.toJSON(), icon: icon.toJSON()});
        if (i) {
          const previous = values[i - 1].getBoundingClientRect();
          assert(prefix + 'stacked core ' + i, rect.top >= previous.bottom && Math.abs(rect.left - previous.left) < 1, {gap: rect.top - previous.bottom, left: rect.left});
        }
      });
      const next = cores[cores.length - 1].nextElementSibling;
      if (next?.matches('.td2-equipment-row')) {
        const pseudo = getComputedStyle(next, '::before'), box = grid.getBoundingClientRect();
        const activeMinor = next.querySelector(':scope > [data-icon-key="equipment_row/minor_attribute"]') && !next.querySelector('[data-icon-key="state/none"]');
        const mod = next.querySelector(':scope > [data-icon-key="equipment_row/mod_slot"]');
        if (activeMinor || mod) assert(prefix + 'full-width visible group divider', pseudo.content === '""' && parseFloat(pseudo.borderTopWidth) > 0 && pseudo.borderTopStyle === 'solid' && pseudo.borderTopColor !== 'rgba(0, 0, 0, 0)' && Math.abs(parseFloat(pseudo.width) - box.width) < 2, {content: pseudo.content, border: pseudo.borderTop, width: pseudo.width, gridWidth: box.width});
        const coreBottom = cores[cores.length - 1].querySelector('.td2-row-value').getBoundingClientRect().bottom;
        assert(prefix + 'following group is below all cores', next.querySelector('.td2-row-value').getBoundingClientRect().top >= coreBottom, coreBottom);
      }
      rows.forEach((row, i) => {
        const icon = row.querySelector(':scope > .td2-icon').getBoundingClientRect();
        const label = row.querySelector('.td2-row-label').getBoundingClientRect();
        const value = row.querySelector('.td2-row-value').getBoundingClientRect();
        assert(prefix + 'row alignment ' + i, Math.abs(icon.top - label.top) < 2 && Math.abs(label.top - value.top) < 2, {iconTop: icon.top, labelTop: label.top, valueTop: value.top});
        assert(prefix + 'nonempty row ' + i, !!row.querySelector('.td2-row-label').textContent.trim() && !!row.querySelector('.td2-row-value').textContent.trim());
        row.querySelectorAll('.td2-icon img').forEach(image => {
          if (!image.getClientRects().length) return;
          const imageBox = image.getBoundingClientRect(), container = image.closest('.td2-icon').getBoundingClientRect();
          assert(prefix + 'image fits icon slot ' + i, imageBox.width <= container.width + 1 && imageBox.height <= container.height + 1, {image: imageBox.toJSON(), container: container.toJSON()});
        });
      });
      const ranks = rows.map(row => ['major_attribute','minor_attribute','mod_slot','talent_slot'].indexOf(row.querySelector(':scope > .td2-icon').dataset.iconKey.split('/')[1]));
      assert(prefix + 'core minor mod talent order', ranks.every((rank,i) => rank >= 0 && (!i || rank >= ranks[i-1])), ranks);
    });
    const exotic = document.querySelector('.td2-exotic-gear');
    if (exotic?.textContent.includes('Memento')) {
      const core = exotic.querySelector('.td2-major-value');
      assert('Memento three values in one group', core.querySelectorAll('.td2-major-option').length === 3, core.textContent);
      assert('Memento retains 1.0 precision', core.textContent.includes('1.0 技能分阶'), core.textContent);
    }
    if (exotic?.textContent.includes('Investor')) {
      const core = exotic.querySelector('.td2-major-value');
      assert('Investor random core uses exactly red blue yellow', JSON.stringify(Array.from(core.querySelectorAll('[data-icon-key]')).map(x => x.dataset.iconKey)) === JSON.stringify(['state/red','state/blue','state/yellow']), core.innerHTML);
      assert('Investor four random values', (exotic.querySelector('.td2-attribute-grid').textContent.match(/随机加成/g) || []).length === 4, core.textContent);
    }
    assert('no horizontal overflow', document.documentElement.scrollWidth <= innerWidth, {scrollWidth: document.documentElement.scrollWidth, viewport: innerWidth});
    let output = document.getElementById('attribute-layout-results');
    if (!output) { output = document.createElement('output'); output.id = 'attribute-layout-results'; output.hidden = true; document.body.appendChild(output); }
    output.textContent = JSON.stringify({viewport: innerWidth, results});
  }
  addEventListener('load', () => requestAnimationFrame(check));
  addEventListener('resize', () => requestAnimationFrame(check));
}());
