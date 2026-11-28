export function renderNav() {
  return `
    <header class="site-header">
      <nav class="nav-bar container">
        <a href="index.html" class="brand">
          <div class="brand-mark">AB</div>
          AutoBrain Shop
        </a>
        <ul class="nav-links">
          <li><a href="index.html">Home</a></li>
          <li><a href="index.html#services">Services</a></li>
          <li><a href="index.html#booking">Book Appointment</a></li>
          <li><a href="customer/index.html">Customer Portal</a></li>
          <li><a href="workshop/index.html">Workshop Dashboard</a></li>
        </ul>
        <div class="nav-actions">
          <a href="customer/index.html" class="btn btn-primary">Sign In</a>
        </div>
        <button class="mobile-menu-toggle" aria-label="Toggle menu">
          <span></span><span></span><span></span>
        </button>
      </nav>
    </header>
  `;
}