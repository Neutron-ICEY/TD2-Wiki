(async function () {
  await document.fonts.ready;
  var results = [];
  var original = mw.config.get;
  var cases = [
    ['5.11 Tactical', '', ['5.11 Tactical', '死亡之握', '看守人']],
    ['5.11_Tactical', '#named-gear_511_keeper', ['5.11 Tactical', '死亡之握', '看守人']],
    ['5.11%20Tactical', '#different', ['5.11 Tactical', '死亡之握', '看守人']],
    ['毒蜥守卫队', '', ['毒蜥守卫队', '放轻松', '守夜者', '尖兵']],
    [encodeURIComponent('毒蜥守卫队'), '#different', ['毒蜥守卫队', '放轻松', '守夜者', '尖兵']],
    ['死亡之握', '', []],
    ['5.11 Tactical/独立词条', '', []]
  ];
  for (var item of cases) {
    mw.config.get = function () { return item[0]; };
    history.replaceState(null, '', location.pathname + item[1]);
    document._td2BrandSetsRuntime.init(document);
    document._td2BrandSetsRuntime.init(document);
    var actual = Array.from(document.querySelectorAll('.td2-navbox-current .td2-navbox-name a')).map(function (a) { return a.textContent; }).sort();
    results.push({title: item[0], hash: item[1], actual: actual, pass: JSON.stringify(actual) === JSON.stringify(item[2].sort())});
  }
  mw.config.get = original;
  history.replaceState(null, '', location.pathname);
  document._td2BrandSetsRuntime.init(document);
  results.push({corners: document.querySelectorAll('.td2-navbox-card > .td2-frame-corners').length, pass: document.querySelectorAll('.td2-navbox-card > .td2-frame-corners').length === 106});
  document.querySelector('#highlight-results').textContent = JSON.stringify(results);
}());
