import { renderNav } from '../components/nav.js';

document.addEventListener('DOMContentLoaded', () => {
  const nav = document.getElementById('nav-placeholder');
  if (nav) nav.innerHTML = renderNav();

  const form = document.getElementById('customer-booking-form') as HTMLFormElement | null;
  if (form) {
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const fd = new FormData(form);
      const vehicle = fd.get('vehicle') as string;
      const service = fd.get('service') as string;
      const date = fd.get('date') as string;
      const time = fd.get('time') as string;
      const notes = fd.get('notes') as string;
      alert(`Appointment requested:\nVehicle: ${vehicle}\nService: ${service}\nDate: ${date} ${time}\nNotes: ${notes}\n\n(This frontend simulates booking; connect to the AutoBrain Shop booking API to confirm.)`);
      form.reset();
    });
  }

  const dateInput = document.querySelector('input[type="date"]') as HTMLInputElement | null;
  if (dateInput) {
    const today = new Date().toISOString().split('T')[0];
    dateInput.min = today;
  }

  const links = document.querySelectorAll<HTMLAnchorElement>('.app-nav a');
  links.forEach((a) => {
    a.addEventListener('click', () => {
      links.forEach((l) => l.classList.remove('active'));
      a.classList.add('active');
    });
  });
});