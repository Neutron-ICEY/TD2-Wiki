/* Lightweight shared administrator entry. No domain modules or editor CSS before activation. */
(function () {
  'use strict';

  const policy = mw.td2EditorEntryPolicy;
  const context = {
    origin: location.origin, title: mw.config.get('wgPageName').replace(/_/g,' '), pageid: mw.config.get('wgArticleId'),
    namespace: mw.config.get('wgNamespaceNumber'), action: mw.config.get('wgAction'), historical: new URL(location.href).searchParams.has('oldid') || new URL(location.href).searchParams.has('diff'),
    user: {id: mw.config.get('wgUserId'), name: mw.config.get('wgUserName'), groups: mw.config.get('wgUserGroups')}
  };
  // Match exact approved scope before loading API or reading any page content.
  const match = policy && policy.select(context);
  if (!match || !policy.isAdmin(context.user) || mw.td2EditorEntryStart) return;
  const target = context.title, pageid = context.pageid, runtime = match.form.runtime;
  mw.td2EditorEntryStart = mw.loader.using(['mediawiki.util', 'mediawiki.api']).then(async () => {
    const api = new mw.Api();
    async function allowed() {
      const result = await api.get({action: 'query', meta: 'userinfo', uiprop: 'groups|rights',
        prop: match.contractPage?'info|templates':'info', ...(match.contractPage?{tltemplates:policy.scope.templates.map(t=>'Template:'+t).join('|'),tllimit:2}:{}), titles: target, intestactions: 'edit', formatversion: 2, maxage: 0, smaxage: 0});
      if(!policy.verify(context, match, result))return false;
      if(match.contractPage){
        if(!result.query.pages[0].templates?.length)return false;
        const source=await api.get({action:'query',prop:'revisions',pageids:pageid,rvprop:'content',rvslots:'main',formatversion:2,maxage:0,smaxage:0});
        const p=source.query?.pages?.[0];
        if(p?.pageid!==pageid||p?.title!==target)return false;
        const checked=policy.scope.check(p.revisions?.[0]?.slots?.main?.content,pageid);
        if(!checked.ok){
          if(!document.getElementById('td2-editor-unavailable')){
            const note=document.createElement('p');note.id='td2-editor-unavailable';note.textContent='JS 表单暂不能安全编辑此页：'+checked.reason+'。请使用标准源代码编辑。';
            document.getElementById('mw-content-text')?.prepend(note);
          }
          return false;
        }
      }
      return true;
    }
    if (!await allowed()) return;
    function mountEntry() {
      if (document.getElementById('td2-js-edit-entry')) return;
      const historical = new URL(location.href).searchParams.has('oldid') || new URL(location.href).searchParams.has('diff');
      const readParams = {};
      const currentURL = mw.util.getUrl(target, readParams),
        editURL = mw.util.getUrl(target, Object.assign({}, readParams, {td2edit:'1'}));
      const text = '编辑表单';
      let item=mw.util.addPortletLink('p-cactions', editURL, text, 'td2-js-edit-entry');
      if (!item) {
        const heading = document.getElementById('firstHeading');
        if (!heading) {
          console.warn('TD2 entry mount unavailable');
          return;
        }
        item = document.createElement('span');
        item.id = 'td2-js-edit-entry';
        const a = document.createElement('a');
        a.href = editURL;
        a.textContent = text;
        item.append(a);
        heading.append(item);
      }
      const link = item.matches('a') ? item : item.querySelector('a');
      // Visible non-secret diagnostics distinguish missing export from version mismatch.
      const expected=runtime.expected, runtimeRevision=runtime.revision;
      item.dataset.entryBuild='ENTRY_BUILD_ID';
      item.dataset.formId=match.form.id;
      item.dataset.entryVersion=expected;
      item.dataset.runtimeRevision=runtimeRevision;
      let active = null,
        loading = false;
      async function enter() {
        if (loading || active) return;
        loading = true;
        link.setAttribute('aria-disabled', 'true');
        try {
          item.dataset.loadStage='permission';
          if (!await allowed()) throw new Error('EDITOR_ACCESS_DENIED');
          item.dataset.loadStage='dependencies';
          await mw.loader.using('mediawiki.api');
          if (!/^[1-9][0-9]*$/.test(runtimeRevision)) throw new Error('UNBOUND_RUNTIME_REVISION');
          item.dataset.loadStage='runtime';
          if (!mw[runtime.exportName]) {
            // Fixed resource identity; arbitrary query-provided script/API URLs are never accepted.
            await mw.loader.getScript(mw.util.getUrl(runtime.title, {
              action: 'raw',
              ctype: 'text/javascript',
              oldid: runtimeRevision

            }));
          }
          item.dataset.exportPresent=String(!!mw[runtime.exportName]);
          item.dataset.actualVersion=mw[runtime.exportName] ? String(mw[runtime.exportName].version) : '';
          if (!mw[runtime.exportName]) throw new Error('EDITOR_EXPORT_MISSING');
          if (mw[runtime.exportName].version !== expected) throw new Error('EDITOR_VERSION_MISMATCH');
          item.dataset.loadStage='mounted';
          active = await mw[runtime.exportName].open({
            onExit: () => {
              active = null;
              location.assign(currentURL);
            }
          });
        } catch (e) {
          item.dataset.loadStage='failed';
          item.dataset.loadError=e.message;
          link.textContent = '编辑器未能加载，点击重试';
          link.title = e.message;
          console.warn('TD2 editor load failed: ' + e.message);
        } finally {
          loading = false;
          link.removeAttribute('aria-disabled');
        }
      }
      link.addEventListener('click', e => {
        if (historical) return;
        e.preventDefault();
        enter();
      });
      if (!historical && new URL(location.href).searchParams.get('td2edit') === '1') enter();
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mountEntry, {
      once: true
    });else mountEntry();
  }).catch(() => {
    // Access or network uncertainty must leave Reader intact; no retry loop.
    console.warn('TD2 editor entry access could not be verified.');
  });
})();
