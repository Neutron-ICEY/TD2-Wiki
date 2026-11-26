(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory(require('./local-session.js'), require('./state.js'));else root.TD2EditorLab.siteSession = factory(root.TD2EditorLab.localSession, root.TD2EditorLab.state);
})(typeof globalThis !== 'undefined' ? globalThis : this, function (local, domain) {
  'use strict';

  const copy = value => value == null ? value : JSON.parse(JSON.stringify(value));
  function create(adapter, catalog, options = {}) {
    let base = null,
      session = null,
      facade = null,
      savedState = null,
      busy = false,
      lastError = null,
      receipt = null;
    let status = 'NOT_LOADED',
      generation = 0,
      disposed = false,
      pendingInput = false,
      submission = null,
      needsReload = false,
      summary = '', creating = false;
    function idle() {
      if (disposed) throw new Error('SESSION_DISPOSED');
      if (busy) throw new Error('SAVE_IN_PROGRESS');
    }
    async function currentOptions() {
      if (!adapter.loadCatalog) return options;
      const latest = await adapter.loadCatalog();
      return {...options, ...latest.options};
    }
    function accept(nextBase, editorOptions) {
      const next = local.create(nextBase.raw, catalog, {...editorOptions,creating,pageTitle:nextBase.title});
      if (next.blockers.length) {
        const e = new Error('SITE_LOAD_BLOCKED: ' + next.blockers.map(b => b.path + ' ' + b.code).join('; '));
        e.blockers = next.blockers;
        throw e;
      }
      base = copy(nextBase);
      session = next;
      savedState = next.state;
      pendingInput = false;
      needsReload = false;
      // Guard every mutating/serializing call even if a host forgot to disable a control.
      facade = {};
      Object.keys(next).forEach(key => {
        if (typeof next[key] === 'function') facade[key] = (...args) => {
          idle();
          return next[key](...args);
        };else Object.defineProperty(facade, key, {
          enumerable: true,
          get: () => next[key]
        });
      });
    }
    const api = {
      get editor() {
        return facade;
      },
      get state() {
        return session?.state;
      },
      get base() {
        return copy(base);
      },
      get busy() {
        return busy;
      },
      get status() {
        return status;
      },
      get lastError() {
        return lastError;
      },
      get receipt() {
        return copy(receipt);
      },
      get submission() {
        return copy(submission);
      },
      get summary(){return summary;},
      setSummary(value){idle();summary=value;},
      get creating(){return creating;},
      get contentDirty() {
        return pendingInput || !!session && (session.needsCleanup || !domain.semanticEqual(session.state, savedState));
      },
      get dirty() {
        return summary!=='' || api.contentDirty;
      },
      get needsReload() {
        return needsReload;
      },
      noteInput(changed) {
        idle();
        pendingInput = changed;
      },
      invalidate() {
        needsReload = true;
      },
      dispose() {
        disposed = true;
        generation++;
        status = 'DISPOSED';
      },
      preview() {
        idle();
        if (!session) throw new Error('NOT_LOADED');
        return session.serialize().raw;
      },
      async load() {
        if (disposed) throw new Error('SESSION_DISPOSED');
        if (busy) throw new Error('SAVE_IN_PROGRESS');
        const request = ++generation;
        busy = true;
        status = 'LOADING';
        try {
          if (adapter.permissions) await adapter.permissions(false);
          const nextBase = await adapter.load();
          const editorOptions = await currentOptions();
          if (disposed || request !== generation) return null;
          if(!nextBase.missing&&options.createOnly&&!base)throw new Error('TARGET_ALREADY_EXISTS');
          creating=nextBase.missing===true && options.createMode===true;
          if (nextBase.missing && !creating) throw new Error('TARGET_NOT_INITIALIZED');
          if(creating){await adapter.permissions(true,nextBase.user);nextBase.raw=options.creationRaw||local.blank(options.creationTemplate);}
          summary='';
          if (base && !base.missing && (nextBase.pageid !== base.pageid || nextBase.title !== base.title)) throw new Error('PAGE_IDENTITY_CHANGED');
          accept(nextBase, editorOptions);
          lastError = null;
          status = 'UNCHANGED';
          return session.state;
        } catch (e) {
          if (!disposed) {
            needsReload = true;
            lastError = e.code || e.message;
            status = 'LOAD_FAILED';
          }
          throw e;
        } finally {
          busy = false;
        }
      },
      edit(key, value) {
        idle();
        if (!session) throw new Error('NOT_LOADED');
        session.edit(key, value);
      },
      async save(onVerify) {
        idle();
        if (!session) throw new Error('NOT_LOADED');
        if (needsReload) throw new Error('RELOAD_REQUIRED');
        busy = true;
        lastError = null;
        const request = generation;
        try {
          const expected = session.serialize().raw;
          submission = {
            target: base.title,
            base: copy(base),
            state: session.state,
            expected,
            summary
          };
          if (!creating && expected === base.raw) {
            if (pendingInput) throw new Error('UNCOMMITTED_INPUT');
            receipt = null;
            status = 'UNCHANGED';
            return session.state;
          }
          const editorOptions = await currentOptions();
          if (disposed || request !== generation) return null;
          if (editorOptions.equipmentCatalog && !session.matchesCatalog(editorOptions.equipmentCatalog[session.identity])) {
            needsReload = true;
            throw new Error('本页可编辑字段已更新，请先保留输入并重读数据。');
          }
          status = 'SUBMITTING';
          const write=creating?adapter.initialize:adapter.save;
          const result = await write(submission.base, submission.expected, () => {
            status = 'VERIFYING';
            if (onVerify) onVerify();
          }, {summary:submission.summary});
          if (disposed || generation !== request) return null;
          receipt = result.receipt || null;
          creating=false;
          accept(result.revision, editorOptions);
          summary='';
          status = 'VERIFIED';
          return session.state;
        } catch (e) {
          if (!disposed) {
            lastError = e.code || e.message;
            receipt = e.receipt || receipt;
            status = e.outcome === 'WRITTEN_UNVERIFIED' ? 'WRITTEN_UNVERIFIED' : e.outcome === 'UNKNOWN' ? 'OUTCOME_UNKNOWN' : 'FAILED';
            if (e.outcome === 'WRITTEN_UNVERIFIED' || e.outcome === 'UNKNOWN' || e.code === 'editconflict' || e.code === 'ACCOUNT_CHANGED') needsReload = true;
          }
          throw e;
        } finally {
          busy = false;
        }
      }
    };
    return api;
  }
  return {
    create
  };
});
