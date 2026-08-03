/**
 * Lightweight behavioral tracker.
 * - Events are queued in memory, never sent one-by-one.
 * - Flushes on a timer (every FLUSH_INTERVAL_MS) or when the queue hits FLUSH_SIZE,
 *   whichever comes first — this batches network calls instead of firing per-click.
 * - High-frequency events (time_spent pings) are throttled client-side before they
 *   even reach the queue.
 * - Flush uses fetch with `keepalive: true` so it survives page navigation without
 *   blocking the UI thread (a non-blocking equivalent of sendBeacon that still lets
 *   us set the Authorization header).
 */
const Tracker = (() => {
  const FLUSH_INTERVAL_MS = 8000;
  const FLUSH_SIZE = 10;
  const TIME_SPENT_THROTTLE_MS = 5000;

  let queue = [];
  let lastTimeSpentPing = 0;
  let pageEnterTs = Date.now();
  let currentProductId = window.__smartreco_product_id || null;

  function enqueue(event) {
    if (!Auth.getToken()) return; // tracking requires a logged-in user in this build
    queue.push(event);
    if (queue.length >= FLUSH_SIZE) flush();
  }

  function flush() {
    if (queue.length === 0) return;
    const batch = queue;
    queue = [];
    const token = Auth.getToken();

    fetch('/events/batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({ events: batch }),
      keepalive: true, // allows the request to complete even during page unload
    }).catch(() => {
      // Non-critical: drop silently rather than retry-loop and risk blocking the UI.
    });
  }

  function trackView(productId) {
    enqueue({ event_type: 'view', product_id: productId });
  }

  function trackSearch(query) {
    if (!query || !query.trim()) return;
    enqueue({ event_type: 'search', query: query.trim() });
  }

  function trackClick(productId) {
    enqueue({ event_type: 'click', product_id: productId });
  }

  function trackTimeSpent(productId, durationMs) {
    const now = Date.now();
    if (now - lastTimeSpentPing < TIME_SPENT_THROTTLE_MS) return; // throttle
    lastTimeSpentPing = now;
    enqueue({ event_type: 'time_spent', product_id: productId, metadata: { duration_ms: durationMs } });
  }

  // Auto time-spent tracking for product detail pages.
  if (currentProductId) {
    trackView(currentProductId);
    window.addEventListener('beforeunload', () => {
      trackTimeSpent(currentProductId, Date.now() - pageEnterTs);
      flush();
    });
  }

  setInterval(flush, FLUSH_INTERVAL_MS);
  window.addEventListener('beforeunload', flush);

  return { trackView, trackSearch, trackClick, trackTimeSpent, flush };
})();
