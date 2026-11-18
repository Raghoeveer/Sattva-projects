/* Shared behaviour for every page: nav, enquiry modal, form submit, reveal. */
(function () {
  // ---- Mobile menu ----
  var toggle = document.querySelector('.menu-toggle');
  var links = document.getElementById('nav-links');
  if (toggle && links) {
    toggle.addEventListener('click', function () {
      var open = links.classList.toggle('open');
      toggle.classList.toggle('open', open);
      toggle.setAttribute('aria-expanded', String(open));
    });
    links.querySelectorAll('a').forEach(function (a) {
      a.addEventListener('click', function () {
        links.classList.remove('open');
        toggle.classList.remove('open');
        toggle.setAttribute('aria-expanded', 'false');
      });
    });
  }

  // ---- Header shadow on scroll ----
  var header = document.querySelector('.site-header');
  window.addEventListener('scroll', function () {
    header.classList.toggle('scrolled', window.scrollY > 40);
  }, { passive: true });

  // ---- Project pages: logo scrolls to the top without adding #top to the URL ----
  var brandTop = document.querySelector('.brand[href="#top"]');
  if (brandTop) {
    brandTop.addEventListener('click', function (e) {
      e.preventDefault();
      window.scrollTo(0, 0); // smooth via CSS scroll-behavior, instant under reduced motion
      if (location.hash) history.replaceState(null, '', location.pathname + location.search);
    });
  }

  // ---- Project pages: highlight the header group of the section in view ----
  var sectionLinks = document.querySelectorAll('.nav-links a[data-sections]');
  if (sectionLinks.length && 'IntersectionObserver' in window) {
    var linkFor = {};
    sectionLinks.forEach(function (a) {
      a.getAttribute('data-sections').split(' ').forEach(function (id) { linkFor[id] = a; });
    });
    var spy = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        sectionLinks.forEach(function (a) { a.removeAttribute('aria-current'); });
        var a = linkFor[e.target.id];
        if (a) a.setAttribute('aria-current', 'true');
      });
    }, { rootMargin: '-35% 0px -64% 0px' });
    document.querySelectorAll('main > section').forEach(function (s) { spy.observe(s); });
  }

  // ---- Enquiry modal ----
  var modal = document.getElementById('enquiry-modal');
  var lastFocus = null;
  function openModal() {
    lastFocus = document.activeElement;
    modal.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
    var first = modal.querySelector('input[name="name"]');
    if (first) first.focus();
  }
  function closeModal() {
    modal.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
    if (lastFocus) lastFocus.focus();
  }
  document.querySelectorAll('[data-open-enquiry]').forEach(function (b) { b.addEventListener('click', openModal); });
  document.querySelectorAll('[data-close-enquiry]').forEach(function (b) { b.addEventListener('click', closeModal); });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && modal.getAttribute('aria-hidden') === 'false') closeModal();
  });

  // ---- Forms: submit to Web3Forms via fetch, then go to /thank-you/ ----
  document.querySelectorAll('[data-enquiry-form]').forEach(function (form) {
    var pageField = form.querySelector('input[name="page"]');
    if (pageField) pageField.value = document.title + ' (' + location.pathname + ')';

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var btn = form.querySelector('button[type="submit"]');
      var label = btn.textContent;
      btn.textContent = 'Sending…';
      btn.disabled = true;

      fetch(form.action, { method: 'POST', body: new FormData(form), headers: { Accept: 'application/json' } })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (!data.success) throw new Error(data.message || 'Submission failed');
          if (typeof gtag === 'function') gtag('event', 'generate_lead', { form_page: location.pathname });
          location.href = '/thank-you/';
        })
        .catch(function () {
          alert('Sorry, that didn’t go through. Please try again, or call us directly.');
          btn.textContent = label;
          btn.disabled = false;
        });
    });
  });

  // ---- Track call / WhatsApp / email clicks (only if analytics is configured) ----
  document.addEventListener('click', function (e) {
    if (typeof gtag !== 'function') return;
    var a = e.target.closest('a[href^="tel:"], a[href^="mailto:"], a[href*="wa.me"]');
    if (!a) return;
    var href = a.getAttribute('href');
    var evt = href.indexOf('tel:') === 0 ? 'phone_click' : href.indexOf('mailto:') === 0 ? 'email_click' : 'whatsapp_click';
    gtag('event', evt, { link_url: href });
  }, true);

  // ---- Scroll reveal ----
  // Plain scroll-position check rather than IntersectionObserver, so nothing can
  // stay hidden in an environment where observer callbacks don't fire.
  if (!matchMedia('(prefers-reduced-motion: reduce)').matches) {
    var pending = [].slice.call(document.querySelectorAll('.card, .icon-card, .plan-card, .list-card, .gallery-item, .step, .review-card, .project-card'));
    pending.forEach(function (el, i) {
      el.classList.add('reveal');
      el.style.transitionDelay = (i % 4) * 60 + 'ms';
    });
    // Checked on scroll and on a light timer. Scroll events are tied to the
    // browser's rendering cycle; the timer isn't, so content can't get stuck hidden.
    var timer;
    var revealInView = function () {
      var limit = window.innerHeight * 0.95;
      pending = pending.filter(function (el) {
        if (el.getBoundingClientRect().top < limit) { el.classList.add('visible'); return false; }
        return true;
      });
      if (!pending.length) {
        clearInterval(timer);
        window.removeEventListener('scroll', revealInView);
      }
    };
    window.addEventListener('scroll', revealInView, { passive: true });
    timer = setInterval(revealInView, 250);
    revealInView();
  }
})();
