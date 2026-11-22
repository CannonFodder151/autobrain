import { renderNav } from '../components/nav.js';

document.addEventListener('DOMContentLoaded', () => {
  const nav = document.getElementById('nav-placeholder');
  if (nav) nav.innerHTML = renderNav();

  const links = document.querySelectorAll<HTMLAnchorElement>('.app-nav a');
  links.forEach((a) => {
    a.addEventListener('click', () => {
      links.forEach((l) => l.classList.remove('active'));
      a.classList.add('active');
    });
  });

  const dateInput = document.querySelector('input[type="date"]') as HTMLInputElement | null;
  if (dateInput) {
    const today = new Date().toISOString().split('T')[0];
    dateInput.min = today;
  }
});