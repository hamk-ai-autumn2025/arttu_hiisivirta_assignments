// Mobile nav toggle
const toggle = document.querySelector('.nav-toggle');
const nav = document.querySelector('.site-nav');
if (toggle && nav) {
  toggle.addEventListener('click', () => {
    const isOpen = nav.classList.toggle('open');
    toggle.setAttribute('aria-expanded', String(isOpen));
  });
  // Close menu on link click (mobile)
  nav.addEventListener('click', (e) => {
    if (e.target.matches('.nav-link')) {
      nav.classList.remove('open');
      toggle.setAttribute('aria-expanded', 'false');
    }
  });
}

// Scroll spy for active nav link
const links = document.querySelectorAll('.nav-link');
const sections = [...links].map(link => document.querySelector(link.getAttribute('href'))).filter(Boolean);

const observer = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    const id = entry.target.getAttribute('id');
    const link = document.querySelector(`.nav-link[href="#${id}"]`);
    if (entry.isIntersecting) {
      links.forEach(l => l.classList.remove('active'));
      link?.classList.add('active');
    }
  });
}, { rootMargin: '-60% 0px -35% 0px', threshold: 0.01 });

sections.forEach(sec => observer.observe(sec));

// Header micro-shrink on scroll
const header = document.querySelector('.site-header');
let lastY = 0;
window.addEventListener('scroll', () => {
  const y = window.scrollY || window.pageYOffset;
  if (!header) return;
  if (y > 8 && y > lastY) header.style.boxShadow = '0 6px 20px rgba(0,0,0,.25)';
  else if (y < 8) header.style.boxShadow = 'none';
  lastY = y;
});

// Back to top
const backToTop = document.querySelector('.back-to-top');
if (backToTop) {
  backToTop.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));
}

// Current year in footer
const yearSpan = document.getElementById('year');
if (yearSpan) yearSpan.textContent = new Date().getFullYear();

// Optional: fake form submission (prevent page reload for now)
const form = document.querySelector('.contact-form');
if (form) {
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    alert('Thanks! We will get back to you shortly.');
    form.reset();
  });
}
