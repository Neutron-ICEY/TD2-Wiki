(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory(require('./page-scope.js'));else (root.TD2EditorLab = root.TD2EditorLab || {}).mediawikiAdapter = factory(root.TD2EditorLab.pageScope);
})(typeof globalThis !== 'undefined' ? globalThis : this, function (scope) {
  'use strict';

  const SUMMARY = '';
  const ORIGIN = 'https://td2.huijiwiki.com';
  const known = new Set(['editconflict', 'badtoken', 'permissiondenied', 'protectedpage', 'assertuserfailed', 'assertnameduserfailed', 'ratelimited', 'abusefilter-disallowed', 'captcha', 'missingtitle', 'articleexists']);
  function error(code, details) {
    return Object.assign(new Error(code), {
      code
    }, details || {});
  }
  function response(data) {
    if (!data || typeof data !== 'object') throw error('INVALID_API_RESPONSE');
    if (data.error) throw error(data.error.code || 'API_ERROR', {
      definite: true
    });
    if (data.warnings) throw error('API_WARNING');
    return data;
  }
  function revision(data, title, expectedRevision) {
    response(data);
    if (data.query?.normalized || data.query?.redirects) throw error('TITLE_NORMALIZATION_REQUIRES_REVIEW');
    const pages = data.query?.pages;
    if (!Array.isArray(pages) || pages.length !== 1) throw error('INVALID_PAGE_RESPONSE');
    const page = pages[0];
    if (page.title !== title || page.ns !== 0) throw error('TARGET_MISMATCH');
    if (page.missing) return {
      title,
      missing: true,
      starttimestamp: data.curtimestamp,
      user: data.query.userinfo
    };
    if (page.invalid || page.redirect || !Number.isSafeInteger(page.pageid)) throw error('INVALID_TARGET');
    const rows = page.revisions;
    if (!Array.isArray(rows) || rows.length !== 1) throw error('INVALID_REVISION_RESPONSE');
    const row = rows[0],
      slot = row.slots?.main;
    if (!slot || slot.contentmodel !== 'wikitext' || slot.contentformat !== 'text/x-wiki' || typeof slot.content !== 'string') throw error('UNSUPPORTED_CONTENT');
    if (!Number.isSafeInteger(row.revid) || row.revid <= 0 || !Number.isSafeInteger(row.parentid) || !row.timestamp || !row.sha1 || !data.curtimestamp) throw error('MISSING_REVISION_METADATA');
    if (expectedRevision && row.revid !== expectedRevision) throw error('REVISION_MISMATCH');
    const user = data.query.userinfo;
    return {
      title,
      pageid: page.pageid,
      revid: row.revid,
      parentid: row.parentid,
      timestamp: row.timestamp,
      sha1: row.sha1,
      contentmodel: slot.contentmodel,
      raw: slot.content,
      comment: row.comment,
      starttimestamp: data.curtimestamp,
      user: user ? {
        id: user.id,
        name: user.name,
        anon: !!user.anon
      } : null
    };
  }
  function create(api, options = {}) {
    if (options.origin !== ORIGIN) throw error('ORIGIN_NOT_ALLOWED');
    const target = options.target;
    if (!options.contractPages || typeof target !== 'string' || !target || target.includes(':')) throw error('TARGET_NOT_ALLOWED');
    let saving = false,
      halted = false,
      readSequence = 0;
    const readSession = Date.now().toString(36) + Math.random().toString(36).slice(2);
    async function get(params) {
      try {
        return response(await api.get({
          ...params,
          format: 'json',
          formatversion: 2,
          maxage: 0,
          smaxage: 0,
          requestid: readSession + '-' + ++readSequence
        }));
      } catch (e) {
        if (e?.code) throw e;
        throw error(known.has(e) ? e : 'READ_API_FAILURE');
      }
    }
    async function permissions(creating = false, expectedUser) {
      const data = await get({
          action: 'query',
          meta: 'userinfo',
          uiprop: 'rights|groups',
          prop:'info',titles:target,intestactions:'edit'
        }),
        user = data.query?.userinfo;
      if (!user || user.anon || !(user.id > 0) || !user.name || !user.rights?.includes('edit') || creating && !user.rights.includes('createpage')) throw error('EDIT_LOGIN_REQUIRED');
      if(!user.groups?.includes('sysop') || data.query?.pages?.[0]?.actions?.edit!==true)throw error('EDITOR_ACCESS_DENIED');
      if (expectedUser && (user.id !== expectedUser.id || user.name !== expectedUser.name)) throw error('ACCOUNT_CHANGED');
      return {
        id: user.id,
        name: user.name
      };
    }
    async function load(revid) {
      const params = {
        action: 'query',
        prop: 'revisions|info',
        meta: 'userinfo',
        rvprop: 'ids|timestamp|sha1|content|contentmodel|comment',
        rvslots: 'main',
        curtimestamp: 1
      };
      if (revid) params.revids = revid;else params.titles = target;
      const result = revision(await get(params), target, revid);
      if (!result.missing && options.pageid && result.pageid !== options.pageid) throw error('PAGE_IDENTITY_CHANGED');
      if(!result.missing){const checked=scope.check(result.raw,result.pageid);if(!checked.ok)throw error('PAGE_CONTRACT_REJECTED: '+checked.reason);}
      return result;
    }
    async function commit(input, text, creating, onVerify, metadata = {}) {
      if (!options.enableWrites) throw error('WRITES_DISABLED');
      if(creating)throw error('CREATE_SCOPE_DENIED');
      const checked=scope.check(text,input.pageid);if(!checked.ok)throw error('PAGE_CONTRACT_REJECTED: '+checked.reason);
      if (halted) throw error('HALTED_REQUIRES_REVIEW');
      if (saving) throw error('SAVE_IN_PROGRESS');
      const base = JSON.parse(JSON.stringify(input));
      if (typeof text !== 'string' || base.title !== target) throw error('TARGET_MISMATCH');
      const customSummary = Object.prototype.hasOwnProperty.call(metadata,'summary');
      const summary=customSummary?metadata.summary:'';
      if(typeof summary!=='string'||Array.from(summary).length>500||/[\r\n\x00-\x1f]/.test(summary)||summary.trim()!==summary)throw error('INVALID_EDIT_SUMMARY');
      saving = true;
      let postStarted = false,
        receipt = null,
        actual = null,
        latest = null;
      try {
        if (!base.user?.name || !(base.user.id > 0)) throw error('SESSION_USER_REQUIRED');
        const user = await permissions(creating, base.user),
          current = await load();
        if (creating) {
          if (!base.missing || !current.missing) throw error('TARGET_ALREADY_EXISTS');
        } else {
          if (base.missing || current.missing || current.pageid !== base.pageid || current.revid !== base.revid || current.raw !== base.raw) throw error('editconflict', {
            stage: 'CLIENT_PRECHECK'
          });
          if (text === base.raw) return {
            nochange: true,
            revision: current
          };
        }
        if (!base.starttimestamp) throw error('MISSING_START_TIMESTAMP');
        const tokens = await get({
          action: 'query',
          meta: 'tokens',
          type: 'csrf',
          assert: 'user',
          assertuser: user.name
        });
        const token = tokens.query?.tokens?.csrftoken;
        if (typeof token !== 'string' || token.length < 3 || token === '+\\') throw error('TOKEN_UNAVAILABLE');
        const params = {
          action: 'edit',
          title: target,
          text,
          summary,
          starttimestamp: base.starttimestamp,
          assert: 'user',
          assertuser: user.name,
          watchlist: 'nochange',
          format: 'json',
          formatversion: 2,
          token
        };
        if (creating) params.createonly = true;else {
          params.nocreate = true;
          params.baserevid = base.revid;
        }
        // basetimestamp can suppress same-account conflicts in upstream 1.38.4. Do not add it.
        postStarted = true;
        const saved = response(await api.post(params));
        if (saved.edit?.captcha) throw error('captcha', {
          definite: true
        });
        const edit = saved.edit;
        if (!edit || edit.result !== 'Success' || edit.title !== target || !Number.isSafeInteger(edit.pageid)) throw error('EDIT_NOT_CONFIRMED');
        receipt = {
          title: target,
          pageid: edit.pageid,
          oldrevid: edit.oldrevid,
          newrevid: edit.newrevid,
          newtimestamp: edit.newtimestamp,
          nochange: Object.prototype.hasOwnProperty.call(edit, 'nochange'),
          summary: params.summary
        };
        if (onVerify) onVerify();
        if (!creating && edit.pageid !== base.pageid) throw error('PAGE_IDENTITY_CHANGED');
        if (receipt.nochange) {
          actual = await load();
          if (actual.missing || actual.pageid !== edit.pageid || actual.raw !== text) throw error('NOCHANGE_REQUIRES_REVIEW');
        } else {
          if (!Number.isSafeInteger(edit.newrevid) || !edit.newtimestamp) throw error('EDIT_NOT_CONFIRMED');
          actual = await load(edit.newrevid);
          if (actual.pageid !== edit.pageid) throw error('PAGE_IDENTITY_CHANGED');
          if (actual.parentid !== (creating ? 0 : base.revid) || !creating && edit.oldrevid !== base.revid) throw error('SERVER_MERGE_REQUIRES_REVIEW');
          if (actual.raw !== text) throw error('SAVED_RAW_MISMATCH');
        }
        if(customSummary && !receipt.nochange && actual.comment!==summary)throw error('SAVED_SUMMARY_MISMATCH');
        latest = await load();
        if (latest.missing || latest.pageid !== actual.pageid || latest.revid !== actual.revid || latest.raw !== actual.raw) throw error('LATEST_CHANGED_AFTER_SAVE');
        if (latest.user?.id !== user.id || latest.user?.name !== user.name) throw error('ACCOUNT_CHANGED');
        return {
          nochange: receipt.nochange,
          revision: actual,
          receipt
        };
      } catch (e) {
        const code = e?.code || (known.has(e) ? e : postStarted ? 'SAVE_OUTCOME_UNKNOWN' : 'PRE_SAVE_FAILURE');
        const definite = e?.definite || known.has(code);
        if (postStarted && (!definite || receipt)) halted = true;
        throw error(code, {
          stage: e.stage || (receipt ? 'VERIFY' : postStarted ? 'SERVER' : 'PRE_SAVE'),
          outcome: receipt ? 'WRITTEN_UNVERIFIED' : postStarted && !definite ? 'UNKNOWN' : 'FAILED',
          receipt,
          actual,
          latest
        });
      } finally {
        saving = false;
      }
    }
    async function preview(text){
      if(typeof text!=='string')throw error('INVALID_PREVIEW_TEXT');
      const data=response(await api.post({action:'parse',title:target,text,contentmodel:'wikitext',prop:'text|modules|jsconfigvars|headhtml|parsewarnings',preview:true,disableeditsection:true,useskin:'huijidragonhide',format:'json',formatversion:2}));
      if(typeof data.parse?.text!=='string')throw error('INVALID_PREVIEW_RESPONSE');
      return {html:data.parse.text,head:data.parse.headhtml||'',modules:data.parse.modules||[],styles:data.parse.modulestyles||[],warnings:data.parse.parsewarnings||[]};
    }
    async function loadCatalog(){
      const result=await preview('{{#invoke:TD2编辑数据|export}}');
      const marker=new DOMParser().parseFromString(result.html,'text/html').querySelector('[data-td2-editor-catalog]');
      if(!marker)throw error('EDITOR_CATALOG_UNAVAILABLE');
      const catalog=JSON.parse(marker.getAttribute('data-td2-editor-catalog'));
      if(!catalog?.options?.equipmentCatalog)throw error('EDITOR_CATALOG_UNAVAILABLE');
      return catalog;
    }
    return {
      loadCatalog,
      preview,
      load,
      permissions,
      get saving() {
        return saving;
      },
      get halted() {
        return halted;
      },
      save: (base, text, onVerify, metadata) => commit(base, text, false, onVerify, metadata),
      initialize: (base, text, onVerify, metadata) => commit(base, text, true, onVerify, metadata)
    };
  }
  return {
    create,
    revision,
    ORIGIN,
    SUMMARY
  };
});
