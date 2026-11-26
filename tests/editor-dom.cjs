'use strict';
function create(){
  const document={activeElement:null},all=node=>[node,...(node.children||[]).flatMap(all)];
  class Element{
    constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.attributes={};this.dataset={};this.events={};this.hidden=false;this.value='';this.style={};}
    append(...nodes){for(const n of nodes){n.parentElement=this;this.children.push(n);}}
    prepend(...nodes){for(const n of nodes)n.parentElement=this;this.children.unshift(...nodes);}
    insertBefore(node,before){node.parentElement=this;this.children.splice(this.children.indexOf(before),0,node);}
    replaceChildren(...nodes){this.children=[];this.append(...nodes);}
    replaceWith(node){node.parentElement=this.parentElement;this.parentElement.children.splice(this.parentElement.children.indexOf(this),1,node);}
    remove(){this.parentElement.children=this.parentElement.children.filter(n=>n!==this);}
    setAttribute(k,v){this.attributes[k]=String(v);}
    getAttribute(k){return this.attributes[k]??null;}
    removeAttribute(k){delete this.attributes[k];}
    addEventListener(k,fn){(this.events[k]??=[]).push(fn);}
    removeEventListener(k,fn){this.events[k]=(this.events[k]||[]).filter(f=>f!==fn);}
    async emit(type){const event={type,target:this,preventDefault(){}};for(let e=this;e;e=e.parentElement)for(const fn of e.events[type]||[])await fn(event);}
    contains(node){return all(this).includes(node);}
    querySelectorAll(selector){return all(this).slice(1).filter(n=>selector.split(',').some(s=>s.startsWith('.')?(n.className||'').split(' ').includes(s.slice(1)):s==='button:not(:disabled)'?n.tagName==='BUTTON'&&!n.disabled:n.tagName===s.toUpperCase()));}
    querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
    closest(selector){for(let n=this;n;n=n.parentElement)if(selector==='[hidden]'&&n.hidden)return n;return null;}
    focus(){document.activeElement=this;}
    get classList(){return {add:(...names)=>{this.className=[this.className||'',...names].join(' ');},contains:name=>(this.className||'').split(' ').includes(name)};}
  }
  const container=new Element('div');
  document.createElement=tag=>new Element(tag);document.createTextNode=text=>({textContent:text});
  document.head=new Element('head');document.getElementById=()=>container;document.querySelector=()=>null;document.querySelectorAll=()=>[];
  return {document,container,all};
}
module.exports={create};
