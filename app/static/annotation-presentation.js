'use strict';
// Relationship describes the source, independently of projection precision.
((root) => {
  function relation(source, context) {
    if (!source) return 'unavailable';
    if (source.revision_id !== context.revision) return 'old_revision';
    if (source.created_view === 'pdf' || context.view === 'pdf') {
      if (source.created_view !== 'pdf' || context.view !== 'pdf') return 'cross';
      return source.pdf_sha256 === context.pdfHash ? 'direct' : 'unavailable';
    }
    return source.segments.every(s => source.kind === 'object'
      ? context.units.has(s.unit_id) : context.representations.has(s.representation_id)) ? 'direct' : 'cross';
  }
  function sourceName(source) {
    if (!source) return '不可访问的来源';
    if (source.created_view === 'pdf') return '原版 PDF';
    return {zh:'中文版本', en:'英文版本', shared:'图表／段落'}[source.source_language] || '原文';
  }
  const precision = {exact:'精确选区', aligned_exact:'已确认对应词语', block:'对应段落，未精确到词语',
    object:'整个对象', page:'仅定位到页', unmapped:'当前视图未定位', stale:'旧修订，定位待确认'};
  function objectLabel(segment, index, total) {
    const prefix = total > 1 ? `对象 ${index + 1} · ` : '';
    if (segment.page_index !== undefined) {
      const number = segment.page_index + 1;
      const printed = segment.page_label && segment.page_label !== String(number) ? `（文内标签 ${segment.page_label}）` : '';
      return prefix + `PDF 文件第 ${number} 页${printed}：` + (segment.raw_quote || segment.quote || '整页');
    }
    return prefix + (segment.raw_quote || segment.quote || segment.label || '整个段落／对象');
  }
  function localTime(note) {
    const date = new Date(note.created_at_iso || '');
    if (Number.isNaN(date.getTime())) return note.created_at || '时间未提供';
    const pad = n => String(n).padStart(2,'0');
    return `${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
  }
  root.GAAnnotationPresentation = {relation, sourceName, precision, objectLabel, localTime};
})(window);
