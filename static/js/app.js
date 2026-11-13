// تبديل الوضع الداكن/الفاتح
function toggleTheme(){
  var h = document.documentElement;
  var next = h.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  h.setAttribute('data-theme', next);
  try { localStorage.setItem('veyra-theme', next); } catch(e){}
}
// سحب الكروت لترتيبها (الترتيب مؤقت في الصفحة)
(function(){
  let dragEl = null;
  document.querySelectorAll('.tile[draggable="true"]').forEach(t => {
    t.addEventListener('dragstart', e => { dragEl = t; t.classList.add('dragging'); e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain','x'); });
    t.addEventListener('dragend', () => { t.classList.remove('dragging'); document.querySelectorAll('.tile.over').forEach(x => x.classList.remove('over')); });
    t.addEventListener('dragover', e => { e.preventDefault(); t.classList.add('over'); });
    t.addEventListener('dragleave', () => t.classList.remove('over'));
    t.addEventListener('drop', e => { e.preventDefault(); t.classList.remove('over'); if (dragEl && dragEl !== t) t.parentNode.insertBefore(dragEl, t); });
  });
})();
