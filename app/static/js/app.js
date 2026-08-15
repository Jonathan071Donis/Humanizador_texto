function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// Mark the current page in the nav (base.html doesn't know the route server-side).
(() => {
  const here = window.location.pathname;
  document.querySelectorAll('.wm-nav .nav-link').forEach((link) => {
    const href = link.getAttribute('href');
    if (href && (href === here || (href !== '/' && here.startsWith(href)))) {
      link.classList.add('active');
    }
  });
})();
