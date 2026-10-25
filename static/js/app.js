// تبديل الوضع الداكن/الفاتح مع تحديث وصف الزر لقارئات الشاشة.
function syncThemeButton() {
  var button = document.getElementById('theme-btn');
  if (!button) return;
  var dark = document.documentElement.getAttribute('data-theme') === 'dark';
  var label = dark ? 'Switch to light mode' : 'Switch to dark mode';
  button.textContent = dark ? '☀' : '☾';
  button.setAttribute('aria-label', label);
  button.setAttribute('title', label);
}
function toggleTheme(){
  var h = document.documentElement;
  var next = h.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  h.setAttribute('data-theme', next);
  try { localStorage.setItem('veyra-theme', next); } catch(e){}
  syncThemeButton();
}
document.addEventListener('DOMContentLoaded', syncThemeButton);
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
