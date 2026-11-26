(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = {
    mount: factory
  };else root.TD2EditorLab.siteHost = {
    mount: factory
  };
})(typeof globalThis !== 'undefined' ? globalThis : this, function (environment) {
  'use strict';

  const {
    document,
    window,
    lab,
    config,
    adapter,
    onExit
  } = environment;
  const host = document.getElementById('mw-content-text');
  if (!host || document.querySelector('[data-td2-js-editor]')) throw new Error('MOUNT_UNAVAILABLE');
  const root = document.createElement('section');
  root.dataset.td2JsEditor = '';
  root.dataset.build = config.version;
  const style = document.createElement('style');
  style.dataset.td2EditorStyle = '';
  style.textContent = config.css;
  document.head.append(style);
  host.prepend(root);
  function el(tag, text) {
    const e = document.createElement(tag);
    if (text !== undefined) e.textContent = text;
    return e;
  }
  const status = el('p', '正在读取当前资料…');
  status.setAttribute('role', 'status');
  status.setAttribute('aria-live', 'polite');
  const form = el('form'),
    fields = el('fieldset'),
    container = el('div'),
    footer = el('footer');
  form.noValidate = true;
  fields.className = 'td2-editor-fields';
  fields.append(container);
  function actionBar() {
    const bar = el('div');
    bar.className = 'td2-editor-actions';
    bar.setAttribute('role', 'group');
    bar.setAttribute('aria-label', '表单操作');
    const preview = el('button', '预览');
    const save = el('button', '保存');
    const reload = el('button', '重读数据');
    const exit = el('button', '返回页面');
    preview.type = reload.type = exit.type = 'button';
    save.type = 'submit';
    bar.append(preview, save, exit, reload);
    return {bar, preview, save, reload, exit};
  }
  const actions = [actionBar(), actionBar()];
  const summaryInput=el('input');summaryInput.type='text';
  const summaryField=lab.uiPrimitives.create(document).Field({id:'td2-edit-summary',label:'编辑摘要',control:summaryInput,help:'本次提交说明，可留空；最多500个Unicode字符，不写入资料正文。'});
  const previewArea=el('section');
  const readerPreview=lab.readerPreview.create({document,adapter,container:previewArea});
  footer.append(summaryField.element, status, actions[1].bar);
  form.append(actions[0].bar, fields, footer);
  root.append(el('h2', '编辑表单'), form, previewArea);
  let controller = lab.siteSession.create(adapter, config.catalog, config.options),
    view = null,
    disposed = false,
    previewPending = false,
    baselineInputs = '',
    unloadAttached = false,
    confirmPending = null;
  function inputs() {
    return JSON.stringify([...container.querySelectorAll('input,textarea,select')].filter(e=>e.dataset.editorTransient!=='true').map(e => [e.id, e.value, e.checked]));
  }
  function beforeUnload(e) {
    if (controller.dirty) {
      e.preventDefault();
      e.returnValue = '';
    }
  }
  function sync() {
    if (disposed) return;
    const blocked = controller.busy || !!confirmPending;
    fields.disabled = blocked;
    summaryInput.disabled=blocked;
    actions.forEach(action => {
      action.preview.disabled = blocked || previewPending || !view;
      action.save.disabled = blocked || !view || !controller.contentDirty || controller.needsReload || adapter.halted;
      action.reload.disabled = action.exit.disabled = blocked;
    });
    root.dataset.dirty = String(controller.dirty);
    root.dataset.sessionStatus = controller.status;
    root.dataset.busy = String(controller.busy);
    form.setAttribute('aria-busy', String(controller.busy));
    if (controller.dirty && !unloadAttached) {
      window.addEventListener('beforeunload', beforeUnload);
      unloadAttached = true;
    }
    if (!controller.dirty && unloadAttached) {
      window.removeEventListener('beforeunload', beforeUnload);
      unloadAttached = false;
    }
  }
  function render() {
    view = null;
    view = lab.editorView.create({
      document,
      container,
      session: controller.editor,
      api: lab,
      onChange: inputChanged
    });
    baselineInputs = inputs();
    summaryInput.value=controller.summary;
    sync();
  }
  async function load() {
    view = null;
    readerPreview.invalidate();
    container.replaceChildren();
    status.textContent = '正在读取当前资料…';
    const promise = controller.load();
    sync();
    try {
      await promise;
      if (disposed) return;
      render();
      status.textContent = '已载入当前版本，可以编辑。';
    } catch (e) {
      if (!disposed) {
        status.textContent = '无法编辑：' + e.message + '。原文未改动，可使用标准源代码编辑。';
      }
    } finally {
      sync();
    }
  }
  function inputChanged() {
    if (!controller.busy && view) {
      readerPreview.invalidate();
      controller.noteInput(inputs() !== baselineInputs);
      sync();
    }
  }
  container.addEventListener('input', inputChanged);
  container.addEventListener('change', inputChanged);
  summaryInput.addEventListener('input',()=>{controller.setSummary(summaryInput.value);summaryField.setError('');sync();});
  function scrollPreview() {
    const bottom=Array.from(document.querySelectorAll('#skin-root, .skin-subnav')).reduce((offset,nav)=>{
      const rect=nav.getBoundingClientRect();
      return /^(fixed|sticky)$/.test(window.getComputedStyle(nav).position)&&rect.width&&rect.bottom>0?Math.max(offset,rect.bottom):offset;
    },0);
    previewArea.style.scrollMarginTop=(Math.ceil(bottom)+16)+'px';
    previewArea.scrollIntoView({block:'start'});
  }
  async function preview() {
    if(disposed||controller.busy||previewPending||!view)return;
    if(!view.validate()){status.textContent='请修正字段错误后预览；尚未保存。';return;}
    previewPending=true;
    sync();
    try{const raw=controller.preview(),pending=readerPreview.show(raw);scrollPreview();const result=await pending;if(result&&!disposed)scrollPreview();}
    catch(e){if(!disposed)status.textContent='预览未完成，输入保留。 '+(e.code||e.message);}
    finally{previewPending=false;sync();}
  }
  function confirmSave() {
    return new Promise(resolve => {
      const dialog=el('dialog'),accept=el('button','确定保存'),cancel=el('button','取消');
      dialog.setAttribute('aria-label','确认保存');
      accept.type=cancel.type='button';
      dialog.append(el('p','确认保存当前修改？'),accept,cancel);root.append(dialog);
      function finish(approved){if(confirmPending!==finish)return;confirmPending=null;dialog.close();dialog.remove();sync();resolve(approved);}
      confirmPending=finish;
      accept.addEventListener('click',()=>finish(true));cancel.addEventListener('click',()=>finish(false));
      dialog.addEventListener('cancel',e=>{e.preventDefault();finish(false);});
      sync();dialog.showModal();cancel.focus();
    });
  }
  form.addEventListener('submit', async e => {
    e.preventDefault();
    if (disposed || confirmPending || controller.busy || !view || !controller.contentDirty || controller.needsReload || adapter.halted) return;
    try {
      if (!view.validate()) {
        status.textContent = '请修正字段错误，尚未保存。';
        return;
      }
      const summary=controller.summary;
      if(Array.from(summary).length>500 || /[\r\n\x00-\x1f]/.test(summary)||summary.trim()!==summary){summaryField.setError('摘要最多500个Unicode字符，不能含换行、控制字符或首尾空白。');summaryInput.focus();status.textContent='请修正编辑摘要，尚未保存。';return;}
      if (!await confirmSave() || disposed) return;
      const pending = controller.save(() => {
        if (disposed) return;
        status.textContent = '服务端已接受，正在回读核验；请稍候…';
        sync();
      });
      sync();
      status.textContent = '正在提交，请稍候…';
      await pending;
      if (disposed) return;
      render();
      status.textContent = controller.status === 'UNCHANGED' ? (controller.summary?'没有资料内容变化；摘要尚未提交，已保留。':'没有需要保存的修改。') : '保存并核验成功，可以继续修改或返回阅读页。';
    } catch (e) {
      if (disposed) return;
      const prefix = controller.status === 'WRITTEN_UNVERIFIED' ? '已提交，结果尚未完成核验；请先核查远端，禁止重复提交。' : controller.status === 'OUTCOME_UNKNOWN' ? '写入结果未知；本地输入保留，禁止自动重发。' : e.code === 'editconflict' ? '编辑冲突；本地输入保留，请核对当前版本。' : '未完成保存，本地输入保留。';
      status.textContent = prefix + ' ' + (e.code || e.message);
    } finally {
      sync();
    }
  });
  function reload() {
    if (controller.busy) return;
    if ((controller.dirty || controller.needsReload) && !window.confirm('重新读取会放弃本地未保存输入。请先核对远端结果，是否继续？')) return;
    if (adapter.halted) {
      status.textContent = '本会话写入已暂停。请返回阅读页核对结果，再重新进入。';
      return;
    }
    load();
  }
  function dispose() {
    if (disposed) return;
    disposed = true;
    if(confirmPending)confirmPending(false);
    controller.dispose();
    readerPreview.dispose();
    window.removeEventListener('beforeunload', beforeUnload);
    window.removeEventListener('pageshow', pageShow);
    container.removeEventListener('input', inputChanged);
    container.removeEventListener('change', inputChanged);
    root.remove();
    style.remove();
    view = null;
  }
  function exit() {
    if (controller.busy) return;
    if (controller.dirty && !window.confirm('有未保存输入，确认放弃并返回阅读页？')) {
      return;
    }
    dispose();
    onExit();
  }
  actions.forEach(action => {
    action.preview.addEventListener('click', preview);
    action.reload.addEventListener('click', reload);
    action.exit.addEventListener('click', exit);
  });
  function pageShow(e) {
    if (!e.persisted || disposed) return;
    if (controller.dirty) {
      controller.invalidate();
      status.textContent = '浏览器恢复了旧会话。输入已保留，请核对并重新读取当前版本后再保存。';
      sync();
    } else load();
  }
  window.addEventListener('pageshow', pageShow);
  const ready = load();
  return {
    ready,
    dispose,
    get dirty() {
      return controller.dirty;
    },
    get busy() {
      return controller.busy;
    }
  };
});
