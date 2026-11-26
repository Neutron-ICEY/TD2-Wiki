(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory(require('./parser.js'));else root.TD2EditorLab.textBoundary = factory(root.TD2EditorLab.parser);
})(typeof globalThis !== 'undefined' ? globalThis : this, function (parser) {
  function valid(text, mode) {
    if (typeof text === 'string') text = text.replace(/\r\n/g, '\n');
    if (typeof text !== 'string' || text.trim() !== text || /[\x00-\x09\x0b-\x1f\x7f]/.test(text)) return false;
    if (mode === 'plain') return !/[\n{}|<>\[\]]/.test(text);
    if (/[<>]/.test(text)) return false;
    try {
      const doc = parser.parse('{{' + parser.MAIN + '\n|value=' + text + '\n}}', {
        textEnvelope: true
      });
      if (doc.main.segments.length !== 1) return false;
      function allowed(node) {
        return !node.name.startsWith('#') && !node.name.includes(':') && node.segments.every(s => s.nested.every(allowed));
      }
      return doc.main.segments[0].nested.every(allowed);
    } catch (e) {
      return false;
    }
  }
  return {
    valid
  };
});
