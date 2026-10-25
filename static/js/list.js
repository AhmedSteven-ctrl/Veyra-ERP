// تحديد الصفوف والتصدير CSV (مربوط بـ list.html)
function selectedRows(){ return Array.from(document.querySelectorAll('.row-check:checked')); }
  function updateBulk(){
    const n = selectedRows().length;
    document.getElementById('bulk').classList.toggle('hidden', n === 0);
    document.getElementById('bulk-count').textContent = n;
    const all = document.querySelectorAll('.row-check');
    document.getElementById('select-all').checked = all.length > 0 && n === all.length;
  }
  function toggleAll(box){ document.querySelectorAll('.row-check').forEach(c => c.checked = box.checked); updateBulk(); }
  function clearSelection(){ document.querySelectorAll('.row-check').forEach(c => c.checked = false); document.getElementById('select-all').checked = false; updateBulk(); }
  function exportSelected(){
    const table = document.getElementById('list');
    const headers = Array.from(table.querySelectorAll('thead th')).slice(1, -2).map(th => th.innerText.trim());
    const lines = [headers.join(',')];
    selectedRows().forEach(c => {
      const tr = c.closest('tr');
      const cells = Array.from(tr.querySelectorAll('td')).slice(1, -2).map(td => '"' + td.innerText.trim().replace(/"/g, '""') + '"');
      lines.push(cells.join(','));
    });
    const blob = new Blob(['\uFEFF' + lines.join('\n')], {type: 'text/csv;charset=utf-8'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = (document.getElementById('list').dataset.code || 'export') + '-export.csv';
    a.click();
  }
