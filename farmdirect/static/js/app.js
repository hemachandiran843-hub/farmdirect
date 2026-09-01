/* FarmDirect — frontend interactions (vanilla JS, no build step) */

// Works both standalone ("/") and behind a URL prefix (sandbox preview)
const S = window.SCRIPT_ROOT || '';

// ---------- Toast helper ----------
function fdToast(msg, isError) {
  let wrap = document.querySelector('.fd-toast-wrap');
  if (!wrap) {
    wrap = document.createElement('div');
    wrap.className = 'fd-toast-wrap';
    document.body.appendChild(wrap);
  }
  const t = document.createElement('div');
  t.className = 'fd-toast' + (isError ? ' err' : '');
  t.innerHTML = `<i class="bi ${isError ? 'bi-exclamation-circle' : 'bi-check-circle'} me-2"></i>${msg}`;
  wrap.appendChild(t);
  setTimeout(() => { t.style.opacity = '0'; t.style.transition = 'opacity .4s'; }, 2600);
  setTimeout(() => t.remove(), 3100);
}

// ---------- Cart API ----------
async function api(url, data) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data || {}),
  });
  if (res.status === 401 || res.redirected) {
    fdToast('Please log in first', true);
    setTimeout(() => window.location.href = (window.AUTH_URL || S + '/login') + '?next=' + encodeURIComponent(location.pathname), 700);
    throw new Error('unauthorized');
  }
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json.error || 'Request failed');
  return json;
}

async function addToCart(productId, qty) {
  try {
    const r = await api(S + '/api/cart/add', { product_id: productId, quantity_kg: qty || 1 });
    fdToast(r.message || 'Added to cart');
    updateCartBadge(r.cart_items);
  } catch (e) { if (e.message !== 'unauthorized') fdToast(e.message, true); }
}

function updateCartBadge(n) {
  document.querySelectorAll('.fd-cart-count').forEach(el => {
    el.textContent = n;
    el.style.display = n > 0 ? 'inline-flex' : 'none';
  });
}

async function cartUpdateQty(cartId, input) {
  const qty = parseFloat(input.value) || 0.5;
  if (qty < 0.5) { input.value = 0.5; return; }
  try {
    await api(S + '/api/cart/update', { cart_id: cartId, quantity_kg: qty });
    setTimeout(() => location.reload(), 250);
  } catch (e) { fdToast(e.message, true); }
}

async function cartRemove(cartId) {
  try {
    await api(S + '/api/cart/remove', { cart_id: cartId });
    const row = document.getElementById('cart-row-' + cartId);
    if (row) row.remove();
    setTimeout(() => location.reload(), 250);
  } catch (e) { fdToast(e.message, true); }
}

// ---------- Farmer order actions ----------
async function itemStatus(orderId, itemId, action) {
  try {
    await api(`${S}/api/orders/${orderId}/item/${iidToPath(itemId)}/status`, { action });
    fdToast(action === 'accept' ? 'Order accepted ✅' : 'Order rejected');
    setTimeout(() => location.reload(), 600);
  } catch (e) { fdToast(e.message, true); }
}
// helper kept trivial for clarity
const iidToPath = (id) => id;

// ---------- Logistics pipeline ----------
async function deliveryAdvance(deliveryId, nextStatus) {
  try {
    await api(`${S}/api/deliveries/${deliveryId}/status`, { status: nextStatus });
    fdToast('Status updated → ' + nextStatus.replace('_', ' '));
    setTimeout(() => location.reload(), 600);
  } catch (e) { fdToast(e.message, true); }
}

// ---------- Bulk quotes ----------
async function requestQuote() {
  const crop = document.getElementById('q-crop').value;
  const qty = document.getElementById('q-qty').value;
  const grade = document.getElementById('q-grade').value;
  const city = document.getElementById('q-city').value;
  try {
    await api(S + '/api/quotes', { crop, quantity_kg: qty, grade, city });
    fdToast('Quotation requested — comparing suppliers…');
    setTimeout(() => location.reload(), 900);
  } catch (e) { fdToast(e.message, true); }
}

async function acceptQuote(qid, rid) {
  try {
    const r = await api(`${S}/api/quotes/${qid}/accept/${rid}`, {});
    fdToast('Supplier accepted — bulk order placed! 🎉');
    setTimeout(() => window.location.href = S + '/track/' + r.order_id, 900);
  } catch (e) { fdToast(e.message, true); }
}

// ---------- Marketplace filters (client-side quick filter) ----------
function quickFilter(input) {
  const q = input.value.toLowerCase();
  document.querySelectorAll('[data-product-card]').forEach(card => {
    const text = card.textContent.toLowerCase();
    card.style.display = text.includes(q) ? '' : 'none';
  });
}

// ---------- Price calculator (listing form) ----------
async function refreshSuggestedPrice() {
  const crop = document.getElementById('f-crop')?.value;
  const grade = document.getElementById('f-grade')?.value;
  const qty = document.getElementById('f-qty')?.value;
  if (!crop) return;
  try {
    const r = await fetch(`${S}/api/ai/price?crop=${encodeURIComponent(crop)}&grade=${grade}&qty=${qty}`);
    const rec = await r.json();
    const el = document.getElementById('suggested-price');
    if (el && rec.suggested_price) {
      el.textContent = '₹' + rec.suggested_price.toFixed(1) + ' /kg';
      const gain = document.getElementById('price-gain-note');
      if (gain) gain.textContent = `${rec.earnings_gain_pct > 0 ? '+' : ''}${rec.earnings_gain_pct}% vs mandi · consumer pays ≈ ₹${rec.consumer_price}/kg`;
    }
  } catch (e) { /* silent */ }
}

// ---------- Chart.js defaults ----------
document.addEventListener('DOMContentLoaded', () => {
  if (window.Chart) {
    Chart.defaults.font.family = "'Segoe UI', system-ui, sans-serif";
    Chart.defaults.color = '#5f6f66';
    Chart.defaults.plugins.legend.labels.boxWidth = 12;
    Chart.defaults.plugins.tooltip.backgroundColor = '#1c2b22';
    Chart.defaults.responsive = true;
    Chart.defaults.maintainAspectRatio = false;
  }
});
