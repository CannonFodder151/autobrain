import { renderNav } from './components/nav.js';

document.addEventListener('DOMContentLoaded', () => {
  const nav = document.getElementById('nav-placeholder');
  if (nav) nav.innerHTML = renderNav();

  const form = document.getElementById('booking-form') as HTMLFormElement | null;
  if (form) {
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const fd = new FormData(form);
      const service = fd.get('service') as string;
      const date = fd.get('date') as string;
      const time = fd.get('time') as string;
      alert(`Availability check requested for ${service} on ${date} at ${time}.\n\n(This frontend simulates availability; connect to the AutoBrain Shop booking API to confirm.)`);
      form.reset();
    });
  }

  const dateInput = document.querySelector('input[type="date"]') as HTMLInputElement | null;
  if (dateInput) {
    const today = new Date().toISOString().split('T')[0];
    dateInput.min = today;
  }
});