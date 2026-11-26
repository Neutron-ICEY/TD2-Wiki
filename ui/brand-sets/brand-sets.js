/* 装备模式渐进增强：不读取、不复制、不存储游戏数值。失败或未加载时两种模式仍可访问。
   正式 Reader Gadget 默认加载。
   页面只有一个模式状态，同步套装加成与天赋。 */
(function () {
  "use strict";
  // ResourceLoader 晚加载、记忆型 content hook 和重复加载共用一个入口。
  // 页面状态必须覆盖全页加成/天赋，不能随 hook 的局部根另建状态。
  if (document._td2BrandSetsRuntime) {
    document._td2BrandSetsRuntime.init(document);
    return;
  }
  var modeControls = null;
  var observedReader = null;
  var positionObserver = null;
  var STAGGER_INTERVAL = 6;
  var FADE_DURATION = 120;
  var navboxAnimations = new Map();
  var sections = new Map();
  var sectionId = 0;
  var sectionRoot = null;
  var sectionRefresh = false;

  function refreshSectionLayout() {
    if (sectionRefresh) return;
    sectionRefresh = true;
    requestAnimationFrame(function () {
      sectionRefresh = false;
      var spy = typeof jQuery !== 'undefined' && jQuery(document.body).data('bs.scrollspy');
      if (spy) { spy.refresh(); spy.process(); }
    });
  }

  function setSectionOpen(section, open) {
    section.open = open;
    section.button.setAttribute('aria-expanded', String(open));
    section.button.setAttribute('aria-label', (open ? '收起' : '展开') + section.label);
    section.nodes.forEach(function (node) { node.classList.toggle('td2-section-hidden', !open); });
    if (!open && section.nodes.some(function (node) { return node.contains(document.activeElement); })) section.button.focus();
    refreshSectionLayout();
  }

  function mountSections(scope) {
    var content = scope.querySelector('#mw-content-text');
    scope.querySelectorAll('[data-td2-notes-heading]').forEach(function (heading) {
      var refs = heading.nextElementSibling;
      if (!refs || !refs.querySelector('ol.references > li')) heading.remove();
    });
    scope.querySelectorAll('[data-td2-notes-link]').forEach(function (item) {
      if (!scope.getElementById(item.getAttribute('data-td2-notes-link'))) item.remove();
    });
    sections.forEach(function (section, heading) {
      if (heading.isConnected) return;
      section.nodes.forEach(function (node) { node.classList.remove('td2-section-hidden'); });
      sections.delete(heading);
    });
    if (!content || !content.querySelector('.td2-brand') || content.closest('[data-td2-js-editor], #editform, .ve-init-target')) return;
    if (typeof mw !== 'undefined' && mw.config && (mw.config.get('wgNamespaceNumber') !== 0 || mw.config.get('wgAction') !== 'view')) return;
    content.querySelectorAll('.td2-brand h2[data-toggle="collapse"]').forEach(function (heading) {
      if (heading.closest('[data-td2-js-editor], #editform, .ve-init-target, table, .td2-navbox')) return;
      var boundary = heading.parentElement.matches('.mw-heading2') ? heading.parentElement : heading;
      if (!boundary.parentElement.matches('.td2-brand, .td2-brand-bonus-header, .td2-brand-top')) return;
      if (!/^#collapse_\d+$/.test(heading.getAttribute('href') || '') || !heading.querySelector('.collapse_arrow')) return;
      var skinPanel = boundary.nextElementSibling;
      if (skinPanel && '#' + skinPanel.id === heading.getAttribute('href')) skinPanel.replaceWith.apply(skinPanel, Array.from(skinPanel.childNodes));
      heading.querySelectorAll('.collapse_arrow').forEach(function (arrow) { arrow.remove(); });
      heading.removeAttribute('data-toggle');
      heading.removeAttribute('href');
      heading.classList.remove('secondary', 'collapsed');
      if (/^collapseHead_\d+$/.test(heading.id)) heading.removeAttribute('id');
    });
    content.querySelectorAll('.td2-brand .mw-references-wrap').forEach(function (refs) {
      if (refs.closest('[data-td2-js-editor], #editform, .ve-init-target, table, .td2-navbox')) return;
      if (!refs.querySelector('ol.references > li')) return;
      var previous = refs.previousElementSibling;
      if (previous && (previous.matches('h2, .mw-heading2'))) return;
      var heading = scope.createElement('h2');
      heading.setAttribute('data-td2-notes-heading', '');
      var title = scope.createElement('span');
      title.className = 'mw-headline';
      title.id = '注释';
      while (scope.getElementById(title.id)) title.id = 'td2-notes-' + (++sectionId);
      title.textContent = '注释';
      heading.appendChild(title);
      refs.before(heading);
      var list = scope.querySelector('#toc.toc-sidebar > .toc-ul-wrap > ul, #toc > ul');
      if (list) {
        var item = scope.createElement('li');
        item.className = 'toclevel-1';
        item.setAttribute('data-td2-notes-link', title.id);
        var link = scope.createElement('a');
        link.href = '#' + title.id;
        link.textContent = '注释';
        item.appendChild(link);
        var navTitle = content.querySelector('.td2-navbox-heading > .mw-headline[id]');
        var nextLink = navTitle && list.querySelector('a[href="#' + CSS.escape(navTitle.id) + '"]');
        if (!nextLink) nextLink = list.querySelector('a[href="#top"], a[href="#firstHeading"]');
        var nextItem = nextLink && nextLink.closest('li');
        list.insertBefore(item, nextItem && nextItem.parentElement === list ? nextItem : null);
      }
    });
    content.querySelectorAll('.td2-brand h2').forEach(function (heading) {
      if (heading.closest('[data-td2-js-editor], #editform, .ve-init-target, table, .td2-navbox')) return;
      var boundary = heading.parentElement.matches('.mw-heading2') ? heading.parentElement : heading;
      var parent = boundary.parentElement;
      if (!parent.matches('.td2-brand, .td2-brand-bonus-header, .td2-brand-top')) return;
      var nodes = [];
      if (parent.matches('.td2-brand-bonus-header')) {
        var bonuses = parent.nextElementSibling;
        if (bonuses && bonuses.matches('.td2-brand-bonuses')) nodes.push(bonuses);
      } else {
        var node = boundary.nextSibling;
        while (node && !(node.nodeType === 1 && node.matches('h1, h2, .mw-heading1, .mw-heading2, .td2-navbox'))) {
          var next = node.nextSibling;
          if (node.nodeType === 3 && node.textContent.trim()) {
            var text = scope.createElement('span');
            node.replaceWith(text);
            text.appendChild(node);
            node = text;
          }
          if (node.nodeType === 1) nodes.push(node);
          node = next;
        }
      }
      if (!nodes.length) return;
      var section = sections.get(heading);
      if (!section) {
        var button = scope.createElement('button');
        button.type = 'button';
        button.className = 'td2-section-toggle';
        var headline = heading.querySelector('.mw-headline');
        section = {button: button, label: (headline || heading).textContent.trim(), nodes: [], open: true};
        if (headline) headline.after(button); else heading.appendChild(button);
        heading.classList.add('td2-section-heading');
        sections.set(heading, section);
      }
      section.nodes.filter(function (node) { return nodes.indexOf(node) < 0; }).forEach(function (node) { node.classList.remove('td2-section-hidden'); });
      section.nodes = nodes;
      section.button.setAttribute('aria-controls', nodes.map(function (node) {
        if (!node.id) {
          var id;
          do { id = 'td2-section-content-' + (++sectionId); } while (scope.getElementById(id));
          node.id = id;
        }
        return node.id;
      }).join(' '));
      setSectionOpen(section, section.open);
    });
    if (sectionRoot !== content.querySelector('.td2-brand')) {
      sectionRoot = content.querySelector('.td2-brand');
      revealSectionHash(true);
    }
  }

  function sectionTarget(hash) {
    if (!hash || hash === '#') return null;
    var id = hash.slice(1);
    try { id = decodeURIComponent(id); } catch (error) {}
    return document.getElementById(id);
  }

  function revealSectionTarget(target) {
    if (!target || !target.closest('.td2-brand')) return false;
    var changed = false;
    var panel = target.closest('.td2-brand-panel');
    if (panel && panel.hidden && modeControls) {
      modeControls.choose(panel.classList.contains('td2-brand-pvp') ? 'PvP' : 'PvE');
      changed = true;
    }
    sections.forEach(function (section, heading) {
      if (!section.open && (heading.contains(target) || section.nodes.some(function (node) { return node === target || node.contains(target); }))) {
        setSectionOpen(section, true);
        changed = true;
      }
    });
    return changed;
  }

  function scrollSectionTarget(target) {
    requestAnimationFrame(function () {
      if (!target.isConnected) return;
      var spy = typeof jQuery !== 'undefined' && jQuery(document.body).data('bs.scrollspy');
      var offset = spy ? Number(spy.options.offset) || 96 : 96;
      window.scrollTo(0, Math.max(0, target.getBoundingClientRect().top + window.scrollY - offset));
      refreshSectionLayout();
    });
  }

  function revealSectionHash(initial) {
    var target = sectionTarget(location.hash);
    if (initial === true && target && target.matches('.td2-navbox-heading > .mw-headline')) {
      // The browser may have followed the fragment before Reader moved the navbox.
      var alignNavbox = function () {
        requestAnimationFrame(function () {
          if (sectionTarget(location.hash) === target) target.scrollIntoView({block: 'start'});
        });
      };
      if (document.readyState === 'complete') alignNavbox();
      else window.addEventListener('load', alignNavbox, {once: true});
      return;
    }
    if (revealSectionTarget(target) || (initial === true && target && target.closest('.td2-brand'))) scrollSectionTarget(target);
  }
  function mountEquipmentNavigation(scope) {
    navboxAnimations.forEach(function (finish, panel) { if (!panel.isConnected) finish(); });
    var content = scope.querySelector('#mw-content-text > .mw-parser-output') || scope.querySelector('#mw-content-text .mw-parser-output');
    if (!content) return;
    var boxes = Array.from(content.querySelectorAll('.td2-navbox'));
    var box = boxes[0];
    if (!box) return;
    boxes.slice(1).forEach(function (duplicate) { duplicate.remove(); });
    if (content.lastElementChild !== box) content.appendChild(box);
    var gearFooter = content.querySelector('.td2-gear-footer');
    if (gearFooter && gearFooter.nextElementSibling !== box) content.insertBefore(gearFooter, box);
    Array.from(box.querySelectorAll('.td2-navbox-panel')).forEach(function (panel) {
      var heading = panel.firstElementChild;
      if (heading.querySelector('button')) return;
      var label = heading.querySelector('.mw-headline') || heading;
      var body = heading.nextElementSibling;
      var button = scope.createElement('button');
      button.type = 'button';
      button.textContent = label.textContent;
      body.id = 'td2-navbox-' + panel.getAttribute('data-section');
      button.setAttribute('aria-controls', body.id);
      var animations = [];
      var frozen = [];
      var reduced = matchMedia('(prefers-reduced-motion: reduce)');
      function cancel() {
        animations.forEach(function (animation) { animation.onfinish = null; animation.cancel(); });
        animations = [];
        body.style.removeProperty('overflow');
        reduced.removeEventListener('change', finish);
        navboxAnimations.delete(panel);
      }
      function clearFrozen() {
        frozen.forEach(function (target) { target.style.removeProperty('opacity'); });
        frozen = [];
      }
      function finish() {
        cancel();
        clearFrozen();
        body.hidden = button.getAttribute('aria-expanded') !== 'true';
        body.inert = body.hidden;
      }
      function setOpen(open, animate) {
        var height = animate && !body.hidden ? body.getBoundingClientRect().height : 0;
        navboxAnimations.forEach(function (settle, child) {
          if (child !== panel && panel.contains(child)) settle();
        });
        if (!open) {
          animations.forEach(function (animation) {
            var target = animation.effect.target;
            if (target !== body) { animation.commitStyles(); frozen.push(target); }
          });
        }
        var opacity = animate && !open && !body.hidden ? parseFloat(getComputedStyle(body).opacity) : 1;
        cancel();
        if (open) clearFrozen();
        button.setAttribute('aria-expanded', String(open));
        if (!open && body.contains(document.activeElement)) button.focus();
        if (!animate || reduced.matches || !body.animate || panel.closest('[hidden]')) {
          finish();
          return;
        }
        body.hidden = false;
        body.inert = !open;
        var targetHeight = open ? body.getBoundingClientRect().height : 0;
        body.style.overflow = 'clip';
        if (open) {
          var targets = Array.from(body.querySelectorAll('.td2-navbox-heading, .td2-navbox-slot-label, .td2-navbox-card'))
            .filter(function (target) { return !target.closest('[hidden]'); })
            .map(function (target) { return {target: target, rect: target.getBoundingClientRect()}; })
            .sort(function (a, b) { return a.rect.top - b.rect.top || a.rect.left - b.rect.left; });
          animations = targets.map(function (item, index) {
            return item.target.animate([{opacity: 0}, {opacity: 1}], {
              duration: FADE_DURATION, delay: index * STAGGER_INTERVAL,
              easing: 'ease-out', fill: 'both'
            });
          });
        } else {
          animations = [body.animate([{opacity: opacity}, {opacity: 0}], {duration: 120, easing: 'ease-out', fill: 'both'})];
        }
        var distance = Math.abs(targetHeight - height);
        var duration = distance === 0 ? 0 : Math.min(320, Math.max(120, 110 + distance / 5));
        if (duration) {
          var heightAnimation = body.animate([{height: height + 'px'}, {height: targetHeight + 'px'}], {duration: duration, easing: 'cubic-bezier(0.22, 1, 0.36, 1)'});
          animations.push(heightAnimation);
          heightAnimation.onfinish = function () { body.style.removeProperty('overflow'); };
        } else {
          body.style.removeProperty('overflow');
        }
        if (!animations.length) { finish(); return; }
        var last = animations.reduce(function (latest, animation) {
          return animation.effect.getComputedTiming().endTime > latest.effect.getComputedTiming().endTime ? animation : latest;
        });
        last.onfinish = finish;
        navboxAnimations.set(panel, finish);
        reduced.addEventListener('change', finish);
      }
      setOpen((panel.getAttribute('data-default-open') || box.getAttribute('data-default-open')) !== 'false');
      button.addEventListener('click', function () { setOpen(button.getAttribute('aria-expanded') !== 'true', true); });
      label.replaceChildren(button);
    });
    var reader = content.querySelector('.td2-brand');
    var title = typeof mw !== 'undefined' && mw.config ? mw.config.get('wgPageName') : reader && reader.getAttribute('data-brand');
    function pageName(value) {
      try { value = decodeURIComponent(value || ''); } catch (error) {}
      return (value || '').replace(/_/g, ' ').trim();
    }
    var normalized = pageName(title);
    Array.from(box.querySelectorAll('.td2-navbox-card')).forEach(function (card) {
      var target = card.getAttribute('data-target').split('#');
      var active = pageName(target[0]) === normalized;
      if (active && box.hasAttribute('data-anchor-current')) {
        var currentAnchor = pageName(location.hash.slice(1));
        active = pageName(target[1]) === currentAnchor || !target[1] && currentAnchor === '武器概览';
      }
      card.classList.toggle('td2-navbox-current', active);
      if (!card.querySelector('.td2-frame-corners')) {
        var corners = scope.createElement('span');
        corners.className = 'td2-frame-corners';
        corners.setAttribute('aria-hidden', 'true');
        ['nw', 'ne', 'sw', 'se'].forEach(function (corner) {
          var point = scope.createElement('span');
          point.className = 'td2-corner-node td2-corner-' + corner;
          corners.appendChild(point);
        });
        card.appendChild(corners);
      }
      var link = card.querySelector('.td2-navbox-name a');
      var selfLink = card.querySelector('.td2-navbox-name .selflink');
      if (!link && selfLink) {
        link = scope.createElement('a');
        link.href = location.href.split('#')[0] + (target[1] ? '#' + encodeURIComponent(target[1]) : '');
        link.textContent = selfLink.textContent;
        selfLink.replaceWith(link);
      }
      if (link && active) link.setAttribute('aria-current', 'page');
      else if (link) link.removeAttribute('aria-current');
    });
  }
  // 定位不依赖目录、皮肤坐标或滚动位置。
  function updateModePosition() {
    if (!modeControls || !modeControls.parentElement) return;
    var anchor = document.querySelector(".td2-brand");
    var view = document.defaultView;
    if (!anchor || !view || !anchor.getBoundingClientRect) return;
    var style = view.getComputedStyle(modeControls);
    var safe = parseFloat(style.paddingLeft) || 0;
    var width = modeControls.getBoundingClientRect().width;
    var viewport = document.documentElement.clientWidth;
    var left = Math.max(safe, Math.min(anchor.getBoundingClientRect().left - width - safe, viewport - width - safe));
    modeControls.style.setProperty("--td2-mode-offset", left + "px");
  }
  // 唯一控件挂在 body，以视口为 fixed 定位基准；离开 Reader 时卸载。
  function placeModeControls(scope) {
    if (!modeControls) return;
    var anchor = scope.querySelector(".td2-brand");
    var destination = anchor ? scope.body : null;
    if (destination && modeControls.parentElement !== destination) destination.appendChild(modeControls);
    else if (!destination && modeControls.parentElement) modeControls.parentElement.removeChild(modeControls);
    if (positionObserver && observedReader !== anchor) {
      positionObserver.disconnect();
      observedReader = anchor;
      if (anchor) {
        positionObserver.observe(anchor);
        positionObserver.observe(modeControls);
        positionObserver.observe(scope.body);
      }
    }
    updateModePosition();
  }

  function pageActionContext() {
    if (typeof mw === 'undefined' || !mw.config) return {title: '', pageid: 0, user: 0, groups: [], historical: false, key: 'preview'};
    // 内容页包括手工词条；不依赖装备 Reader 或表单是否存在。
    if (mw.config.get('wgNamespaceNumber') !== 0 || mw.config.get('wgAction') !== 'view' || mw.config.get('wgIsArticle') === false) return null;
    var params = new URL(location.href).searchParams;
    var context = {
      title: (mw.config.get('wgPageName') || '').replace(/_/g, ' '),
      pageid: mw.config.get('wgArticleId'), user: mw.config.get('wgUserId'),
      groups: mw.config.get('wgUserGroups') || [],
      historical: params.has('oldid') || params.has('diff')
    };
    context.key = JSON.stringify(context);
    return context;
  }

  function pageShareURL(scope) {
    var canonical = scope.querySelector('link[rel="canonical"]');
    var full = new URL(canonical ? canonical.href :
      (typeof mw !== 'undefined' && mw.util ? mw.util.getUrl(mw.config.get('wgPageName')) : location.href), location.href);
    full.hash = '';
    var pageid = typeof mw !== 'undefined' && mw.config && mw.config.get('wgArticleId');
    var util = typeof mw !== 'undefined' && mw.huijiApi || (typeof window !== 'undefined' && window.$cockpitUtil);
    // /p/ 是已在 TD2 核实的灰机页面 ID 路由；无需自建短链或在点击后等待网络。
    if (typeof pageid === 'number' && Number.isSafeInteger(pageid) && pageid > 0) {
      try {
        var short = new URL(util && typeof util.getPageUrlById === 'function' ? util.getPageUrlById(pageid, 'td2') : '/p/' + pageid, full);
        if (short.origin === full.origin && short.pathname === '/p/' + pageid && !short.search && !short.hash) return short.href;
        if (short.origin === full.origin && short.pathname === '/index.php' && short.search === '?curid=' + pageid && !short.hash) return new URL('/p/' + pageid, full).href;
      } catch (error) {}
    }
    return full.href;
  }


  function mountEditActions(scope, row, context) {
    var entry = scope.getElementById('td2-js-edit-entry');
    var source = scope.getElementById('ca-edit');
    if (entry) {
      entry.hidden = !row._td2CanEdit;
      // 表单入口由现有 Editor 在核实页面合同和权限后创建，公共框架不猜测表单。
      if (row._td2CanEdit && entry.parentElement !== row) row.insertBefore(entry, row.children[1] || null);
    }
    if (!source && row._td2CanEdit) {
      source = scope.createElement('a');
      source.id = 'ca-edit';
    }
    if (source) {
      source.hidden = !row._td2CanEdit;
      if (row._td2CanEdit) {
        var link = source.matches('a') ? source : source.querySelector('a');
        if (link) {
          link.textContent = '编辑源码';
          link.href = mw.util.getUrl(context.title, {action: 'edit'});
          link.hidden = false;
          if (link.parentElement !== row) row.appendChild(link);
        }
      }
    }
  }

  function mountPageActions(scope) {
    var heading = scope.getElementById('firstHeading');
    var context = pageActionContext();
    var row = scope.getElementById('td2-page-actions');
    if (!heading || !context) {
      if (row) row.remove();
      return;
    }
    if (row && row._td2PageKey !== context.key) { row.remove(); row = null; }
    if (!row) {
      row = scope.createElement('div');
      row.id = 'td2-page-actions';
      row._td2PageKey = context.key;
      row.setAttribute('role', 'group');
      row.setAttribute('aria-label', '页面操作');
      var copy = scope.createElement('button');
      copy.type = 'button';
      copy.textContent = '复制链接';
      copy.setAttribute('aria-live', 'polite');
      bindCopyButton(copy, function () { return pageShareURL(scope); });
      row.appendChild(copy);
      heading.appendChild(row);
      if (context.user > 0 && context.groups.indexOf('sysop') !== -1 && !context.historical && context.pageid > 0) {
        mw.loader.using(['mediawiki.util', 'mediawiki.api']).then(function () {
          return new mw.Api().get({action: 'query', meta: 'userinfo', uiprop: 'groups|rights',
            prop: 'info', pageids: context.pageid, intestactions: 'edit', formatversion: 2, maxage: 0, smaxage: 0});
        }).then(function (result) {
          var current = pageActionContext();
          if (!current || current.key !== context.key || scope.getElementById('td2-page-actions') !== row) return;
          var query = result.query || {}, user = query.userinfo || {}, pages = query.pages || [], page = pages.length === 1 && pages[0];
          row._td2CanEdit = user.id === context.user && !user.anon && (user.groups || []).indexOf('sysop') !== -1 &&
            (user.rights || []).indexOf('edit') !== -1 && !!page && !page.missing && page.ns === 0 &&
            page.pageid === context.pageid && page.title === context.title && !!page.actions && page.actions.edit === true;
          mountEditActions(scope, row, context);
        }).catch(function () { /* 权限未知时保留复制按钮；服务端仍负责拒绝未授权写入。 */ });
      }
    }
    mountEditActions(scope, row, context);
  }

  function bindCopyButton(copy, url) {
      if (copy._td2CopyBound) return;
      copy._td2CopyBound = true;
      copy.setAttribute('aria-live', 'polite');
      var copyTimer;
      var copyRequest = 0;
      copy.addEventListener('click', function () {
        var request = ++copyRequest;
        clearTimeout(copyTimer);
        copy.textContent = '复制链接';
        copy.classList.toggle('td2-copy-success', false);
        var copying;
        try { copying = navigator.clipboard.writeText(url()); }
        catch (error) { copying = Promise.reject(error); }
        Promise.resolve(copying).then(function () {
          if (request !== copyRequest) return;
          copy.textContent = '成功复制';
          copy.classList.toggle('td2-copy-success', true);
        }, function () {
          if (request !== copyRequest) return;
          copy.textContent = '复制失败';
        }).then(function () {
          if (request !== copyRequest) return;
          copyTimer = setTimeout(function () {
            copy.textContent = '复制链接';
            copy.classList.toggle('td2-copy-success', false);
          }, 1800);
        });
      });
  }

  function homeRemaining(seconds) {
    var days = Math.floor(seconds / 86400);
    var hours = Math.floor(seconds / 3600) % 24;
    var minutes = Math.floor(seconds / 60) % 60;
    return days ? days + '天 ' + hours + '小时' :
      hours ? hours + '小时 ' + minutes + '分' : minutes ? minutes + '分钟' : '不足1分钟';
  }

  var seasonTimer;
  function updateHomeSeasons(scope) {
    if (seasonTimer !== undefined) window.clearTimeout(seasonTimer);
    var now = Math.floor(Date.now() / 1000);
    var next = Infinity;
    scope.querySelectorAll('.td2-home .td2-home-season-card').forEach(function (card) {
      var start = Number(card.dataset.start);
      var end = Number(card.dataset.end);
      var active = start <= now && now < end;
      card.classList.toggle('td2-home-season-off', !active);
      if (now < start && start < end) next = Math.min(next, start);
      if (!active) return;
      var left = end - now;
      var hours = Math.floor(left / 3600);
      var text = Math.floor(hours / 168) + '周 ' + (Math.floor(hours / 24) % 7) + '日 ' + (hours % 24) + '时';
      var time = card.querySelector('.td2-home-season-time');
      if (time.textContent !== text) time.textContent = text;
      var finish = card.querySelector('time[datetime]');
      if (finish) {
        var format = homeDateFormat();
        var deadline = homeDate(format, end).reading + (format ? ' 结束' : ' 结束（北京时间）');
        if (finish.textContent !== deadline) finish.textContent = deadline;
      }
      var ring = card.querySelector('.td2-home-ring');
      var elapsed = now - start;
      ring.style.setProperty('--td2-home-arc', (360 * elapsed / (end - start)).toFixed(4) + 'deg');
      ring.classList.toggle('td2-home-ring-filled', elapsed > 0);
      // Keep the arc moving between changes to the whole-hour reading.
      next = Math.min(next, end, now + left % 60 + 1);
    });
    if (Number.isFinite(next)) {
      seasonTimer = window.setTimeout(function () { updateHomeSeasons(scope); }, Math.min(2147483647, Math.max(1, next * 1000 - Date.now())));
    }
  }

  var eventDeck = null;
  var eventBoundaryTimer;

  function homeDateFormat(useServerTimeFor) {
    try {
      var zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
      // Use the same Beijing reading as the server if the local zone cannot be identified.
      if (!zone || zone === useServerTimeFor) return null;
      var format = new Intl.DateTimeFormat('zh-CN', {timeZone: zone, month: 'numeric', day: 'numeric',
        hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZoneName: 'shortOffset'});
      return typeof format.formatToParts === 'function' ? format : null;
    } catch (_) { return null; }
  }

  function homeDate(format, epoch) {
    if (!format) {
      var beijing = new Date((epoch + 8 * 3600) * 1000);
      return {reading: (beijing.getUTCMonth() + 1) + '月' + beijing.getUTCDate() + '日 ' +
        String(beijing.getUTCHours()).padStart(2, '0') + ':' + String(beijing.getUTCMinutes()).padStart(2, '0'),
        zone: '北京时间'};
    }
    var parts = {};
    format.formatToParts(epoch * 1000).forEach(function (part) { parts[part.type] = part.value; });
    return {reading: parts.month + '月' + parts.day + '日 ' + parts.hour + ':' + parts.minute,
      zone: parts.timeZoneName.replace('GMT', 'UTC').replace(/^UTC[+-]0$/, 'UTC')};
  }

  function dissolveHomeCaption(caption) {
    if (!caption || !caption.clientWidth || !caption.clientHeight) return;
    var reveal = [.025, .22, .52, .80, .95, .99];
    var width = caption.clientWidth, height = caption.clientHeight;
    var canvas = document.createElement('canvas');
    canvas.width = width * reveal.length;
    canvas.height = height;
    canvas.style.width = (100 * reveal.length) + '%';
    var ctx = canvas.getContext('2d');
    if (!ctx || !canvas.animate) return;

    // 一组相邻小块共享出现时间，笔画从不规则的缺口中显现。
    var title = caption.querySelector('.td2-home-news-title');
    var cell = Math.max(2, Math.round(parseFloat(getComputedStyle(title).fontSize) / 7));
    var block = cell * 2, columns = Math.ceil(width / block);
    var clusters = Array.from({length: columns * Math.ceil(height / block)}, Math.random);
    ctx.fillStyle = getComputedStyle(caption).backgroundColor;
    ctx.fillRect(0, 0, canvas.width, height);
    for (var y = 0; y < height; y += cell) {
      for (var x = 0; x < width; x += cell) {
        var cluster = clusters[Math.floor(y / block) * columns + Math.floor(x / block)];
        var rank = cluster + (Math.random() - .5) * .24;
        for (var frame = 0; frame < reveal.length; frame++) {
          if (rank < reveal[frame]) ctx.clearRect(frame * width + x, y, Math.min(cell, width - x), cell);
        }
      }
    }
    var bounds = caption.getBoundingClientRect();
    caption.querySelectorAll('.td2-home-event-type, .td2-home-news-title, .td2-home-event-icon').forEach(function (part) {
      var range = document.createRange();
      range.selectNodeContents(part);
      var box = range.getBoundingClientRect();
      var style = getComputedStyle(part);
      ctx.fillStyle = part.classList.contains('td2-home-event-icon') ? '#fff' : style.color;
      ctx.globalAlpha = Number(style.opacity);
      for (var f = 0; f < 4; f++) {
        var count = Math.ceil(box.width / 50 * (1 - reveal[f]));
        for (var i = 0; i < count; i++) {
          var size = cell * (Math.random() < .3 ? 2 : 1);
          var px = box.left - bounds.left + Math.random() * Math.max(0, box.width - size);
          var py = box.top - bounds.top + Math.random() * Math.max(0, box.height - size);
          ctx.fillRect(f * width + Math.round(px), Math.round(py), size, size);
        }
      }
    });
    var overlay = document.createElement('span');
    overlay.className = 'td2-home-dissolve';
    overlay.setAttribute('aria-hidden', 'true');
    overlay.appendChild(canvas);
    caption.appendChild(overlay);
    var animation = canvas.animate([{transform: 'none'}, {transform: 'translateX(-100%)'}], {
      duration: 200, easing: 'steps(' + reveal.length + ', end)'
    });
    animation.onfinish = animation.oncancel = function () { overlay.remove(); };
    return animation;
  }

  function mountHomeEvents(scope) {
    if (eventBoundaryTimer !== undefined) window.clearTimeout(eventBoundaryTimer);
    var panel = scope.querySelector('.td2-home .td2-home-events');
    var now = Math.floor(Date.now() / 1000);
    var next = Infinity;
    var format = panel && homeDateFormat('Asia/Shanghai');
    var slides = panel ? Array.from(panel.querySelectorAll('.td2-home-story')).filter(function (card) {
      if (!card.hasAttribute('data-start')) return true;
      var start = Number(card.dataset.start);
      var end = Number(card.dataset.end);
      var active = start <= now && now < end;
      card.classList.toggle('td2-home-event-off', !active);
      if (!active) {
        if (now < start) next = Math.min(next, start);
        return false;
      }
      next = Math.min(next, end);
      var remaining = card.querySelector('.td2-home-event-time');
      if (!remaining) return true;
      var text = homeRemaining(end - now);
      if (remaining.textContent !== text) remaining.textContent = text;
      next = Math.min(next, now + (end - now) % 60 + 1);
      var a = homeDate(format, start), b = homeDate(format, end);
      remaining.parentElement.title = a.reading + (a.zone === b.zone ? '' : ' ' + a.zone) +
        ' 至 ' + b.reading + '（' + b.zone + '）';
      return true;
    }) : [];
    if (Number.isFinite(next)) {
      eventBoundaryTimer = window.setTimeout(function () { mountHomeEvents(scope); },
        Math.min(2147483647, Math.max(1, next * 1000 - Date.now())));
    }
    var selectedSlide = null;
    var focusLabel = null;
    if (eventDeck) {
      if (eventDeck.panel === panel && slides.length === eventDeck.slides.length &&
          slides.every(function (slide, i) { return slide === eventDeck.slides[i]; })) return;
      if (eventDeck.panel === panel) {
        selectedSlide = panel.querySelector('.td2-home-story[aria-hidden="false"]');
        var focused = scope.activeElement;
        if (eventDeck.controls.contains(focused)) focusLabel = focused.getAttribute('aria-label');
        else if (selectedSlide && selectedSlide.contains(focused) && !slides.includes(selectedSlide)) focusLabel = '';
      }
      eventDeck.destroy();
      eventDeck = null;
    }
    if (slides.length < 2) {
      if (focusLabel !== null) {
        var heading = panel.querySelector('h2');
        heading.tabIndex = -1;
        heading.focus({preventScroll: true});
      }
      return;
    }

    var controls = document.createElement('div');
    controls.className = 'td2-home-event-controls';
    controls.setAttribute('role', 'group');
    controls.setAttribute('aria-label', '活动切换');
    var motion = window.matchMedia('(prefers-reduced-motion: reduce)');
    var canHover = window.matchMedia('(hover: hover)');
    var current = Math.max(0, slides.indexOf(selectedSlide));
    var timer;
    var dissolve;
    var events = new AbortController();
    var options = {signal: events.signal};

    function button(parent, label, className) {
      var item = document.createElement('button');
      item.type = 'button';
      item.className = className;
      item.setAttribute('aria-label', label);
      item.title = label;
      parent.appendChild(item);
      return item;
    }
    function stepKey(key, label, direction) {
      var item = button(controls, label + '（' + key + '）', 'td2-home-event-key');
      item.setAttribute('aria-keyshortcuts', key);
      item.textContent = key;
      item.addEventListener('click', function () { step(direction); });
    }
    stepKey('Q', '上一项活动', -1);
    var dots = document.createElement('div');
    dots.className = 'td2-home-event-dots';
    controls.appendChild(dots);
    var selectors = slides.map(function (slide, index) {
      var item = button(dots, '显示' + slide.querySelector('.td2-home-news-title').textContent.trim(), 'td2-home-event-pick');
      item.addEventListener('click', function () { show(index); });
      return item;
    });
    stepKey('E', '下一项活动', 1);

    function show(index) {
      var changed = index !== current;
      if (changed && slides[current].contains(document.activeElement)) {
        selectors[index].focus({preventScroll: true});
      }
      current = index;
      slides.forEach(function (slide, i) {
        slide.inert = i !== current;
        slide.setAttribute('aria-hidden', String(i !== current));
        selectors[i].setAttribute('aria-pressed', String(i === current));
      });
      if (changed) {
        if (dissolve) dissolve.cancel();
        if (!motion.matches) dissolve = dissolveHomeCaption(slides[current].querySelector('.td2-home-news-caption'));
      }
      schedule();
    }
    function step(direction) {
      show((current + direction + slides.length) % slides.length);
    }
    function schedule() {
      window.clearTimeout(timer);
      if (events.signal.aborted || document.hidden || motion.matches) return;
      if ((canHover.matches && panel.matches(':hover')) || panel.querySelector(':focus-visible')) return;
      timer = window.setTimeout(function () { step(1); }, 12000);
    }
    document.addEventListener('keydown', function (event) {
      if (event.defaultPrevented || event.repeat || event.isComposing || event.ctrlKey || event.altKey || event.metaKey) return;
      var target = event.target;
      if (!target.closest || target.isContentEditable || target.closest('input, textarea, select, dialog, [role="dialog"], [role="textbox"], [role="searchbox"], [role="combobox"]')) return;
      if (target !== document.body && target !== document.documentElement && !panel.closest('.td2-home').contains(target)) return;
      var key = event.key.toLowerCase();
      var fromDot = dots.contains(target);
      if (key === 'q' || (fromDot && key === 'arrowleft')) step(-1);
      else if (key === 'e' || (fromDot && key === 'arrowright')) step(1);
      else return;
      event.preventDefault();
      if (fromDot) selectors[current].focus({preventScroll: true});
    }, options);
    panel.addEventListener('pointerenter', schedule, options);
    panel.addEventListener('pointerleave', schedule, options);
    panel.addEventListener('focusin', schedule, options);
    panel.addEventListener('focusout', function () { queueMicrotask(schedule); }, options);
    document.addEventListener('visibilitychange', schedule, options);
    canHover.addEventListener('change', schedule, options);
    motion.addEventListener('change', function () {
      if (motion.matches && dissolve) dissolve.cancel();
      schedule();
    }, options);
    panel.appendChild(controls);
    panel.classList.add('td2-home-rotating');
    show(current);
    if (focusLabel !== null) {
      var target = Array.from(controls.querySelectorAll('button')).find(function (item) {
        return item.getAttribute('aria-label') === focusLabel;
      });
      (target || selectors[current]).focus({preventScroll: true});
    }
    eventDeck = {panel: panel, slides: slides, controls: controls, destroy: function () {
      events.abort();
      window.clearTimeout(timer);
      if (dissolve) dissolve.cancel();
      controls.remove();
      panel.classList.remove('td2-home-rotating');
      slides.forEach(function (slide) { slide.inert = false; slide.removeAttribute('aria-hidden'); });
    }};
  }

  function initBrandSets(root) {
    var node = root && root[0] ? root[0] : root;
    var scope = node && node.ownerDocument ? node.ownerDocument : document;
    updateHomeSeasons(scope);
    mountHomeEvents(scope);
    mountEquipmentNavigation(scope);
    if (document._td2NavboxMotion) document._td2NavboxMotion();
    mountPageActions(scope);
    if (document._td2BrandSetsRuntime.initWeaponCharts) document._td2BrandSetsRuntime.initWeaponCharts(scope);
    var anchor = scope.querySelector(".td2-brand");
    var panels = Array.from(scope.querySelectorAll(".td2-brand-panel"));
    var previous = modeControls || scope.querySelector(".td2-brand-mode-controls");
    if (previous && previous.choose) previous.choose(previous.getAttribute("data-mode") || "PvE");
    if (anchor && panels.length && !previous) {
      var controls = document.createElement("div");
      controls.className = "td2-brand-mode-controls";
      controls.setAttribute("role", "group");
      controls.setAttribute("aria-label", "选择页面数据模式（套装加成与装备天赋同步）");
      var buttons = [];
      function choose(mode) {
        controls.setAttribute("data-mode", mode);
        Array.from(scope.querySelectorAll(".td2-brand-panel")).forEach(function (panel) {
          var active = panel.classList.contains("td2-brand-" + mode.toLowerCase());
          panel.hidden = !active;
          panel.classList.toggle("td2-mode-pvp", active && mode === "PvP" && !panel.classList.contains('td2-gear-effect-group') && !panel.classList.contains('td2-gear-talent-links'));
        });
        buttons.forEach(function (button) { button.setAttribute("aria-pressed", String(button.textContent === mode)); });
      }
      function addButtons(group) {
        var localButtons = [];
        ["PvE", "PvP"].forEach(function (mode, index) {
        var button = document.createElement("button");
        button.type = "button";
        button.className = "td2-frame";

        button.textContent = mode;
        // 和模板:TD2边框角节点使用同一 class/四角合同；CSS 几何只有一份。
        var corners = document.createElement("span");
        corners.className = "td2-frame-corners";
        corners.setAttribute("aria-hidden", "true");
        ["nw", "ne", "sw", "se"].forEach(function (corner) {
          var point = document.createElement("span");
          point.className = "td2-corner-node td2-corner-" + corner;
          corners.appendChild(point);
        });
        button.appendChild(corners);
        button.addEventListener("click", function () { choose(mode); });
        button.addEventListener("keydown", function (event) {
          if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
            event.preventDefault();
            var next = 1 - index;
            choose(next === 0 ? "PvE" : "PvP");
            localButtons[next].focus();
          }
        });
        buttons.push(button); localButtons.push(button);
        group.appendChild(button);
      });
      }
      addButtons(controls);
      modeControls = controls;
      controls.choose = choose;
      choose("PvE");
    }
    if (previous) modeControls = previous;
    placeModeControls(scope);
    mountSections(scope);
  }
  // 单一生命周期注册；重复脚本/content hook 不会重复添加监听器。
  if (typeof ResizeObserver !== "undefined") positionObserver = new ResizeObserver(updateModePosition);
  if (document.defaultView) document.defaultView.addEventListener("resize", updateModePosition);
  if (document.defaultView) document.defaultView.addEventListener('hashchange', function () { mountEquipmentNavigation(document); revealSectionHash(); });
  if (document.defaultView) document.defaultView.addEventListener('popstate', revealSectionHash);
  document.addEventListener('click', function (event) {
    if (event.button !== 0 || event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return;
    var element = event.target.nodeType === 1 ? event.target : event.target.parentElement;
    var heading = element.closest('.td2-section-heading');
    if (heading && sections.has(heading) && !element.closest('a, input, select, textarea, [contenteditable="true"]')) {
      if (element.closest('button') && !element.closest('.td2-section-toggle')) return;
      var section = sections.get(heading);
      setSectionOpen(section, !section.open);
      return;
    }
    var link = element.closest('a[href]');
    if (!link || link.download || (link.target && link.target !== '_self') || link.origin !== location.origin || link.pathname !== location.pathname || link.search !== location.search) return;
    var target = sectionTarget(link.hash);
    var changed = revealSectionTarget(target);
    if (changed) scrollSectionTarget(target);
  }, true);
  document._td2BrandSetsRuntime = {init: initBrandSets};
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { initBrandSets(document); });
  } else {
    initBrandSets(document);
  }
  if (typeof MutationObserver !== "undefined") new MutationObserver(function (changes) {
    // 复用原观察器；覆盖晚到的 Reader 和编辑入口。
    if (changes.some(function (m) {
      if (m.type === 'attributes') return m.target.matches('.td2-brand h2');
      return Array.from(m.addedNodes).concat(Array.from(m.removedNodes || [])).some(function (n) {
      return n.nodeType===1 && n.querySelector && (
        n.matches("#firstHeading, #td2-js-edit-entry, #ca-edit") || n.querySelector("#firstHeading, #td2-js-edit-entry, #ca-edit") ||
        n.matches(".td2-navbox") || n.querySelector(".td2-navbox") ||
        n.matches(".td2-brand, .td2-brand-panel, .mw-references-wrap, h2") ||
        n.querySelector(".td2-brand") || n.querySelector(".td2-brand-panel"));
    });})) initBrandSets(document);
  }).observe(document.documentElement,{childList:true,subtree:true,attributes:true,attributeFilter:['data-toggle']});
  // MediaWiki 动态加载页面片段时复用同一个增强入口；普通浏览器不需要 mw。
  if (typeof mw !== "undefined" && mw.hook) {
    mw.hook("wikipage.content").add(initBrandSets);
  }
})();

(function () {
  'use strict';
  if (typeof ResizeObserver === 'undefined' || typeof matchMedia === 'undefined') return;
  if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', start, {once: true}); } else start();
  function start() {
  if (document._td2NavboxMotion) { document._td2NavboxMotion(); return; }
  var reduced = matchMedia('(prefers-reduced-motion: reduce)');
  var entries = new Map();
  var navbox = null;
  var pending = false;
  function schedule() {
    if (pending) return;
    pending = true;
    requestAnimationFrame(update);
  }
  var resize = new ResizeObserver(schedule);
  function update() {
    pending = false;
    if (navbox) navbox.querySelectorAll('.td2-navbox-name a').forEach(function (link) {
      if (entries.has(link)) return;
      var window = document.createElement('span');
      window.className = 'td2-name-window';
      var text = document.createElement('span');
      text.className = 'td2-name-motion';
      text.textContent = link.textContent;
      link.title = link.closest('.td2-navbox-card').title || link.textContent;
      link.textContent = '';
      window.appendChild(text);
      link.appendChild(window);
      entries.set(link, {window: window, text: text, distance: -1, animation: null});
      resize.observe(window);
    });
    entries.forEach(function (entry, link) {
      var visible = link.isConnected && link.getClientRects().length && !document.hidden;
      var distance = visible && !reduced.matches ? Math.max(0, entry.text.scrollWidth - entry.window.clientWidth) : 0;
      if (distance <= 1) distance = 0;
      if (distance !== entry.distance) {
        if (entry.animation) entry.animation.cancel();
        entry.animation = null;
        entry.distance = distance;
        if (distance) {
          var travel = distance / 22 * 1000;
          var returnDuration = 300;
          var duration = travel + returnDuration + 3000;
          entry.animation = entry.text.animate([
            {transform: 'translateX(0)', offset: 0},
            {transform: 'translateX(0)', offset: 1500 / duration},
            {transform: 'translateX(-' + distance + 'px)', offset: (1500 + travel) / duration},
            {transform: 'translateX(-' + distance + 'px)', offset: (3000 + travel) / duration, easing: 'ease-in-out'},
            {transform: 'translateX(0)', offset: 1}
          ], {duration: duration, iterations: Infinity, easing: 'linear'});
        }
      }
      if (!link.isConnected) { resize.unobserve(entry.window); entries.delete(link); }
    });
  }
  var changes = new MutationObserver(schedule);
  function attachNavbox() {
    var current = document.querySelector('#mw-content-text .td2-navbox');
    if (current === navbox) return;
    changes.disconnect();
    navbox = current;
    if (navbox) changes.observe(navbox, {subtree: true, childList: true, attributes: true, attributeFilter: ['hidden']});
    schedule();
  }
  document._td2NavboxMotion = attachNavbox;
  reduced.addEventListener('change', schedule);
  document.addEventListener('visibilitychange', schedule);
  document.fonts.ready.then(schedule);
  document.fonts.addEventListener('loadingdone', schedule);
  attachNavbox();
  }
}());

/* Reader chart geometry and readouts share an ease-in-out curve. */
(function () {
  'use strict';
  function chartProgress(start, now, duration) {
    var progress = Math.max(0, Math.min(1, (now - start) / (duration || 200)));
    if (progress === 0 || progress === 1) return progress;
    // Solve the time coordinate of cubic-bezier(0.42, 0, 0.58, 1).
    var t = progress;
    for (var i = 0; i < 5; i++) {
      t -= (t * (1.26 + t * (-0.78 + 0.52 * t)) - progress) / (1.26 + t * (-1.56 + 1.56 * t));
    }
    return t * t * (3 - 2 * t);
  }

  /* Vision comparison: values and native icons belong to the article markup. */
  function initVision() {
    document.querySelectorAll('.td2-threat-distance-figure').forEach(function (figure) {
      var plot = figure.querySelector('.td2-threat-distance-plot');
      if (!plot || plot.querySelector('svg')) return;
      // The adjacent table owns the distance values; the ruler only projects them.
      var distances = Array.from(figure.querySelectorAll('table tr')).slice(1).map(function (row) { return Number(row.cells[1].textContent.trim()); });
      if (!distances.length || !distances.every(Number.isFinite)) return;
      var maximum = Math.max.apply(null, distances);
      var svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 480 154" aria-hidden="true" style="display:block;width:100%;height:auto;"><g font-family="Arial, sans-serif"><path d="M46 76H434M46 69V83" fill="none" stroke="#eee" stroke-opacity=".5" stroke-width="1.5"/><text x="3" y="82" font-family="Microsoft YaHei, sans-serif" font-size="18" fill="#b8b8b8">敌人</text>';
      distances.forEach(function (distance, index) {
        var x = 46 + 388 * distance / maximum, lower = index % 2 === 1;
        var y = lower ? 137 : 40, end = lower ? 104 : 50;
        var unitX = x + (String(distance).length === 1 ? 13.6209 : 21.9632);
        svg += '<path d="M'+x+' 76V'+end+'" stroke="#eee" stroke-opacity=".35" fill="none"/><circle cx="'+x+'" cy="76" r="2.5" fill="#ff6a13"/><text x="'+x+'" y="'+y+'" fill="#ff6a13" font-size="30" text-anchor="middle" font-weight="600">'+distance+'</text><text x="'+unitX+'" y="'+y+'" fill="#ff6a13" font-size="19">米</text>';
      });
      plot.innerHTML = svg + '</g></svg>';
    });
    document.querySelectorAll('.td2-threat-vision').forEach(function (root) {
      if (root.dataset.visionMounted) return;
      var scaleIcon = root.querySelector('.vision-scale-source img');
      var panels = Array.from(root.querySelectorAll('.enemy')).map(function (element) {
        var diagram = element.querySelector('.diagram');
        diagram.innerHTML = '<svg class="plot" viewBox="0 0 280 224" role="img"><circle class="vision-reference" cx="140" cy="112" r="94" fill="#eee" fill-opacity=".08" stroke="#eee" stroke-opacity=".45" stroke-width=".85"/><path class="vision-main" fill="#ff6a13" fill-opacity=".28" stroke="none"/><path class="vision-peripheral" fill="#eee" fill-opacity=".14" stroke="none"/><path d="M132.48 18L140 10.48L147.52 18Z" fill="#ddd" fill-opacity=".85"/><circle class="vision-center" cx="140" cy="112" r="2.162" fill="#eee" fill-opacity=".9"/><g aria-label="直径 200 米"><image class="vision-scale-icon" x="118" y="212" width="10" height="10" opacity=".72"/><text x="132" y="221" fill="#b8b8b8" font-family="Arial, Microsoft YaHei, sans-serif" font-size="10">200 米</text></g></svg><span class="missing" hidden>未明确配置</span>';
        diagram.querySelector('.vision-scale-icon').setAttribute('href', scaleIcon.getAttribute('src'));
        return {
          element: element, data: JSON.parse(element.getAttribute('data-vision')),
          svg: diagram.querySelector('.plot'), main: diagram.querySelector('.vision-main'),
          peripheral: diagram.querySelector('.vision-peripheral'), center: diagram.querySelector('.vision-center'),
          missing: diagram.querySelector('.missing'), numbers: Array.from(element.querySelectorAll('[data-number]')),
          current: null, target: null
        };
      });
      var reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
      var frame = 0;
      var selection = {profile: 'default', purpose: 'investigation', state: 'idle'};
      var labels = {profile: {default: '默认', legendary: '传奇'}, purpose: {investigation: '调查', alert: '警戒'}, state: {idle: '待机', combat: '战斗', aim: '瞄准'}};
      var controls = root.querySelector('.controls');
      [['profile','配置'],['purpose','视野'],['state','状态']].forEach(function (axis) {
        var row = document.createElement('div'); row.className = 'control-row';
        var label = document.createElement('span'); label.className = 'control-label'; label.textContent = axis[1];
        var buttons = document.createElement('div'); buttons.className = 'buttons'; buttons.setAttribute('role','group'); buttons.setAttribute('aria-label',axis[1]);
        Object.keys(labels[axis[0]]).forEach(function (key) {
          var button = document.createElement('button'); button.type = 'button'; button.textContent = labels[axis[0]][key];
          button.dataset.axis = axis[0]; button.dataset.value = key;
          button.addEventListener('click',function () {
            if (selection[axis[0]] === key) return;
            selection[axis[0]] = key; render(true);
          });
          buttons.appendChild(button);
        });
        row.append(label,buttons); controls.appendChild(row);
      });
      root.querySelectorAll('.native-icon').forEach(function (icon) {
        var image = icon.querySelector('img');
        if (!image) return;
        function mask() {
          if (!image.naturalWidth) return;
          if (typeof CSS === 'undefined' || !(CSS.supports('mask-image','url("x")') || CSS.supports('-webkit-mask-image','url("x")'))) return;
          // CDN masks require CORS; keep the original image until that request succeeds.
          var maskImage = new Image();
          maskImage.crossOrigin = 'anonymous';
          maskImage.onload = function () {
            icon.style.setProperty('--icon','url("'+maskImage.src+'")');
            icon.classList.add('masked');
          };
          maskImage.src = image.currentSrc || image.src;
        }
        image.addEventListener('load',mask); mask();
      });
      function sector(angle, radius) {
        if (!angle || !radius) return '';
        var r = 94 * radius / 100;
        // A full circle has no radial edge. Reuse this path for intermediate sectors.
        if (angle === 360) return 'M140 '+(112-r)+'A'+r+' '+r+' 0 1 1 140 '+(112+r)+'A'+r+' '+r+' 0 1 1 140 '+(112-r)+'Z';
        var a = angle * Math.PI / 360, x = r * Math.sin(a), y = r * Math.cos(a);
        return 'M140 112L'+(140-x).toFixed(3)+' '+(112-y).toFixed(3)+'A'+r+' '+r+' 0 '+(angle>180?1:0)+' 1 '+(140+x).toFixed(3)+' '+(112-y).toFixed(3)+'Z';
      }
      function paint(panel, values, final) {
        panel.current = values;
        panel.main.setAttribute('d',sector(values[0],values[1]));
        panel.peripheral.setAttribute('d',sector(values[2],values[3]));
        panel.center.style.display = '';
        panel.numbers.forEach(function (number) {
          var i = Number(number.dataset.number);
          number.textContent = final ? values[i] : Number(values[i].toFixed(panel.precision[i]));
        });
      }
      function render(animate) {
        if (frame) cancelAnimationFrame(frame);
        frame = 0;
        var moving = false;
        controls.querySelectorAll('button').forEach(function (button) { button.setAttribute('aria-pressed', String(selection[button.dataset.axis] === button.dataset.value)); });
        root.querySelectorAll('[data-profile-icon]').forEach(function (icon) { icon.style.display = icon.dataset.profileIcon === selection.profile ? '' : 'none'; });
        root.querySelector('[data-selection-label]').textContent = labels.purpose[selection.purpose]+' · '+labels.state[selection.state];
        root.querySelector('.selection-summary').setAttribute('aria-label',labels.profile[selection.profile]+'配置，'+labels.purpose[selection.purpose]+'视野，'+labels.state[selection.state]);
        panels.forEach(function (panel) {
          var profile = panel.data[selection.profile];
          var v = profile && profile[selection.state] && profile[selection.state][selection.purpose];
          var previous = panel.target;
          panel.target = v || null;
          panel.missing.hidden = !!v;
          panel.numbers.forEach(function (number) { number.nextElementSibling.hidden = !v; });
          if (v) {
            panel.svg.setAttribute('aria-label','主要 '+v[0]+'°／'+v[1]+' 米，周边 '+v[2]+'°／'+v[3]+' 米');
            panel.from = panel.current ? panel.current.slice() : v.slice();
            panel.precision = v.map(function (value,i) { return Number.isInteger(value) && (!previous || Number.isInteger(previous[i])) ? 0 : 1; });
            if (animate && !reduced.matches && panel.current && v.some(function (value,i) { return value !== panel.current[i]; })) {
              moving = true;
            } else {
              panel.from = v.slice();
              paint(panel,v,true);
            }
          } else {
            panel.current = null;
            panel.svg.setAttribute('aria-label','未明确配置');
            panel.main.setAttribute('d','');
            panel.peripheral.setAttribute('d','');
            panel.center.style.display = 'none';
            panel.numbers.forEach(function (number) { number.textContent = '—'; });
          }
        });
        if (!moving) return;
        var start = performance.now();
        function tick(now) {
          if (!root.isConnected) { frame = 0; return; }
          var progress = chartProgress(start, now);
          panels.forEach(function (panel) {
            if (!panel.target) return;
            var values = progress === 1 ? panel.target : panel.from.map(function (value,i) { return value+(panel.target[i]-value)*progress; });
            paint(panel,values,progress===1);
          });
          frame = progress < 1 ? requestAnimationFrame(tick) : 0;
        }
        frame = requestAnimationFrame(tick);
      }
      root.dataset.visionMounted = 'true';
      render(false);
      reduced.addEventListener('change',function () { if (reduced.matches) render(false); });
    });
  }
  if (document._td2ThreatVisionRuntime) {
    document._td2ThreatVisionRuntime();
  } else {
    document._td2ThreatVisionRuntime = initVision;
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',initVision,{once:true}); else initVision();
    if (typeof mw !== 'undefined' && mw.hook) mw.hook('wikipage.content').add(initVision);
  }

// Weapon control charts. Each article owns its stance and native model data.
function attributes(element, values) {
  Object.keys(values).forEach(function (key) { element.setAttribute(key, values[key]); });
  return element;
}

function axisNumber(value) {
  return String(value).replace("-", "−");
}

function makeSVG(tag, attrs, label) {
  var element = attributes(document.createElementNS("http://www.w3.org/2000/svg", tag), attrs);
  if (label !== undefined) element.textContent = label;
  return element;
}

var weaponGridCm = 25;
var weaponMinSpanCm = 200;
var weaponSpanStepCm = 2 * weaponGridCm;

function weaponChartSpan(horizontalReach, upperReach, bottomOrigin) {
  var margin = weaponGridCm / 2;
  var required = Math.max(2 * (horizontalReach + margin), (bottomOrigin ? 1 : 2) * (upperReach + margin));
  // At exactly half a cell from an edge, the next tier is already due.
  var steps = Math.max(0, Math.floor((required - weaponMinSpanCm) / weaponSpanStepCm) + 1);
  return weaponMinSpanCm + steps * weaponSpanStepCm;
}

function mountWeaponAxes(section, bottomOrigin) {
  var stage = section.querySelector(".recoil-stage");
  var chart = stage.querySelector("svg"), field = chart.querySelector("svg");
  var grid = field.querySelector(".grid, .recoil-grid");
  var axes = field.querySelector(".axes, .recoil-axes");
  var series = field.querySelector(".recoil-series");
  var labels = chart.querySelector(".ticks, .recoil-labels");
  var lines = makeSVG("path", {}), border = makeSVG("rect", {}), unit = makeSVG("text", {}, "厘米");
  grid.replaceChildren(lines, border);
  labels.replaceChildren(unit);

  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  var ticks = new Map();
  var span = weaponMinSpanCm, targetSpan = span, progress = 1, fadeStart = 0, frame = 0;
  var width, height, left, top, side = 0;

  function selectTick(value, horizontal) {
    var key = (horizontal ? "x" : "y") + value;
    var tick = ticks.get(key);
    if (!tick) {
      var text = makeSVG("text", horizontal ? {"text-anchor":"middle"} :
        {"text-anchor":"end", "dominant-baseline":"central"}, axisNumber(value));
      tick = {text:text, value:value, horizontal:horizontal, weight:0, from:0};
      ticks.set(key, tick);
      labels.append(text);
    }
    tick.to = 1;
  }

  function layout() {
    var small = width < 450, digits = String(targetSpan).length;
    var gutter = Math.max(small ? 34 : 40, 12 + 7 * digits);
    var headroom = 22, footroom = 32;
    side = Math.min(width - 2 * gutter, height - headroom - footroom);
    if (side <= 0) return;
    left = (width - side) / 2;
    top = headroom + (height - headroom - footroom - side) / 2;
    chart.setAttribute("viewBox", [0, 0, width, height].join(" "));
    attributes(field, {x:left, y:top, width:side, height:side});
    attributes(unit, {x:left, y:top - 8});

    // Keep ticks common to both tiers. On interruption, fade from their displayed weights.
    fadeStart = progress;
    ticks.forEach(function (tick) { tick.from = tick.weight; tick.to = 0; });
    var cells = targetSpan / weaponGridCm, pixelsPerCell = side / cells;
    var labelGap = Math.max(small ? 32 : 40, 14 + 7 * digits);
    var labelStep = Math.ceil(labelGap / pixelsPerCell) * weaponGridCm;
    for (var i = 0; i <= cells; i++) {
      var x = i * weaponGridCm - targetSpan / 2;
      var y = bottomOrigin ? i * weaponGridCm : x;
      var edge = i === 0 || i === cells, room = Math.min(i, cells - i) * pixelsPerCell;
      if (edge || x === 0 || (x % labelStep === 0 && room >= labelGap)) selectTick(x, true);
      if (edge || y === 0 || (y % labelStep === 0 && room >= 20)) selectTick(y, false);
    }
  }

  function drawScale() {
    if (side <= 0) return;
    var half = span / 2, low = bottomOrigin ? 0 : -half, high = low + span;
    var pixelsPerCm = side / span;
    field.setAttribute("viewBox", [-half, -high, span, span].join(" "));
    // Clip the incoming trace to the plot while leaving room below zero for baseline dots.
    if (series) {
      var clipHeight = span + weaponGridCm / 2;
      attributes(series, {x:-half, y:-high, width:span, height:clipHeight, viewBox:[-half, -high, span, clipHeight].join(" ")});
    }
    var path = [];
    for (var x = (Math.floor(-half / weaponGridCm) + 1) * weaponGridCm; x < half; x += weaponGridCm) {
      if (x !== 0) path.push("M " + x + " " + (-high) + " V " + (-low));
    }
    for (var y = (Math.floor(low / weaponGridCm) + 1) * weaponGridCm; y < high; y += weaponGridCm) {
      if (y !== 0) path.push("M " + (-half) + " " + (-y) + " H " + half);
    }
    lines.setAttribute("d", path.join(" "));
    attributes(border, {x:-half, y:-high, width:span, height:span});
    axes.setAttribute("d", "M " + (-half) + " 0 H " + half + " M 0 " + (-high) + " V " + (-low));

    var blend = progress === 1 ? 1 : (progress - fadeStart) / (1 - fadeStart);
    ticks.forEach(function (tick, key) {
      if (progress === 1 && !tick.to) {
        tick.text.remove();
        ticks.delete(key);
        return;
      }
      tick.weight = tick.from + (tick.to - tick.from) * blend;
      var v = tick.value;
      var room = (tick.horizontal ? half - Math.abs(v) : Math.min(high - v, v - low)) * pixelsPerCm;
      attributes(tick.text, {
        x:tick.horizontal ? left + (half + v) * pixelsPerCm : left - (bottomOrigin ? 10 : 5),
        y:tick.horizontal ? top + side + (bottomOrigin ? 24 : 19) : top + (high - v) * pixelsPerCm,
        opacity:tick.weight * Math.max(0, Math.min(1, 1 + room / 8))
      });
    });
  }

  function resize() {
    var bounds = stage.getBoundingClientRect();
    if (width === bounds.width && height === bounds.height) return;
    width = bounds.width;
    height = bounds.height;
    layout();
    drawScale();
  }
  resize();
  new ResizeObserver(resize).observe(stage);

  return function show(horizontalReach, upperReach, paintData) {
    var next = weaponChartSpan(horizontalReach, upperReach, bottomOrigin);
    var from = span, zoom = next !== from;
    var updateScale = zoom || next !== targetSpan;
    if (frame) cancelAnimationFrame(frame);
    frame = 0;
    targetSpan = next;
    if (updateScale) {
      progress = 0;
      layout();
    }

    function paint(p) {
      // Interpolate pixels per centimetre. The matching data fraction keeps the
      // circles and viewport in step, even when a stance change crosses several tiers.
      if (updateScale) {
        progress = p;
        span = p === 1 ? next : p === 0 ? from : 1 / ((1 - p) / from + p / next);
        drawScale();
      }
      if (paintData) paintData(p === 1 ? 1 : p * span / next);
    }
    if (reduced.matches || side <= 0 || !section.isConnected || (!zoom && !paintData)) {
      paint(1);
      return;
    }
    var start = performance.now(), duration = zoom ? 240 : 200;
    function tick(now) {
      var p = reduced.matches || !section.isConnected ? 1 : chartProgress(start, now, duration);
      paint(p);
      frame = p < 1 ? requestAnimationFrame(tick) : 0;
    }
    paint(0);
    frame = requestAnimationFrame(tick);
  };
}

function mountAccuracy(section, model) {
  var chart = section.querySelector(".chart");
  var world = chart.querySelector(".world");
  var initialRing = world.querySelector(".start-ring");
  var limitRing = world.querySelector(".end-ring");
  var point = world.querySelector(".pinpoint");
  var initialValue = section.querySelector('[data-part="start-angle"]');
  var limitValue = section.querySelector('[data-part="end-angle"]');
  var formatAngle = new Intl.NumberFormat("zh-CN", {maximumFractionDigits:2});
  var showExtent = mountWeaponAxes(section, false);
  var current;

  function radius(angle) {
    return projectionMetres * 100 * Math.tan(angle * Math.PI / 180);
  }

  function paint(angles) {
    var start = angles[0], end = angles[1];
    var startRadius = radius(start), endRadius = radius(end);
    current = angles;
    attributes(initialRing, {r:startRadius, visibility:start === end ? "hidden" : "visible"});
    limitRing.setAttribute("r", endRadius);
    point.setAttribute("visibility", Math.min(start, end) === 0 ? "visible" : "hidden");
    point.classList.toggle("at-end", end === 0);
    initialValue.textContent = formatAngle.format(start);
    limitValue.textContent = formatAngle.format(end);
  }

  return function showAccuracy(modeButton) {
    var mode = modeButton.dataset.mode;
    var target = model.angles[mode];
    chart.querySelector("title").textContent = model.name + "，" + modeButton.textContent + "精准度，" +
      projectionMetres + " 米，初始扩散 " + formatAngle.format(target[0]) + "°，极限扩散 " + formatAngle.format(target[1]) + "°";
    var reach = radius(Math.max(target[0], target[1]));
    if (!current || target.every(function (angle, i) { return angle === current[i]; })) {
      paint(target);
      showExtent(reach, reach);
      return;
    }
    var from = current;
    showExtent(reach, reach, function (progress) {
      paint(progress === 1 ? target : from.map(function (angle, i) { return angle + (target[i] - angle) * progress; }));
    });
  };
}

var projectionMetres = 10;
var distanceCaption = '<small class="td2-chart-distance">距离 ' + projectionMetres + ' 米</small>';
var panelMarkup = [
  '',
  '  <figure data-part="weapon-accuracy" class="spread-panel">',
  '    <figcaption>精准度</figcaption>',
  '    <div class="recoil-stage">',
  '      <svg class="chart" role="img" xmlns="http://www.w3.org/2000/svg">',
  '        <title></title>',
  '        <svg class="world" overflow="hidden">',
  '          <g class="board"></g>',
  '          <g class="grid"></g>',
  '          <path class="axes" vector-effect="non-scaling-stroke"/>',
  '          <circle class="start-ring" cx="0" cy="0"/>',
  '          <circle class="end-ring" cx="0" cy="0"/>',
  '          <path class="pinpoint" d="M 0 0 h 0" visibility="hidden"/>',
  '        </svg>',
  '        <g class="ticks" aria-hidden="true"></g>',
  '      </svg>',
  '    </div>',
  '    <div class="modes" role="group" aria-label="精准度射击姿态"></div>',
  '    ' + distanceCaption,
  '    <dl class="td2-chart-readouts">',
  '      <div class="td2-weapon-stat">',
  '        <dt>初始扩散</dt>',
  '        <dd><span data-part="start-angle"></span><span class="angle-unit">°</span></dd>',
  '      </div>',
  '      <div class="td2-weapon-stat">',
  '        <dt>极限扩散</dt>',
  '        <dd><span data-part="end-angle"></span><span class="angle-unit">°</span></dd>',
  '      </div>',
  '    </dl>',
  '  </figure>',
  '  <figure data-part="weapon-recoil" class="recoil-component">',
  '    <figcaption>后坐力</figcaption>',
  '    <div class="recoil-stage">',
  '      <svg class="recoil-graphic" role="img" xmlns="http://www.w3.org/2000/svg">',
  '        <title></title>',
  '        <svg class="recoil-field">',
  '          <g class="recoil-grid"></g>',
  '          <g class="recoil-target"></g>',
  '          <path class="recoil-axes" vector-effect="non-scaling-stroke"/>',
  '          <svg class="recoil-series" overflow="hidden"></svg>',
  '        </svg>',
  '        <g class="recoil-labels" aria-hidden="true"></g>',
  '      </svg>',
  '    </div>',
  '    ' + distanceCaption,
  '  </figure>'
].join('\n');

var stances = {stand:"站立瞄准", move:"移动瞄准", cover:"掩体瞄准", blind:"掩体盲射", hip:"腰射"};
var palette = [[91,222,133], [240,218,76], [255,157,65], [248,84,74]];

function shotColor(index, count) {
  var position = 3 * index / Math.max(1, count - 1);
  var segment = Math.min(2, Math.floor(position));
  var rgb = palette[segment].map(function (a, i) {
    return Math.round(a + (palette[segment + 1][i] - a) * (position - segment));
  });
  return "rgb(" + rgb.join(",") + ")";
}

function mountRecoil(section, trace) {
  var setExtent = mountWeaponAxes(section, true);
  var horizontalReach = 0, upperReach = 0;
  function includePoint(pair) {
    var point = pair.split(",");
    horizontalReach = Math.max(horizontalReach, Math.abs(Number(point[0])));
    upperReach = Math.max(upperReach, -Number(point[1]));
    return point;
  }
  var cloud = makeSVG("g", {class:"recoil-traces"});
  var farthest = Math.max.apply(null, trace.distances);
  var order = trace.groups.map(function (_, i) { return i; }).filter(function (i) { return i !== trace.medoid; });
  order.sort(function (a, b) { return trace.distances[b] - trace.distances[a]; });
  order.push(trace.medoid);
  order.forEach(function (index) {
    var representative = index === trace.medoid;
    var closeness = farthest ? 1 - trace.distances[index] / farthest : 1;
    var group = makeSVG("g", {class:"recoil-dots " + (representative ? "representative" : "other"),
      opacity:representative ? 1 : .34 + .38 * closeness});
    var dots = trace.groups[index].split(" ").map(function (pair, shot) {
      var point = includePoint(pair);
      return makeSVG("circle", {cx:point[0], cy:point[1], fill:shotColor(shot, trace.shots), "data-shot":shot + 1});
    });
    if (representative && dots.length > 1) {
      trace.path.split(" ").forEach(includePoint);
      var line = makeSVG("polyline", {class:"recoil-line", points:trace.path,
        fill:"none", stroke:"white", "stroke-linejoin":"round", "vector-effect":"non-scaling-stroke"});
      group.append.apply(group, dots.slice(1, -1).concat(line, dots[0], dots[dots.length - 1]));
    } else group.append.apply(group, dots);
    cloud.append(group);
  });
  section.querySelector(".recoil-series").replaceChildren(cloud);
  setExtent(horizontalReach, upperReach);
  section.querySelector(".recoil-graphic title").textContent = section.closest(".td2-weapon-charts").dataset.name +
    "，" + projectionMetres + " 米后坐力轨迹";
}

function drawTarget(node, target, url, onBaseline) {
  function rect(bounds, attrs) {
    return Object.assign({x:bounds[0], y:bounds[1], width:bounds[2], height:bounds[3]}, attrs);
  }
  var board = target.board;
  if (onBaseline) node.setAttribute("transform", "translate(0 " + -(board[1] + board[3]) + ")");
  node.append(makeSVG("rect", rect(board, {class:"recoil-board"})),
    makeSVG("image", rect(target.paper, {href:url, class:"recoil-paper", preserveAspectRatio:"xMidYMid meet"})),
    makeSVG("rect", rect(board, {class:"recoil-board-edge", fill:"none", "vector-effect":"non-scaling-stroke"})));
}

function mountRangeAxis(axis) {
  var marks = Array.from(axis.querySelectorAll(".td2-weapon-range-mark"));
  function layout() {
    var bounds = axis.getBoundingClientRect();
    if (!bounds.width) return;
    marks.forEach(function (mark) { mark.style.marginLeft = ""; });
    var labels = marks.map(function (mark) {
      var rect = mark.getBoundingClientRect();
      var anchor = rect.left - bounds.left;
      return {mark:mark, anchor:anchor, width:rect.width};
    });
    var totalWidth = labels.reduce(function (sum, label) { return sum + label.width; }, 0);
    var gap = Math.min(8, Math.max(0, (bounds.width - totalWidth) / Math.max(1, labels.length - 1)));
    var right = bounds.width;
    for (var i = labels.length - 1; i >= 0; i--) {
      var label = labels[i];
      label.left = Math.min(label.anchor, right - label.width);
      right = label.left - gap;
    }
    // Only push right when the leftmost labels have run out of room.
    var left = 0;
    labels.forEach(function (label) {
      left = Math.max(left, label.left);
      label.mark.style.marginLeft = (left - label.anchor) + "px";
      left += label.width + gap;
    });
  }
  axis.dataset.mounted = "true";
  layout();
  if (typeof ResizeObserver !== "undefined") {
    var observer = new ResizeObserver(layout);
    observer.observe(axis);
    marks.forEach(function (mark) { observer.observe(mark); });
  }
}

function initCharts(scope) {
  scope.querySelectorAll(".td2-weapon-range-axis:not([data-mounted])").forEach(mountRangeAxis);
  scope.querySelectorAll(".td2-weapon-charts:not([data-mounted])").forEach(function (root) {
    var img = root.querySelector(".td2-chart-art img");
    if (!img) return;
    root.dataset.mounted = "true";
    var target = JSON.parse(root.dataset.target);
    var body = document.createElement("div");
    body.className = "td2-chart-panels";
    body.innerHTML = panelMarkup;
    root.append(body);
    var accuracy = body.querySelector(".spread-panel");
    var angles = root.dataset.angles && JSON.parse(root.dataset.angles);
    var availableStances = Object.keys(stances).filter(function (key) { return angles && angles[key]; });
    if (availableStances.length) {
      drawTarget(accuracy.querySelector(".board"), target, img.currentSrc || img.src, false);
      var modes = accuracy.querySelector(".modes");
      var show = mountAccuracy(accuracy, {name:root.dataset.name, angles:angles});
      var select = function (button) {
        if (button.getAttribute("aria-pressed") === "true") return;
        Array.prototype.forEach.call(modes.children, function (b) { b.setAttribute("aria-pressed", String(b === button)); });
        show(button);
      };
      availableStances.forEach(function (key) {
        var button = document.createElement("button");
        button.type = "button";
        button.textContent = stances[key];
        button.dataset.mode = key;
        button.addEventListener("click", function () { select(button); });
        modes.append(button);
      });
      select(modes.firstElementChild);
    } else accuracy.remove();
    var recoil = body.querySelector(".recoil-component");
    if (root.dataset.recoil) {
      drawTarget(recoil.querySelector(".recoil-target"), target, img.currentSrc || img.src, true);
      mountRecoil(recoil, JSON.parse(root.dataset.recoil));
    } else recoil.remove();
  });
}
if (!document._td2BrandSetsRuntime.initWeaponCharts) {
  document._td2BrandSetsRuntime.initWeaponCharts = initCharts;
  if (document.readyState !== "loading") initCharts(document);
}
})();
