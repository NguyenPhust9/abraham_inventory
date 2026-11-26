const COLOR_MAP = [
  ['xám dương', ['#8fa3bd']],
  ['xanh dương', ['#2e6fde']],
  ['dương cam', ['#2e6fde', '#f5822a']],
  ['dương', ['#2e6fde']],
  ['xanh ngọc', ['#2fb6a6']],
  ['xám đậm', ['#5c6066']],
  ['xám nhạt', ['#c9cdd1']],
  ['trắng dè ngọc', ['#f4faf8', '#2fb6a6']],
  ['trắng bạc', ['#eef0ee']],
  ['trắng inox', ['#e9ecec']],
  ['trắng', ['#ffffff']],
  ['hồng đậm', ['#e85d9e']],
  ['hồng nhạt', ['#fbc4d8']],
  ['hồng', ['#f48fb1']],
  ['vàng cà phê', ['#c69749']],
  ['vàng', ['#f4c430']],
  ['cam', ['#f5822a']],
  ['đỏ', ['#d8342a']],
  ['đen đỏ', ['#1b1b1b', '#d8342a']],
  ['đen cam', ['#1b1b1b', '#f5822a']],
  ['đen dương', ['#1b1b1b', '#2e6fde']],
  ['đen', ['#1b1b1b']],
  ['xám', ['#9aa0a6']],
  ['bạc', ['#c7cbcf']],
  ['lá', ['#4c9a5b']],
  ['ngọc', ['#2fb6a6']],
  ['tím', ['#8a63c9']],
  ['inox', ['#c7cbcf']]
];

let PRODUCTS = [];
let catalogCategories = [];
let catalogPage = 0;
let catalogTotalAvailable = 0;
let catalogHasMore = false;
let catalogTotalGroups = 0;
let catalogController = null;
let catalogRequestId = 0;
let catalogSearchTimer = null;
let catalogBusy = false;
let catalogFailed = false;
let searchComposing = false;
let promotionSuggestions = [];
let promotionSuggestionsLoadedAt = 0;
let promotionSuggestionsLoading = false;
let warningController = null;
let catalogLastLoadedAt = 0;
let catalogCacheVersion = String(window.CATALOG_CACHE_VERSION || '0');
let REORDER_ITEMS = [];
let reorderQuery = '';
let reorderRefreshInFlight = false;
let reorderLastLoadedAt = 0;
const catalogMode = document.querySelector('.catalog-page')?.dataset.priceType || 'dealer';
const priceType = catalogMode === 'retail' ? 'retail' : 'dealer';
const isPromotionCatalog = catalogMode === 'promotion';
const priceLabel = isPromotionCatalog ? 'Giá khuyến mãi' : (priceType === 'retail' ? 'Giá lẻ' : 'Giá đại lý');
let activeCat = 'Tất cả';
let onlyInStock = false;
let showLotDetails = false;
let visibleInventory = [];
let sortStockOrder = '';
let minPrice = null;
let maxPrice = null;

const els = {
  search: document.getElementById('search'),
  pills: document.getElementById('catpills'),
  grid: document.getElementById('grid'),
  empty: document.getElementById('emptyState'),
  summaryText: document.getElementById('summaryText'),
  summaryStock: document.getElementById('summaryStock'),
  onlyStock: document.getElementById('onlyStock'),
  lotDetails: document.getElementById('lotDetails'),
  sortStock: document.getElementById('sortStock'),
  minPrice: document.getElementById('minPrice'),
  maxPrice: document.getElementById('maxPrice'),
  modal: document.getElementById('productModal'),
  modalTitle: document.getElementById('modalTitle'),
  modalSub: document.getElementById('modalSub'),
  modalBody: document.getElementById('modalBody'),
  modalClose: document.getElementById('modalClose'),
  zoomDialog: document.getElementById('imageZoomDialog'),
  zoomImage: document.getElementById('imageZoomImage'),
  zoomTitle: document.getElementById('imageZoomTitle'),
  zoomLevel: document.getElementById('imageZoomLevel'),
  zoomViewport: document.getElementById('imageZoomViewport'),
  zoomStage: document.getElementById('imageZoomStage'),
  zoomCopy: document.getElementById('imageZoomCopy'),
  zoomDownload: document.getElementById('imageZoomDownload'),
  zoomIn: document.getElementById('imageZoomIn'),
  zoomOut: document.getElementById('imageZoomOut'),
  zoomClose: document.getElementById('imageZoomClose'),
};

// Load one nearby row ahead; let this observer be the only lazy-loading gate.
function loadCatalogImage(img) {
  if (!img.dataset.catalogSrc) return;
  img.loading = 'eager';
  img.fetchPriority = 'auto';
  img.src = img.dataset.catalogSrc;
  img.removeAttribute('data-catalog-src');
}

const catalogImageObserver = 'IntersectionObserver' in window ? new IntersectionObserver(entries => {
  for (const entry of entries) {
    if (!entry.isIntersecting) continue;
    const img = entry.target;
    loadCatalogImage(img);
    catalogImageObserver.unobserve(img);
  }
}, {rootMargin: '480px 0px'}) : null;

function loadProductDetailImage(image, previewUrl, fullUrl) {
  const holder = image.parentElement;
  image.dataset.fullSrc = fullUrl;
  image.fetchPriority = 'high';
  image.src = previewUrl || fullUrl;
  if (!previewUrl || previewUrl === fullUrl) return;

  // Reuse the card's cached photo immediately, then swap in the decoded full image.
  // Do not replace a newer product or leave a blank image when the full request fails.
  const fullImage = new Image();
  fullImage.fetchPriority = 'high';
  fullImage.decoding = 'async';
  fullImage.onload = async () => {
    try { await fullImage.decode(); } catch { return; }
    if (!holder.isConnected || image.dataset.fullSrc !== fullUrl) return;
    image.src = fullUrl;
    // A failed thumbnail may have been replaced by the shared missing-photo handler.
    if (!image.isConnected) holder.replaceChildren(image);
  };
  fullImage.src = fullUrl;
}

let audioContext = null;
let imageZoom = 1;
let zoomDrag = null;
let zoomGroup = null;

function layoutImageZoom() {
  const image = els.zoomImage;
  const viewport = els.zoomViewport;
  const stage = els.zoomStage;
  if (!image.naturalWidth || !image.naturalHeight || !viewport.clientWidth || !viewport.clientHeight) return;

  // Keep the same point centered while the image or screen size changes.
  const oldWidth = stage.offsetWidth;
  const oldHeight = stage.offsetHeight;
  const centerX = oldWidth
    ? Math.max(0, Math.min(1, (viewport.scrollLeft + viewport.clientWidth / 2 - stage.offsetLeft) / oldWidth))
    : .5;
  const centerY = oldHeight
    ? Math.max(0, Math.min(1, (viewport.scrollTop + viewport.clientHeight / 2 - stage.offsetTop) / oldHeight))
    : .5;

  const fit = Math.min(viewport.clientWidth / image.naturalWidth, viewport.clientHeight / image.naturalHeight);
  stage.style.width = `${Math.round(image.naturalWidth * fit * imageZoom)}px`;
  stage.style.height = `${Math.round(image.naturalHeight * fit * imageZoom)}px`;

  requestAnimationFrame(() => {
    viewport.scrollTo(
      stage.offsetLeft + stage.offsetWidth * centerX - viewport.clientWidth / 2,
      stage.offsetTop + stage.offsetHeight * centerY - viewport.clientHeight / 2
    );
  });
}

function setImageZoom(value) {
  imageZoom = Math.max(1, Math.min(3, value));
  els.zoomLevel.textContent = `${Math.round(imageZoom * 100)}%`;
  els.zoomOut.disabled = imageZoom === 1;
  els.zoomIn.disabled = imageZoom === 3;
  els.zoomViewport.classList.toggle('can-pan', imageZoom > 1);
  layoutImageZoom();
}

function openImageZoom(imageUrl, title, group, previewUrl) {
  if (!imageUrl || !els.zoomDialog) return;
  zoomGroup = group;
  els.zoomStage.style.width = '0px';
  els.zoomStage.style.height = '0px';
  loadProductDetailImage(els.zoomImage, previewUrl, imageUrl);
  els.zoomImage.alt = title;
  els.zoomTitle.textContent = title;
  els.zoomDialog.showModal();
  setImageZoom(1);
  requestAnimationFrame(layoutImageZoom);
}

function unlockAudio() {
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) return;

  if (!audioContext) {
    audioContext = new AudioContextClass();
  }

  if (audioContext.state === 'suspended') {
    audioContext.resume();
  }
}

function playUISound(kind = 'click') {
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) return;

  unlockAudio();

  if (audioContext.state === 'suspended') {
    audioContext.resume();
  }

  const settings = {
    click: { frequency: 520, endFrequency: 700, duration: .07, volume: .065 },
    open: { frequency: 620, endFrequency: 920, duration: .16, volume: .085 },
    close: { frequency: 420, endFrequency: 260, duration: .12, volume: .07 },
    celebration: { frequency: 760, endFrequency: 1120, duration: .13, volume: .07 },
  }[kind] || { frequency: 520, endFrequency: 700, duration: .07, volume: .065 };

  const now = audioContext.currentTime;
  const oscillator = audioContext.createOscillator();
  const gain = audioContext.createGain();

  oscillator.type = 'sine';
  oscillator.frequency.setValueAtTime(settings.frequency, now);
  oscillator.frequency.exponentialRampToValueAtTime(settings.endFrequency, now + settings.duration);
  gain.gain.setValueAtTime(.0001, now);
  gain.gain.exponentialRampToValueAtTime(settings.volume, now + .01);
  gain.gain.exponentialRampToValueAtTime(.0001, now + settings.duration);

  oscillator.connect(gain);
  gain.connect(audioContext.destination);
  oscillator.start(now);
  oscillator.stop(now + settings.duration + .02);
}

// Dong bo trang thai loc voi checkbox tren giao dien ngay tu dau,
// tranh viec checkbox hien tick san (checked trong HTML) nhung
// bien onlyInStock van la false cho den khi nguoi dung bam doi.
if (els.onlyStock) {
  onlyInStock = els.onlyStock.checked;
}

function normalizeModelName(modelName) {
  if (!modelName) return '';

  return String(modelName)
    .replace(/\s*\([^)]*\)\s*$/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function normalizeText(value) {
  return String(value || '')
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim();
}

function escapeHTML(value) {
  return String(value || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function colorHex(name) {
  const n = normalizeText(name);

  for (const [key, hex] of COLOR_MAP) {
    if (n === key) return hex;
  }

  for (const [key, hex] of COLOR_MAP) {
    if (n.includes(key)) return hex;
  }

  return ['#b9b6a8'];
}

function swatchStyle(name) {
  const hex = colorHex(name);

  if (hex.length === 1) {
    return `background:${hex[0]};`;
  }

  return `background:linear-gradient(135deg, ${hex[0]} 50%, ${hex[1]} 50%);`;
}

function stockBadge(n) {
  const qty = Number(n || 0);

  if (qty <= 0) {
    return {
      cls: 'out',
      label: 'HẾT HÀNG'
    };
  }

  if (qty <= 5) {
    return {
      cls: 'low',
      label: `CÒN ${qty}`
    };
  }

  return {
    cls: 'good',
    label: `CÒN ${qty}`
  };
}

function fmtPrice(p) {
  if (p === null || p === undefined || p === '') {
    return 'Liên hệ';
  }

  const price = Number(p);

  if (Number.isNaN(price) || price <= 0) {
    return 'Liên hệ';
  }

  return price.toLocaleString('vi-VN') + ' đ';
}

function prepareProduct(p) {
  const originalModel = p.original_model || p.model || '';
  const cleanModel = normalizeModelName(p.model || originalModel);

  return {
    ...p,
    model: cleanModel,
    original_model: originalModel,
    category: p.category || '',
    color: p.color || '',
    code: p.code || '',
    stock: Number(p.stock || 0),
    reserved: Number(p.reserved || 0),
    available: Number(p.available || 0),
    price: p.price,
    image_url: p.image_url || null,
    image_thumb_url: p.image_thumb_url || p.image_url || null
  };
}

function groupByModel(items) {
  const map = new Map();

  for (const p of items) {
    const cleanModel = normalizeModelName(p.model || p.original_model);
    const category = p.category || '';
    const key = normalizeText(cleanModel) + '||' + normalizeText(category);

    if (!map.has(key)) {
      map.set(key, {
        model: cleanModel,
        category: category,
        variants: []
      });
    }

    map.get(key).variants.push({
      ...p,
      model: cleanModel
    });
  }

  return Array.from(map.values());
}

function getGroupPrice(variants) {
  const withPrice = variants.find(v => v.promotion_active && Number(v.price) > 0) || variants.find(v => {
    const price = Number(v.price);
    return !Number.isNaN(price) && price > 0;
  });

  return withPrice ? withPrice.price : null;
}

function getGroupPromotion(variants) {
  return variants.find(v => v.promotion_active) || null;
}

function formatPromotionDate(value) {
  if (!value) return '';
  const parts = String(value).split('-');
  return parts.length === 3 ? `${parts[2]}/${parts[1]}/${parts[0]}` : value;
}

function getGroupAvailable(variants) {
  return variants.reduce((total, variant) => {
    return total + Number(variant.available || 0);
  }, 0);
}

function getGroupImage(variants) {
  return variants.find(v => v.image_url) || variants[0] || null;
}

function readPriceFilter(input) {
  if (!input || input.value === '') return null;

  const value = Number(input.value);
  return Number.isFinite(value) && value >= 0 ? value : null;
}

function sortVariants(variants) {
  return [...variants].sort((a, b) => {
    const availableDiff = Number(b.available || 0) - Number(a.available || 0);

    if (availableDiff !== 0) {
      return availableDiff;
    }

    return String(a.color || '').localeCompare(String(b.color || ''), 'vi');
  });
}

function displayVariants(variants) {
  if (showLotDetails) return variants;
  const merged = new Map();
  for (const variant of variants) {
    const key = JSON.stringify([variant.code, normalizeText(variant.color)]);
    if (!merged.has(key)) {
      merged.set(key, { ...variant, batch_number: null, received_date: null,
        stock: 0, reserved: 0, available: 0 });
    }
    const total = merged.get(key);
    for (const field of ['stock', 'reserved', 'available']) {
      total[field] += Number(variant[field] || 0);
    }
  }
  return Array.from(merged.values());
}

function renderColorRows(variants) {
  return sortVariants(displayVariants(variants)).map(v => {
    const badge = stockBadge(v.available);
    const colorName = v.color || 'Chưa có màu';

    return `
      <div class="colorrow ${showLotDetails ? 'with-lot-details' : 'merged-colors'}">
        <div class="swatch" style="${swatchStyle(colorName)}"></div>
        <div class="cname">${escapeHTML(colorName)}${v.batch_number ? `<small class="lot-description">Lô: ${escapeHTML(v.batch_number)}</small>` : ''}</div>
        ${showLotDetails ? `<div class="received-date"><span>${escapeHTML(formatInventoryDate(v.received_date))}</span></div>` : ''}
        ${showLotDetails ? inventoryAgeBadge(v.received_date, true) : ''}
        <div class="stockbadge ${badge.cls}" title="${escapeHTML(badge.label)}">${showLotDetails ? Math.max(0, Number(v.available || 0)).toLocaleString('vi-VN') : escapeHTML(badge.label)}</div>
      </div>
    `;
  }).join('');
}

function formatInventoryDate(value) {
  if (!value) return '';
  const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})/);
  return match ? `${match[3]}/${match[2]}/${match[1]}` : String(value);
}

function inventoryAge(value, now = new Date()) {
  const match = String(value || '').match(/^(\d{4})-(\d{2})-(\d{2})(?:$|T|\s)/);
  if (!match) return null;
  const [, year, month, day] = match.map(Number);
  const received = new Date(Date.UTC(year, month - 1, day));
  if (received.getUTCFullYear() !== year || received.getUTCMonth() !== month - 1 || received.getUTCDate() !== day) return null;
  const today = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit'
  }).formatToParts(now);
  const parts = Object.fromEntries(today.map(part => [part.type, part.value]));
  const age = Math.floor((Date.UTC(Number(parts.year), Number(parts.month) - 1, Number(parts.day)) - received.getTime()) / 86400000);
  return age >= 0 ? age : null;
}

function inventoryAgeBadge(value, compact = false) {
  const age = inventoryAge(value);
  return age === null ? '<span class="inventory-age unknown">—</span>'
    : `<span class="inventory-age ${age > 90 ? 'overdue' : ''}" title="Lưu kho ${age} ngày">${age}${compact ? '' : ' ngày'}</span>`;
}

function inventoryWarnings(items) {
  return items.filter(item => Number(item.available || 0) > 0 && inventoryAge(item.received_date) > 90)
    .sort((a, b) => inventoryAge(b.received_date) - inventoryAge(a.received_date));
}

function updateInventoryWarnings(items = visibleInventory) {
  const button = document.getElementById('inventoryWarningButton');
  const dialog = document.getElementById('inventoryWarningDialog');
  if (!button || !dialog) return;
  button.hidden = !showLotDetails;
  if (!showLotDetails) {
    if (dialog.open) dialog.close();
    return;
  }
  const warnings = inventoryWarnings(items);
  const quantity = warnings.reduce((sum, item) => sum + Number(item.available || 0), 0);
  document.getElementById('inventoryWarningSummary').textContent =
    `${warnings.length} dòng tồn kho · ${quantity.toLocaleString('vi-VN')} chiếc còn hàng quá 90 ngày, theo bộ lọc hiện tại.`;
  document.getElementById('inventoryWarningRows').innerHTML = warnings.length ? warnings.map(item => `
    <tr><td data-label="Mẫu xe">${escapeHTML(item.model)}</td><td data-label="Mã hàng">${escapeHTML(item.code)}</td>
    <td data-label="Màu">${escapeHTML(item.color)}</td><td data-label="Số lô">${escapeHTML(item.batch_number || '—')}</td>
    <td data-label="Ngày nhập">${escapeHTML(formatInventoryDate(item.received_date))}</td>
    <td data-label="Lưu kho">${inventoryAgeBadge(item.received_date)}</td><td data-label="Còn hàng">${Number(item.available || 0).toLocaleString('vi-VN')}</td></tr>
  `).join('') : '<tr><td colspan="7" class="inventory-warning-empty">Không có lô còn hàng quá 90 ngày trong bộ lọc hiện tại.</td></tr>';
}

function buildShareText(group) {
  const inStockVariants = sortVariants(group.variants).filter(v => Number(v.available || 0) > 0);

  const colorNames = inStockVariants.map(v => v.color || 'Chưa có màu').join(', ');

  const price = fmtPrice(getGroupPrice(group.variants));

  return `${group.model}${group.category ? ' - ' + group.category : ''}, còn màu: ${colorNames}. ${priceLabel}: ${price}`;
}

async function copyText(text) {
  const content = String(text || '');

  if (!content) {
    alert('Không có nội dung để copy.');
    return;
  }

  // Cách 1: Clipboard API - chạy tốt trên HTTPS / localhost
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(content);
      alert('Đã copy.');
      return;
    } catch (error) {
      console.warn('Clipboard API lỗi, chuyển sang cách dự phòng:', error);
    }
  }

  // Cách 2: Dự phòng cho điện thoại / HTTP nội bộ
  const textarea = document.createElement('textarea');
  textarea.value = content;
  textarea.setAttribute('readonly', '');

  textarea.style.position = 'fixed';
  textarea.style.top = '0';
  textarea.style.left = '0';
  textarea.style.width = '1px';
  textarea.style.height = '1px';
  textarea.style.opacity = '0';
  textarea.style.zIndex = '-1';

  document.body.appendChild(textarea);

  textarea.focus();
  textarea.select();
  textarea.setSelectionRange(0, textarea.value.length);

  let copied = false;

  try {
    copied = document.execCommand('copy');
  } catch (error) {
    copied = false;
  }

  document.body.removeChild(textarea);

  if (copied) {
    alert('Đã copy.');
    return;
  }

  // Cách 3: Nếu điện thoại vẫn chặn, hiện nội dung để bấm giữ copy tay
  window.prompt('Điện thoại không cho copy tự động. Bạn bấm giữ để copy nội dung này:', content);
}

async function copyProductImage(group) {
  const imgVariant = getGroupImage(sortVariants(group.variants));
  const imageUrl = imgVariant && imgVariant.image_url;

  if (!imageUrl) {
    alert('Sản phẩm này chưa có ảnh để copy.');
    return;
  }

  if (!navigator.clipboard || !window.ClipboardItem) {
    alert('Trình duyệt này không hỗ trợ copy ảnh. Bạn có thể bấm giữ vào ảnh để lưu/gửi thủ công.');
    return;
  }

  try {
    const response = await fetch(imageUrl, { mode: 'cors' });
    const blob = await response.blob();
    const pngBlob = await toPngBlob(blob);

    await navigator.clipboard.write([
      new ClipboardItem({
        'image/png': pngBlob
      })
    ]);

    alert('Đã copy ảnh. Dán (Ctrl+V) vào Zalo/Facebook để gửi khách.');
  } catch (error) {
    console.warn('Không copy được ảnh:', error);
    alert('Không copy được ảnh (có thể do lỗi tải ảnh). Bạn có thể bấm giữ vào ảnh để lưu/gửi thủ công.');
  }
}

async function copyProductText(group) {
  await copyText(buildShareText(group));
}

async function downloadProductImage(imageUrl, model, button) {
  if (!imageUrl || button.disabled) return;

  const label = button.textContent;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);
  button.disabled = true;
  button.textContent = 'Đang tải…';
  button.setAttribute('aria-busy', 'true');

  try {
    const response = await fetch(imageUrl, { mode: 'cors', signal: controller.signal });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const blob = await response.blob();
    if (!blob.size || !blob.type.startsWith('image/')) throw new Error('Ảnh không hợp lệ');

    // Use the full image and export PNG for easy sharing on phones and computers.
    const pngBlob = await toPngBlob(blob);
    const filename = String(model || 'san-pham')
      .replace(/[<>:"/\\|?*\u0000-\u001f]/g, '-')
      .replace(/[.\s]+$/g, '').trim().slice(0, 120) || 'san-pham';
    const url = URL.createObjectURL(pngBlob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `Abraham-${filename}.png`;
    document.body.appendChild(link);
    try {
      link.click();
    } finally {
      link.remove();
      // Give the browser time to begin saving before releasing the image bytes.
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    }
  } catch (error) {
    console.warn('Không tải được ảnh:', error);
    alert('Không tải được ảnh. Vui lòng kiểm tra kết nối và thử lại.');
  } finally {
    clearTimeout(timeout);
    button.disabled = false;
    button.textContent = label;
    button.removeAttribute('aria-busy');
  }
}

function toPngBlob(blob) {
  if (blob.type === 'image/png') {
    return Promise.resolve(blob);
  }

  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(blob);

    img.onload = () => {
      const canvas = document.createElement('canvas');
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;

      const ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0);

      canvas.toBlob(pngBlob => {
        URL.revokeObjectURL(url);
        if (pngBlob) resolve(pngBlob);
        else reject(new Error('Không convert được ảnh sang PNG'));
      }, 'image/png');
    };

    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error('Không tải được ảnh'));
    };

    img.src = url;
  });
}

function openProductModal(group) {
  playUISound('open');
  const variants = sortVariants(displayVariants(group.variants));
  const imgVariant = getGroupImage(variants);
  const groupPrice = getGroupPrice(variants);

  const totalStock = variants.reduce((sum, v) => sum + Number(v.stock || 0), 0);
  const totalReserved = variants.reduce((sum, v) => sum + Number(v.reserved || 0), 0);
  const totalAvailable = variants.reduce((sum, v) => sum + Number(v.available || 0), 0);

  els.modalTitle.textContent = group.model;
  els.modalSub.textContent = group.category || 'Chưa phân loại';

  const imageHTML = imgVariant && imgVariant.image_url
    ? `<img data-product-image class="modal-image" alt="${escapeHTML(group.model)}" decoding="async">`
    : `<div class="modal-no-image">Chưa có ảnh sản phẩm</div>`;

  const variantRows = variants.map(v => {
    const badge = stockBadge(v.available);
    const colorName = v.color || 'Chưa có màu';

    return `
      <div class="variant-row">
        <div class="swatch" style="${swatchStyle(colorName)}"></div>

        <div>
          <div class="variant-color">${escapeHTML(colorName)}</div>
          <div class="variant-code">Mã hàng: ${escapeHTML(v.code)}</div>
          ${v.batch_number ? `<div class="variant-code">Số lô: ${escapeHTML(v.batch_number)}</div>` : ''}
          ${showLotDetails ? `<div class="variant-code">Ngày nhập kho: ${escapeHTML(formatInventoryDate(v.received_date))}</div>` : ''}
          ${showLotDetails ? inventoryAgeBadge(v.received_date) : ''}
        </div>

        <div class="stockbadge ${badge.cls} modal-stock">
          ${showLotDetails ? Math.max(0, Number(v.available || 0)).toLocaleString('vi-VN') : escapeHTML(badge.label)}
        </div>

        <button type="button" class="copy-btn" data-copy="${escapeHTML(v.code)}">
          Copy mã
        </button>
      </div>
    `;
  }).join('');

  els.modalBody.innerHTML = `
    <div class="modal-image-wrap">
      ${imageHTML}
    </div>

    <div>
      <div class="modal-info-grid">
        <div class="modal-stat">
          <div class="modal-stat-label">Tổng tồn</div>
          <div class="modal-stat-value">${totalStock.toLocaleString('vi-VN')}</div>
        </div>

        <div class="modal-stat">
          <div class="modal-stat-label">Đã đặt</div>
          <div class="modal-stat-value">${totalReserved.toLocaleString('vi-VN')}</div>
        </div>

        <div class="modal-stat">
          <div class="modal-stat-label">Có thể bán</div>
          <div class="modal-stat-value">${totalAvailable.toLocaleString('vi-VN')}</div>
        </div>
      </div>

      <div class="modal-info-grid">
        <div class="modal-stat">
          <div class="modal-stat-label">Số màu</div>
          <div class="modal-stat-value">${new Set(variants.map(v => v.color || '')).size}</div>
        </div>

        <div class="modal-stat">
          <div class="modal-stat-label">${priceLabel}</div>
          <div class="modal-stat-value">${escapeHTML(fmtPrice(groupPrice))}</div>
        </div>

        <div class="modal-stat">
          <div class="modal-stat-label">Loại</div>
          <div class="modal-stat-value">${escapeHTML(group.category || 'N/A')}</div>
        </div>
      </div>

      <h3 class="variant-title">Danh sách màu / mã hàng</h3>

      <div class="variant-list">
        ${variantRows}
      </div>

      <div class="copy-pair-row">
        ${imgVariant && imgVariant.image_url ? `<button type="button" class="modal-zoom-btn" id="modalZoomBtn" aria-label="Phóng to ảnh ${escapeHTML(group.model)}"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3M11 8v6M8 11h6"/></svg>Phóng to</button>` : ''}
        <button type="button" class="copy-all-btn" id="copyProductImageBtn">
          Copy ảnh
        </button>

        <button type="button" class="copy-all-btn" id="downloadProductImageBtn" aria-label="Tải ảnh sản phẩm" ${imgVariant && imgVariant.image_url ? '' : 'disabled'}>
          Tải ảnh
        </button>

        <button type="button" class="copy-all-btn" id="copyProductTextBtn">
          Copy danh sách
        </button>
      </div>

      <div class="modal-note">
        Gợi ý: bấm "Tải ảnh" để lưu ảnh về máy, hoặc "Copy ảnh" để dán vào Zalo/Facebook. Sau đó bấm "Copy danh sách" để gửi kèm thông tin cho khách.
      </div>
    </div>
  `;

  els.modalBody.querySelectorAll('.copy-btn').forEach(btn => {
    btn.addEventListener('click', event => {
      event.stopPropagation();
      playUISound('celebration');
      copyText(btn.dataset.copy || '');
    });
  });

  const copyImageBtn = document.getElementById('copyProductImageBtn');
  const downloadImageBtn = document.getElementById('downloadProductImageBtn');
  downloadImageBtn.addEventListener('click', event => {
    event.stopPropagation();
    downloadProductImage(imgVariant?.image_url, group.model, downloadImageBtn);
  });
  const zoomBtn = document.getElementById('modalZoomBtn');
  if (zoomBtn) {
    loadProductDetailImage(els.modalBody.querySelector('.modal-image'), imgVariant.image_thumb_url, imgVariant.image_url);
    zoomBtn.addEventListener('click', () => openImageZoom(imgVariant.image_url, group.model, group, imgVariant.image_thumb_url));
  }

  if (copyImageBtn) {
    copyImageBtn.addEventListener('click', event => {
      event.stopPropagation();
      playUISound('celebration');
      copyProductImage(group);
    });
  }

  const copyTextBtn = document.getElementById('copyProductTextBtn');
  if (copyTextBtn) {
    copyTextBtn.addEventListener('click', event => {
      event.stopPropagation();
      playUISound('celebration');
      copyProductText(group);
    });
  }

  els.modal.showModal();
}

function render() {
  if (catalogBusy || catalogFailed) return;
  catalogImageObserver?.disconnect();
  // The server filters and sorts the complete inventory before pagination.
  const filtered = PRODUCTS;
  visibleInventory = filtered;
  const warningButton = document.getElementById('inventoryWarningButton');
  if (warningButton) warningButton.hidden = !showLotDetails;
  const groups = groupByModel(filtered);

  els.grid.innerHTML = '';
  els.empty.style.display = groups.length ? 'none' : 'block';

  els.summaryText.textContent = `${catalogTotalGroups.toLocaleString('vi-VN')} mẫu xe${catalogTotalGroups > groups.length ? ` · Đang xem ${catalogPage * 24 + 1}–${catalogPage * 24 + groups.length}` : ''}`;
  els.summaryStock.textContent = `${catalogTotalAvailable.toLocaleString('vi-VN')} chiếc sẵn sàng theo bộ lọc`;

  for (const g of groups) {
    const card = document.createElement('div');
    card.className = 'card';
    card.tabIndex = 0;
    card.setAttribute('role', 'button');
    card.setAttribute('aria-label', `Xem ${g.model}`);
    card.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        openProductModal(g);
      }
    });

    const imgVariant = getGroupImage(g.variants);
    const groupPrice = getGroupPrice(g.variants);
    const promotion = getGroupPromotion(g.variants);
    const colorRows = renderColorRows(g.variants);

    card.innerHTML = `
      <div class="card-top">
        ${promotion ? `<div class="promotion-ribbon ${promotion.promotion_tag === 'hot' ? 'hot' : 'discount'}">${promotion.promotion_tag === 'hot' ? 'HOT' : 'GIẢM GIÁ'}</div>` : ''}
        ${
          imgVariant && imgVariant.image_url
            ? `<div class="card-image-stage">
                <img data-product-image class="card-img" data-catalog-src="${escapeHTML(imgVariant.image_thumb_url || imgVariant.image_url)}" alt="${escapeHTML(g.model)}" loading="lazy" decoding="async" fetchpriority="low">
              </div>`
            : `<div class="card-image-stage">${productImagePlaceholder()}</div>`
        }

        <div class="model">${escapeHTML(g.model)}</div>

        ${
          g.category
            ? `<div class="cat-tag">${escapeHTML(g.category)}</div>`
            : ''
        }
      </div>

      <div class="colorlist">
        ${colorRows}
      </div>

      <div class="card-footer">
      <div class="price-row">
        <span>${priceLabel}</span>
        <span class="price">${promotion && promotion.original_price ? `<del>${escapeHTML(fmtPrice(promotion.original_price))}</del>` : ''}${escapeHTML(fmtPrice(groupPrice))}</span>
      </div>
      ${promotion ? `<div class="promotion-period">Áp dụng ${formatPromotionDate(promotion.promotion_start)} – ${formatPromotionDate(promotion.promotion_end)}</div>` : '<div class="promotion-period" aria-hidden="true"></div>'}
      </div>
    `;

    card.addEventListener('click', () => {
      openProductModal(g);
    });

    els.grid.appendChild(card);
  }
  for (const img of els.grid.querySelectorAll('img[data-catalog-src]')) {
    if (catalogImageObserver) catalogImageObserver.observe(img);
    else loadCatalogImage(img);
  }
  renderPagination();
}

function renderPagination() {
  const pagination = document.getElementById('catalogPagination');
  const pages = Math.ceil(catalogTotalGroups / 24);
  pagination.replaceChildren();
  if (pages <= 1) return;
  const previous = document.createElement('button');
  previous.type = 'button';
  previous.textContent = '← Trang trước';
  previous.disabled = catalogPage === 0 || catalogBusy;
  const next = document.createElement('button');
  next.type = 'button';
  next.textContent = 'Trang sau →';
  next.disabled = !catalogHasMore || catalogBusy;
  const label = document.createElement('span');
  label.textContent = `${catalogPage + 1} / ${pages}`;
  for (const [button, page] of [[previous, catalogPage - 1], [next, catalogPage + 1]]) {
    button.addEventListener('click', async () => {
      if (await loadCatalogPage(page)) {
        document.querySelector('.catalog-controls-shell').scrollIntoView({block: 'start'});
      }
    });
  }
  pagination.append(previous, label, next);
}

function buildPills() {
  const cats = ['Tất cả', ...Array.from(new Set(catalogCategories.filter(Boolean))).sort((a, b) => a.localeCompare(b, 'vi'))];
  const signature = JSON.stringify([cats, activeCat]);
  if (els.pills.dataset.signature === signature) return;
  els.pills.dataset.signature = signature;
  els.pills.innerHTML = cats.map(c => `<button type="button" class="pill ${c === activeCat ? 'active' : ''}" data-cat="${escapeHTML(c)}" aria-pressed="${c === activeCat}">${escapeHTML(c)}</button>`).join('');
  els.pills.querySelectorAll('.pill').forEach(button => {
    button.addEventListener('click', () => {
      activeCat = button.dataset.cat;
      buildPills();
      scheduleCatalogSearch(0);
    });
  });
}

function catalogParams(page = 0) {
  const params = new URLSearchParams({page: String(page), page_size: '24', v: catalogCacheVersion});
  const q = els.search.value.trim();
  if (q) params.set('q', q);
  if (activeCat !== 'Tất cả') params.set('category', activeCat);
  if (onlyInStock) params.set('only_stock', '1');
  if (sortStockOrder) params.set('sort', sortStockOrder);
  if (minPrice !== null) params.set('min_price', String(minPrice));
  if (maxPrice !== null) params.set('max_price', String(maxPrice));
  if (isPromotionCatalog) params.set('promotion', 'discount');
  return params;
}

function setCatalogBusy(busy) {
  catalogBusy = busy;
  els.grid.setAttribute('aria-busy', String(busy));
  els.grid.inert = busy;
  const status = document.getElementById('catalogStatus');
  status.hidden = !busy;
  if (busy) {
    status.textContent = 'Đang tìm sản phẩm…';
    els.empty.style.display = 'none';
  }
  document.querySelectorAll('#catalogPagination button').forEach(button => {button.disabled = busy;});
}

function scheduleCatalogSearch(delay = 220) {
  clearTimeout(catalogSearchTimer);
  document.getElementById('inventoryWarningDialog')?.close();
  // Invalidate immediately, even during debounce, so an older response cannot win.
  catalogRequestId += 1;
  catalogController?.abort();
  setCatalogBusy(true);
  const filterCount = Number(minPrice !== null) + Number(maxPrice !== null);
  document.getElementById('filterCount').textContent = filterCount ? `(${filterCount})` : '';
  catalogSearchTimer = setTimeout(() => loadCatalogPage(0), delay);
}

async function loadCatalogPage(page = 0) {
  clearTimeout(catalogSearchTimer);
  catalogController?.abort();
  const controller = new AbortController();
  catalogController = controller;
  const requestId = ++catalogRequestId;
  const params = catalogParams(page);
  setCatalogBusy(true);
  const timeout = setTimeout(() => controller.abort('timeout'), 20000);
  try {
    const response = await fetch(`/api/products/${priceType}?${params}`, {signal: controller.signal, cache: 'no-store', priority: 'high'});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    if (priceType === 'retail' && response.headers.get('X-Retail-Prices-Visible') !== '1') {
      window.location.reload();
      return false;
    }
    const data = await response.json();
    if (requestId !== catalogRequestId) return false;
    if (!Array.isArray(data)) throw new Error('Invalid catalog response');
    catalogCacheVersion = response.headers.get('X-Catalog-Cache-Version') || catalogCacheVersion;
    PRODUCTS = data.map(prepareProduct);
    catalogFailed = false;
    try {
      const categories = JSON.parse(response.headers.get('X-Catalog-Categories') || '[]');
      catalogCategories = Array.isArray(categories) ? categories : [];
    } catch (_error) { catalogCategories = []; }
    catalogPage = page;
    catalogHasMore = response.headers.get('X-Catalog-Has-More') === '1';
    catalogTotalGroups = Number(response.headers.get('X-Catalog-Total-Groups') || 0);
    catalogTotalAvailable = Number(response.headers.get('X-Catalog-Total-Available') || 0);
    catalogLastLoadedAt = Date.now();
    setCatalogBusy(false);
    buildPills();
    render();
    return true;
  } catch (error) {
    if (requestId !== catalogRequestId) return false;
    setCatalogBusy(false);
    catalogFailed = true;
    PRODUCTS = [];
    catalogTotalGroups = catalogTotalAvailable = 0;
    els.grid.replaceChildren();
    document.getElementById('catalogPagination').replaceChildren();
    els.summaryText.textContent = 'Chưa tải được sản phẩm';
    els.summaryStock.textContent = '';
    const status = document.getElementById('catalogStatus');
    status.hidden = false;
    status.textContent = 'Kết nối bị gián đoạn. Vui lòng thử lại.';
    const retry = document.createElement('button');
    retry.type = 'button';
    retry.className = 'catalog-tool-button';
    retry.textContent = 'Thử lại';
    retry.addEventListener('click', () => loadCatalogPage(page));
    status.append(retry);
    return false;
  } finally {
    clearTimeout(timeout);
    if (requestId === catalogRequestId) catalogController = null;
  }
}

function load() { return loadCatalogPage(catalogPage); }

if (els.search) {
  els.search.addEventListener('compositionstart', () => {
    searchComposing = true;
    clearTimeout(catalogSearchTimer);
    catalogRequestId += 1;
    catalogController?.abort();
  });
  els.search.addEventListener('compositionend', () => { searchComposing = false; scheduleCatalogSearch(); });
  els.search.addEventListener('input', () => { if (!searchComposing) scheduleCatalogSearch(); });
  els.search.addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.isComposing) { event.preventDefault(); scheduleCatalogSearch(0); }
  });
}
if (els.onlyStock) els.onlyStock.addEventListener('change', () => {
  onlyInStock = els.onlyStock.checked;
  scheduleCatalogSearch(0);
});

function resetCatalogFilters() {
  els.search.value = '';
  activeCat = 'Tất cả';
  onlyInStock = false;
  els.onlyStock.checked = false;
  sortStockOrder = '';
  els.sortStock.value = '';
  minPrice = maxPrice = null;
  els.minPrice.value = els.maxPrice.value = '';
  buildPills();
  scheduleCatalogSearch(0);
}
document.getElementById('resetCatalogFilters').addEventListener('click', resetCatalogFilters);
document.getElementById('emptyResetFilters').addEventListener('click', resetCatalogFilters);

if (els.lotDetails) {
  els.lotDetails.checked = showLotDetails;
  els.lotDetails.addEventListener('change', () => {
    showLotDetails = els.lotDetails.checked;
    document.getElementById('inventoryWarningButton').hidden = !showLotDetails;
    render();
  });
}

document.getElementById('inventoryWarningButton')?.addEventListener('click', async () => {
  if (!showLotDetails) return;
  const dialog = document.getElementById('inventoryWarningDialog');
  const summary = document.getElementById('inventoryWarningSummary');
  const rows = document.getElementById('inventoryWarningRows');
  warningController?.abort();
  const controller = new AbortController();
  warningController = controller;
  summary.textContent = 'Đang kiểm tra các lô quá 90 ngày theo bộ lọc…';
  rows.replaceChildren();
  dialog.showModal();
  const params = catalogParams();
  params.set('overdue', '1');
  params.set('page_size', '60');
  const timeout = setTimeout(() => controller.abort(), 30000);
  try {
    const items = [];
    let page = 0;
    let hasMore;
    do {
      params.set('page', String(page++));
      const response = await fetch(`/api/products/${priceType}?${params}`, {signal: controller.signal});
      if (!response.ok) throw new Error('Could not load inventory warnings');
      items.push(...(await response.json()).map(prepareProduct));
      hasMore = response.headers.get('X-Catalog-Has-More') === '1';
    } while (hasMore);
    if (warningController === controller && dialog.open) updateInventoryWarnings(items);
  } catch (_error) {
    if (warningController === controller && dialog.open) summary.textContent = 'Chưa tải được cảnh báo. Đóng và mở lại để thử lại.';
  } finally { clearTimeout(timeout); }
});

document.getElementById('inventoryWarningDialog')?.addEventListener('close', () => {
  warningController?.abort();
  warningController = null;
});
document.getElementById('inventoryWarningClose')?.addEventListener('click', () => {
  document.getElementById('inventoryWarningDialog').close();
});
document.getElementById('inventoryWarningDialog')?.addEventListener('click', event => {
  if (event.target === event.currentTarget) event.currentTarget.close();
});

if (els.sortStock) els.sortStock.addEventListener('change', () => {
  sortStockOrder = els.sortStock.value;
  scheduleCatalogSearch(0);
});
for (const input of [els.minPrice, els.maxPrice]) {
  input?.addEventListener('input', () => {
    minPrice = readPriceFilter(els.minPrice);
    maxPrice = readPriceFilter(els.maxPrice);
    scheduleCatalogSearch();
  });
}

if (els.modalClose) {
  els.modalClose.addEventListener('click', () => {
    playUISound('close');
    els.modal.close();
  });
}

function renderReorderSuggestions() {
  const list = document.getElementById('reorderList');
  const mobileCount = document.getElementById('reorderMobileCount');
  if (!list) return;

  if (!REORDER_ITEMS.length) {
    list.innerHTML = '<div class="reorder-empty">Tồn kho hiện tại đang đủ mức dự trữ 2 tháng.</div>';
    if (mobileCount) mobileCount.textContent = 'Tồn kho đang đủ';
    return;
  }

  if (mobileCount) mobileCount.textContent = `${REORDER_ITEMS.length} sản phẩm cần nhập`;

  const filteredItems = REORDER_ITEMS.filter(item => {
    if (!reorderQuery) return true;
    return normalizeText(`${item.model || ''} ${item.category || ''}`).includes(reorderQuery);
  });

  if (!filteredItems.length) {
    list.innerHTML = '<div class="reorder-empty">Không tìm thấy sản phẩm cần nhập phù hợp.</div>';
    return;
  }

  list.innerHTML = filteredItems.map(item => `
    <article class="reorder-item">
      <div class="reorder-thumb">
        ${item.image_url
          ? `<img data-product-image src="${escapeHTML(item.image_thumb_url || item.image_url)}" alt="${escapeHTML(item.model)}" loading="lazy" decoding="async">`
          : productImagePlaceholder()}
      </div>
      <div class="reorder-copy">
        <strong>${escapeHTML(item.model)}</strong>
        <span>Tồn kho: <b>${Number(item.stock).toLocaleString('vi-VN')}</b></span>
        <span>Bán TB/tháng: ${Number(item.average_monthly_sales).toLocaleString('vi-VN')}</span>
      </div>
      <div class="reorder-needed">
        <span>Cần nhập</span>
        <strong>${Number(item.reorder_quantity).toLocaleString('vi-VN')}</strong>
      </div>
    </article>
  `).join('');

}

function renderPromotionSuggestions() {
  const list = document.getElementById('promotionSuggestionList');
  if (!list) return;

  const promotionGroups = groupByModel(promotionSuggestions)
    .map(group => {
      const promotion = getGroupPromotion(group.variants);
      return promotion ? { group, promotion } : null;
    })
    .filter(Boolean)
    .sort((a, b) => {
      const aDiscount = Number(a.promotion.original_price || 0) - Number(a.promotion.price || 0);
      const bDiscount = Number(b.promotion.original_price || 0) - Number(b.promotion.price || 0);
      return bDiscount - aDiscount;
    });

  if (!promotionGroups.length) {
    list.innerHTML = '<div class="promotion-suggestion-empty">Chưa có chương trình khuyến mãi đang áp dụng.</div>';
    return;
  }

  list.innerHTML = promotionGroups.map(({ group, promotion }) => `
    <a class="promotion-suggestion-item" href="/ctkm" aria-label="Xem khuyến mãi ${escapeHTML(group.model)}">
      <div class="promotion-suggestion-thumb">
        ${promotion.image_url
          ? `<img data-product-image src="${escapeHTML(promotion.image_thumb_url || promotion.image_url)}" alt="${escapeHTML(group.model)}" loading="lazy" decoding="async">`
          : productImagePlaceholder()}
      </div>
      <div class="promotion-suggestion-copy">
        <span class="promotion-suggestion-tag ${promotion.promotion_tag === 'hot' ? 'hot' : 'discount'}">
          ${promotion.promotion_tag === 'hot' ? 'HOT' : 'GIẢM GIÁ'}
        </span>
        <strong>${escapeHTML(group.model)}</strong>
        <span class="promotion-suggestion-period">${formatPromotionDate(promotion.promotion_start)} – ${formatPromotionDate(promotion.promotion_end)}</span>
      </div>
      <div class="promotion-suggestion-price">
        ${promotion.original_price ? `<del>${escapeHTML(fmtPrice(promotion.original_price))}</del>` : ''}
        <strong>${escapeHTML(fmtPrice(promotion.price))}</strong>
      </div>
    </a>
  `).join('');
}

async function loadReorderSuggestions() {
  const list = document.getElementById('reorderList');
  if (!list || reorderRefreshInFlight) return;
  reorderRefreshInFlight = true;

  try {
    const response = await fetch(`/api/reorder-suggestions?v=${encodeURIComponent(catalogCacheVersion)}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    catalogCacheVersion = response.headers.get('X-Catalog-Cache-Version') || catalogCacheVersion;
    REORDER_ITEMS = Array.isArray(data.items) ? data.items : [];
    reorderLastLoadedAt = Date.now();
    renderReorderSuggestions();
  } catch (error) {
    console.error('Không tải được gợi ý nhập hàng:', error);
    list.innerHTML = '<div class="reorder-empty reorder-error">Chưa thể tính gợi ý nhập hàng.</div>';
  } finally {
    reorderRefreshInFlight = false;
  }
}

const reorderPanel = document.getElementById('reorderPanel');
const reorderDock = document.querySelector('.reorder-dock');
const reorderDesktopToggle = document.getElementById('reorderDesktopToggle');
const catalogContentLayout = document.querySelector('.catalog-content-layout');
const reorderDesktopMedia = window.matchMedia('(min-width: 1101px)');
const reorderMobileTrigger = document.getElementById('reorderMobileTrigger');
const reorderMobileClose = document.getElementById('reorderMobileClose');
const reorderBackdrop = document.getElementById('reorderBackdrop');
const reorderSearch = document.getElementById('reorderSearch');

function setReorderPanelOpen(open, moveFocus = true) {
  if (!reorderPanel || !reorderMobileTrigger) return;
  const desktop = reorderDesktopMedia.matches;
  const modalOpen = open && !desktop;
  reorderPanel.hidden = !open;
  reorderBackdrop.hidden = !modalOpen;
  catalogContentLayout.classList.toggle('reorder-collapsed', !open);
  reorderDock.classList.toggle('is-open', open);
  reorderPanel.classList.toggle('mobile-open', modalOpen);
  document.body.classList.toggle('reorder-sheet-open', modalOpen);
  reorderMobileTrigger.setAttribute('aria-expanded', String(open));
  reorderDesktopToggle.setAttribute('aria-expanded', String(open));
  const toggleLabel = open ? 'Thu gọn gợi ý nhập hàng' : 'Mở gợi ý nhập hàng';
  reorderDesktopToggle.setAttribute('aria-label', toggleLabel);
  reorderDesktopToggle.title = toggleLabel;
  reorderDesktopToggle.querySelector('.reorder-toggle-arrow').textContent = open ? '›' : '‹';
  if (modalOpen) {
    reorderPanel.setAttribute('role', 'dialog');
    reorderPanel.setAttribute('aria-modal', 'true');
  } else {
    reorderPanel.removeAttribute('role');
    reorderPanel.removeAttribute('aria-modal');
  }
  for (const selector of ['.catalog-controls-shell', '.catalog-main', '.catalog-heading', '.catalog-topbar', '.catalog-branding', '#inventoryAiLauncher', '#inventoryAiPanel']) {
    document.querySelector(selector).inert = modalOpen;
  }
  if (open) {
    if (modalOpen && moveFocus) reorderMobileClose.focus();
    if (Date.now() - reorderLastLoadedAt > 300000) loadReorderSuggestions();
    if (Date.now() - promotionSuggestionsLoadedAt > 300000) loadPromotionSuggestions();
  } else if (moveFocus) {
    (desktop ? reorderDesktopToggle : reorderMobileTrigger).focus();
  }
}

reorderDesktopToggle?.addEventListener('click', () => setReorderPanelOpen(reorderPanel.hidden));
reorderDesktopMedia.addEventListener('change', () => setReorderPanelOpen(false, false));

async function loadPromotionSuggestions() {
  if (promotionSuggestionsLoading) return;
  promotionSuggestionsLoading = true;
  const list = document.getElementById('promotionSuggestionList');
  list.textContent = 'Đang tải khuyến mãi…';
  try {
    const response = await fetch(`/api/products/${priceType}?promotion=all&page_size=6`);
    if (!response.ok) throw new Error('Could not load promotions');
    promotionSuggestions = (await response.json()).map(prepareProduct);
    promotionSuggestionsLoadedAt = Date.now();
    renderPromotionSuggestions();
  } catch (_error) { list.textContent = 'Chưa tải được khuyến mãi. Mở mục Khuyến mãi để thử lại.'; }
  finally { promotionSuggestionsLoading = false; }
}

reorderPanel?.addEventListener('keydown', event => {
  if (event.key !== 'Tab' || reorderDesktopMedia.matches || reorderPanel.hidden) return;
  const focusable = Array.from(reorderPanel.querySelectorAll('button, input, a[href]')).filter(el => !el.disabled && el.getClientRects().length);
  const first = focusable[0], last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
});

if (reorderMobileTrigger) {
  reorderMobileTrigger.addEventListener('click', () => setReorderPanelOpen(true));
}

if (reorderMobileClose) {
  reorderMobileClose.addEventListener('click', () => setReorderPanelOpen(false));
}

if (reorderBackdrop) {
  reorderBackdrop.addEventListener('click', () => setReorderPanelOpen(false));
}

if (reorderSearch) {
  reorderSearch.addEventListener('input', () => {
    reorderQuery = normalizeText(reorderSearch.value);
    renderReorderSuggestions();
  });
}

document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && !reorderPanel.hidden && !document.querySelector('dialog[open]')) setReorderPanelOpen(false);
});

setInterval(() => {
  if (!reorderPanel.hidden && document.visibilityState === 'visible' && Date.now() - reorderLastLoadedAt >= 5 * 60 * 1000) {
    loadReorderSuggestions();
  }
}, 5 * 60 * 1000);
document.addEventListener('visibilitychange', () => {
  if (!reorderPanel.hidden && !document.hidden && Date.now() - reorderLastLoadedAt >= 5 * 60 * 1000) {
    loadReorderSuggestions();
  }
});

if (els.zoomDialog) {
  els.zoomImage.addEventListener('load', () => {
    if (els.zoomDialog.open) layoutImageZoom();
  });
  els.zoomClose.addEventListener('click', () => els.zoomDialog.close());
  els.zoomCopy.addEventListener('click', () => {
    if (zoomGroup) copyProductImage(zoomGroup);
  });
  els.zoomDownload.addEventListener('click', () => {
    downloadProductImage(els.zoomImage.dataset.fullSrc, els.zoomTitle.textContent, els.zoomDownload);
  });
  els.zoomDialog.addEventListener('close', () => { zoomGroup = null; });
  els.zoomIn.addEventListener('click', () => setImageZoom(imageZoom + .5));
  els.zoomOut.addEventListener('click', () => setImageZoom(imageZoom - .5));
  els.zoomDialog.addEventListener('click', event => {
    if (event.target === els.zoomDialog) els.zoomDialog.close();
  });
  els.zoomViewport.addEventListener('pointerdown', event => {
    if (imageZoom === 1 || event.pointerType === 'touch' || event.button !== 0) return;
    zoomDrag = {
      x: event.clientX,
      y: event.clientY,
      left: els.zoomViewport.scrollLeft,
      top: els.zoomViewport.scrollTop,
    };
    els.zoomViewport.setPointerCapture(event.pointerId);
    els.zoomViewport.classList.add('is-dragging');
    event.preventDefault();
  });
  els.zoomViewport.addEventListener('pointermove', event => {
    if (!zoomDrag) return;
    els.zoomViewport.scrollTo(
      zoomDrag.left - (event.clientX - zoomDrag.x),
      zoomDrag.top - (event.clientY - zoomDrag.y)
    );
  });
  const stopZoomDrag = () => {
    zoomDrag = null;
    els.zoomViewport.classList.remove('is-dragging');
  };
  els.zoomViewport.addEventListener('pointerup', stopZoomDrag);
  els.zoomViewport.addEventListener('pointercancel', stopZoomDrag);
  window.addEventListener('resize', () => {
    if (els.zoomDialog.open) layoutImageZoom();
  });
}

if (els.modal) {
  els.modal.addEventListener('click', event => {
    if (event.target === els.modal) {
      playUISound('close');
      els.modal.close();
    }
  });
}

document.addEventListener('keydown', event => {
  if (els.zoomDialog && els.zoomDialog.open) {
    if (event.key === '+' || event.key === '=') setImageZoom(imageZoom + .5);
    if (event.key === '-') setImageZoom(imageZoom - .5);
    return;
  }
  if (event.key === 'Escape' && els.modal && els.modal.open) {
    playUISound('close');
    els.modal.close();
  }
});

document.addEventListener('click', event => {
  if (event.target.closest('.pills-arrow')) {
    playUISound('click');
  }
});

// Mobile browsers require audio to be initialized from a real touch gesture.
document.addEventListener('pointerdown', unlockAudio, { once: true, passive: true });
document.addEventListener('touchstart', unlockAudio, { once: true, passive: true });

load();

setInterval(() => {
  if (!catalogBusy && document.visibilityState === 'visible' && Date.now() - catalogLastLoadedAt >= 5 * 60 * 1000) {
    load();
  }
}, 300000);
document.addEventListener('visibilitychange', () => {
  if (!catalogBusy && document.visibilityState === 'visible' && Date.now() - catalogLastLoadedAt >= 5 * 60 * 1000) {
    load();
  }
});
