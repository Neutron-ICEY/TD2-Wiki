(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else (root.TD2EditorLab = root.TD2EditorLab || {}).parser = factory();
}(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  const MAIN = "品牌套装信息", FORMAL_MAIN = MAIN;
  const MAIN_TEMPLATES = [MAIN, "装备组信息", "奇特装备信息", "武器信息"];
  function fail(code, offset) { const e = new Error(code + " at " + offset); e.code = code; e.offset = offset; throw e; }
  function parse(raw, options={}) {
    if (typeof raw !== "string" || raw.length > 524288) fail("INPUT_LIMIT", 0);
    function protectedEnd(i) {
      if (raw.startsWith("<!--", i)) {
        const end = raw.indexOf("-->", i + 4);
        if (end < 0) fail("UNCLOSED_COMMENT", i);
        return end + 3;
      }
      if (raw.startsWith("<nowiki>", i)) {
        const end = raw.indexOf("</nowiki>", i + 8);
        if (end < 0) fail("UNCLOSED_NOWIKI", i);
        return end + 9;
      }
      if (raw.startsWith("<nowiki/>", i)) return i + 9;
      return null;
    }
    function template(start, depth) {
      if (depth > 12) fail("NESTING_LIMIT", start);
      if (raw.startsWith("{{{", start)) fail("UNSUPPORTED_TEMPLATE_ARGUMENT", start);
      let i = start + 2, segmentStart = i, nested = [], equal = null;
      const segments = [];
      function finish(end) { segments.push({start: segmentStart, end, equal, nested}); nested = []; equal = null; }
      while (i < raw.length) {
        const protectedTo = protectedEnd(i);
        if (protectedTo !== null) { i = protectedTo; continue; }
        if (raw.startsWith("{{", i)) { const child = template(i, depth + 1); nested.push(child); i = child.end; continue; }
        if (raw.startsWith("}}", i)) {
          if (raw.startsWith("}}}", i)) {
            let end=i;while(raw[end]==="}")end++;
            if(!options.textEnvelope || (end-i)%2!==0)fail("AMBIGUOUS_BRACE_RUN", i);
          }
          finish(i);
          const first = segments.shift();
          if (first.nested.length) fail("DYNAMIC_TEMPLATE_NAME", first.start);
          const name = raw.slice(first.start, first.end).trim();
          return {name, nameStart:first.start, nameEnd:first.end, start, end: i + 2, segments};
        }
        if(options.textEnvelope && raw.startsWith("[[",i)){
          const end=raw.indexOf("]]",i+2);
          if(end<0 || /[\[\]{}<>]/.test(raw.slice(i+2,end)))fail("UNSUPPORTED_LINK_STRUCTURE",i);
          i=end+2;continue;
        }
        // Unsupported links/tags cannot be safely confused with a top-level pipe.
        if (raw[i] === "[" || raw[i] === "]" || raw[i] === "<" || raw[i] === ">") fail("UNSUPPORTED_MANAGED_SYNTAX", i);
        if (raw[i] === "|") { finish(i); segmentStart = i + 1; equal = null; i++; continue; }
        if (raw[i] === "=" && equal === null) equal = i;
        i++;
      }
      fail("UNCLOSED_TEMPLATE", start);
    }
    const candidates = [];
    let i = 0;
    while (i < raw.length) {
      const protectedTo = protectedEnd(i);
      if (protectedTo !== null) { i = protectedTo; continue; }
      if (raw.startsWith("[[", i)) {
        const end = raw.indexOf("]]", i + 2);
        if (end < 0 || raw.slice(i + 2, end).includes("[[")) fail("UNSUPPORTED_OUTSIDE_LINK", i);
        if (raw.slice(i + 2, end).includes("{{")) fail("UNSUPPORTED_OUTSIDE_LINK", i);
        i = end + 2; continue;
      }
      if (raw[i] === "<" || raw[i] === ">") fail("UNSUPPORTED_OUTSIDE_TAG", i);
      if (raw.startsWith("}}", i)) fail("UNEXPECTED_TEMPLATE_CLOSE", i);
      if (raw.startsWith("{{", i)) {
        const node = template(i, 0);
        if (MAIN_TEMPLATES.includes(node.name)) candidates.push(node);
        i = node.end; continue;
      }
      i++;
    }
    if (candidates.length !== 1) fail("MAIN_TEMPLATE_COUNT", 0);
    const main = candidates[0];
    return {raw, main, prefix: raw.slice(0, main.start), suffix: raw.slice(main.end)};
  }
  return {parse, MAIN, FORMAL_MAIN, MAIN_TEMPLATES};
}));
