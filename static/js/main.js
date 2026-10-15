document.addEventListener('DOMContentLoaded', () => {
  const sidebar = document.getElementById('sidebar');
  const toggle = document.getElementById('mobileToggle');
  if (toggle && sidebar) toggle.addEventListener('click', () => sidebar.classList.toggle('open'));
  const pass = document.getElementById('password');
  const show = document.getElementById('togglePassword');
  if (pass && show) show.addEventListener('click', () => {
    const visible = pass.type === 'text'; pass.type = visible ? 'password' : 'text';
    show.innerHTML = visible ? '<i class="fa-regular fa-eye"></i>' : '<i class="fa-regular fa-eye-slash"></i>';
    show.setAttribute('aria-label', visible ? 'Show password' : 'Hide password');
  });
  document.querySelectorAll('.expiry-days[data-date]').forEach(el => {
    const days = Math.ceil((new Date(el.dataset.date+'T00:00:00') - new Date(new Date().toDateString())) / 86400000);
    el.textContent = days < 0 ? `${Math.abs(days)} days ago` : `${days} days`;
    const status = el.closest('tr')?.querySelector('.expiry-status');
    if (status) {
      status.textContent = days < 0 ? 'Expired' : days <= 30 ? 'Expiring soon' : days <= 90 ? 'Upcoming' : 'In date';
      status.classList.add(days < 0 ? 'critical' : days <= 30 ? 'low' : 'good');
    }
  });
  document.querySelectorAll('.flash').forEach(el => setTimeout(() => { if (el.isConnected) el.classList.add('flash-fade'); }, 6500));
});
