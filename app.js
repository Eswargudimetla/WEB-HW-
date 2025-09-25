(async function loadReviews() {
  const container = document.getElementById('reviews-container');
  if (!container) return;

  try {
    const res = await fetch('./data.json', { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const reviews = await res.json();

    reviews.slice(0, 50).forEach(rv => {
      const card = document.createElement('article');
      card.className = 'card review';
      card.innerHTML = `
        <div class="review-head">
          <div>
            <div class="bizname">${escapeHTML(rv.businessName ?? 'Business')}</div>
            <div class="date">${escapeHTML(rv.date ?? '')}</div>
          </div>
          <div class="rating" aria-label="rating">
            ${'★'.repeat(Math.round(rv.rating ?? 0))}${'☆'.repeat(5 - Math.round(rv.rating ?? 0))}
          </div>
        </div>
        <p class="review-text">${escapeHTML(rv.text ?? '')}</p>
        <div class="tags">
          ${rv.category ? `<span class="tag">${escapeHTML(rv.category)}</span>` : ''}
          ${rv.price ? `<span class="tag">${escapeHTML(rv.price)}</span>` : ''}
          ${rv.location ? `<span class="tag">${escapeHTML(rv.location)}</span>` : ''}
        </div>
      `;
      container.appendChild(card);
    });
  } catch (err) {
    console.error('Failed to load reviews:', err);
    const fallback = document.createElement('p');
    fallback.className = 'note';
    fallback.textContent = 'Could not load reviews.json. Serve over HTTP (not file://) and check your path.';
    container.appendChild(fallback);
  }

  function escapeHTML(str){
    return String(str).replace(/[&<>"']/g, s => ({
      '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
    }[s]));
  }
})();
