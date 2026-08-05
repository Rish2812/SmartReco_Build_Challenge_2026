// --- Explore mega-menu (click to open, click outside to close) ---
document.addEventListener('DOMContentLoaded', () => {
  const dropdown = document.getElementById('exploreDropdown');
  const trigger = document.getElementById('exploreTrigger');
  if (!dropdown || !trigger) return;

  trigger.addEventListener('click', (e) => {
    e.stopPropagation();
    dropdown.classList.toggle('open');
  });
  document.addEventListener('click', (e) => {
    if (!dropdown.contains(e.target)) dropdown.classList.remove('open');
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') dropdown.classList.remove('open');
  });
});

// --- Course card hover-preview popover ---
// Uses event delegation (mouseover/mouseout bubble, unlike mouseenter/mouseleave) so it
// works for cards rendered dynamically after fetch (e.g. the dashboard recommendation
// panel), not just ones present at page load.
(() => {
  let popoverEl = null;
  let showTimer = null;
  let hideTimer = null;
  let activeCard = null;

  function getPopover() {
    if (!popoverEl) {
      popoverEl = document.createElement('div');
      popoverEl.className = 'course-popover';
      document.body.appendChild(popoverEl);
      popoverEl.addEventListener('mouseenter', () => clearTimeout(hideTimer));
      popoverEl.addEventListener('mouseleave', scheduleHide);
    }
    return popoverEl;
  }

  function renderContent(card) {
    const d = card.dataset;
    const stars = '★★★★★';
    const priceHtml = Number(d.price) === 0
      ? '<span class="price" style="color:var(--moss);">Free</span>'
      : `<span class="price">$${d.price}</span>`;
    return `
      <span class="tag">${d.category}</span>
      <h4>${d.title}</h4>
      <div class="badges"><span class="badge">${d.level}</span></div>
      <p class="desc">${d.desc.length > 160 ? d.desc.slice(0, 160) + '…' : d.desc}</p>
      <div class="meta-row"><span class="stars">${stars}</span><strong>${d.rating}</strong><span style="color:var(--muted);">(${d.reviews} reviews)</span></div>
      <div class="price-row">${priceHtml}<a class="view-btn" href="/product/${d.id}">View course</a></div>
    `;
  }

  function positionPopover(card, pop) {
    const rect = card.getBoundingClientRect();
    const popWidth = 320;
    const margin = 12;
    let left = rect.right + margin;
    if (left + popWidth > window.innerWidth - 8) {
      left = rect.left - popWidth - margin; // flip to the left if no room on the right
    }
    if (left < 8) left = Math.min(rect.left, window.innerWidth - popWidth - 8);
    let top = rect.top;
    const estHeight = 260;
    if (top + estHeight > window.innerHeight - 8) {
      top = Math.max(8, window.innerHeight - estHeight - 8);
    }
    pop.style.left = `${left}px`;
    pop.style.top = `${top}px`;
  }

  function scheduleHide() {
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => {
      const pop = getPopover();
      pop.classList.remove('visible');
      activeCard = null;
    }, 150);
  }

  document.addEventListener('mouseover', (e) => {
    const card = e.target.closest('[data-preview]');
    if (!card || card === activeCard) return;
    clearTimeout(hideTimer);
    clearTimeout(showTimer);
    showTimer = setTimeout(() => {
      activeCard = card;
      const pop = getPopover();
      pop.innerHTML = renderContent(card);
      positionPopover(card, pop);
      pop.classList.add('visible');
    }, 350); // small delay so the popover doesn't flicker on fast mouse movement
  });

  document.addEventListener('mouseout', (e) => {
    const card = e.target.closest('[data-preview]');
    if (!card) return;
    const toEl = e.relatedTarget;
    if (toEl && (card.contains(toEl) || (popoverEl && popoverEl.contains(toEl)))) return;
    clearTimeout(showTimer);
    scheduleHide();
  });

  window.addEventListener('scroll', () => {
    if (activeCard && popoverEl) positionPopover(activeCard, popoverEl);
  }, true);
})();
