"use strict";
const fold=require('./title-casefold.json'),assert=require('node:assert/strict');
function normalized(name){return [...name.normalize('NFC').replace(/_/g,' ').replace(/[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+/g,' ').replace(/^ +| +$/g,'')].map(c=>fold[c]??c.toLowerCase()).join('');}
function safeRelative(source){assert(typeof source==='string'&&source&&!/[\\:]/.test(source),'Invalid relative path');for(const p of source.split('/'))assert(p&&p!=='.'&&p!=='..'&&!/[\x00-\x1f<>:"|?*]/.test(p)&&!/[ .]$/.test(p)&&!/^(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\..*)?$/i.test(p),'Invalid portable path');return source;}
module.exports={normalized,safeRelative};
