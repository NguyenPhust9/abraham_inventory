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
let REORDER_ITEMS = [];
let reorderQuery = '';
let reorderRefreshInFlight = false;
let reorderLastLoadedAt = 0;
const priceType = document.querySelector('.catalog-page')?.dataset.priceType === 'retail' ? 'retail' : 'dealer';
const priceLabel = priceType === 'retail' ? 'Giá lẻ' : 'Giá đại lý';
let activeCat = 'Tất cả';
let onlyInStock = false;
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
  zoomIn: document.getElementById('imageZoomIn'),
  zoomOut: document.getElementById('imageZoomOut'),
  zoomClose: document.getElementById('imageZoomClose'),
};

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

function openImageZoom(imageUrl, title, group) {
  if (!imageUrl || !els.zoomDialog) return;
  zoomGroup = group;
  els.zoomStage.style.width = '0px';
  els.zoomStage.style.height = '0px';
  els.zoomImage.src = imageUrl;
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
    lantern: { frequency: 760, endFrequency: 1120, duration: .13, volume: .07 },
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
    image_url: p.image_url || null
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
  const withPrice = variants.find(v => {
    const price = Number(v.price);
    return !Number.isNaN(price) && price > 0;
  });

  return withPrice ? withPrice.price : null;
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

function renderColorRows(variants) {
  return sortVariants(variants).map(v => {
    const badge = stockBadge(v.available);
    const colorName = v.color || 'Chưa có màu';

    return `
      <div class="colorrow">
        <div class="swatch" style="${swatchStyle(colorName)}"></div>
        <div class="cname">${escapeHTML(colorName)}</div>
        <div class="stockbadge ${badge.cls}">${escapeHTML(badge.label)}</div>
      </div>
    `;
  }).join('');
}

function matchesSearch(product, keyword) {
  if (!keyword) return true;

  const searchText = [
    product.model,
    product.original_model,
    product.code,
    product.color,
    product.category
  ].map(normalizeText).join(' ');

  return searchText.includes(keyword);
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
  const variants = sortVariants(group.variants);
  const imgVariant = getGroupImage(variants);
  const groupPrice = getGroupPrice(variants);

  const totalStock = variants.reduce((sum, v) => sum + Number(v.stock || 0), 0);
  const totalReserved = variants.reduce((sum, v) => sum + Number(v.reserved || 0), 0);
  const totalAvailable = variants.reduce((sum, v) => sum + Number(v.available || 0), 0);

  els.modalTitle.textContent = group.model;
  els.modalSub.textContent = group.category || 'Chưa phân loại';

  const imageHTML = imgVariant && imgVariant.image_url
    ? `<img class="modal-image" src="${escapeHTML(imgVariant.image_url)}" alt="${escapeHTML(group.model)}">
       <button type="button" class="modal-zoom-btn" id="modalZoomBtn" aria-label="Phóng to ảnh ${escapeHTML(group.model)}">⌕ Phóng to</button>`
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
        </div>

        <div class="stockbadge ${badge.cls} modal-stock">
          ${escapeHTML(badge.label)}
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
          <div class="modal-stat-value">${variants.length}</div>
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
        <button type="button" class="copy-all-btn" id="copyProductImageBtn">
          Copy ảnh
        </button>

        <button type="button" class="copy-all-btn" id="copyProductTextBtn">
          Copy danh sách
        </button>
      </div>

      <div class="modal-note">
        Gợi ý: bấm "Copy ảnh" dán vào Zalo/Facebook trước, sau đó bấm "Copy danh sách" dán tin nhắn tiếp theo để gửi khách đầy đủ.
      </div>
    </div>
  `;

  els.modalBody.querySelectorAll('.copy-btn').forEach(btn => {
    btn.addEventListener('click', event => {
      event.stopPropagation();
      playUISound('lantern');
      copyText(btn.dataset.copy || '');
    });
  });

  const copyImageBtn = document.getElementById('copyProductImageBtn');
  const zoomBtn = document.getElementById('modalZoomBtn');
  if (zoomBtn) {
    zoomBtn.addEventListener('click', () => openImageZoom(imgVariant.image_url, group.model, group));
  }

  if (copyImageBtn) {
    copyImageBtn.addEventListener('click', event => {
      event.stopPropagation();
      playUISound('lantern');
      copyProductImage(group);
    });
  }

  const copyTextBtn = document.getElementById('copyProductTextBtn');
  if (copyTextBtn) {
    copyTextBtn.addEventListener('click', event => {
      event.stopPropagation();
      playUISound('lantern');
      copyProductText(group);
    });
  }

  els.modal.showModal();
}

function render() {
  const q = normalizeText(els.search.value);

  const filtered = PRODUCTS.filter(p => {
    const matchesCat = activeCat === 'Tất cả' || p.category === activeCat;
    const matchesQ = matchesSearch(p, q);
    const matchesStock = !onlyInStock || Number(p.available || 0) > 0;
    const price = Number(p.price);
    const hasPrice = Number.isFinite(price) && price > 0;
    const matchesMinPrice = minPrice === null || (hasPrice && price >= minPrice);
    const matchesMaxPrice = maxPrice === null || (hasPrice && price <= maxPrice);

    return matchesCat && matchesQ && matchesStock && matchesMinPrice && matchesMaxPrice;
  });

  const groups = groupByModel(filtered);

  if (sortStockOrder === 'asc' || sortStockOrder === 'desc') {
    groups.sort((a, b) => {
      const stockA = getGroupAvailable(a.variants);
      const stockB = getGroupAvailable(b.variants);

      return sortStockOrder === 'asc' ? stockA - stockB : stockB - stockA;
    });
  } else if (sortStockOrder === 'price-asc' || sortStockOrder === 'price-desc') {
    groups.sort((a, b) => {
      const priceA = Number(getGroupPrice(a.variants) || 0);
      const priceB = Number(getGroupPrice(b.variants) || 0);

      return sortStockOrder === 'price-asc' ? priceA - priceB : priceB - priceA;
    });
  } else {
    groups.sort((a, b) => a.model.localeCompare(b.model, 'vi'));
  }

  els.grid.innerHTML = '';
  els.empty.style.display = groups.length ? 'none' : 'block';

  const totalAvail = filtered.reduce((sum, p) => {
    return sum + Number(p.available || 0);
  }, 0);

  els.summaryText.textContent = `${groups.length} mẫu xe · ${filtered.length} biến thể màu`;
  els.summaryStock.textContent = `${totalAvail.toLocaleString('vi-VN')} chiếc sẵn sàng`;

  for (const g of groups) {
    const card = document.createElement('div');
    card.className = 'card';

    const imgVariant = getGroupImage(g.variants);
    const groupPrice = getGroupPrice(g.variants);
    const colorRows = renderColorRows(g.variants);

    card.innerHTML = `
      <div class="card-top">
        ${
          imgVariant && imgVariant.image_url
            ? `<img class="card-img" src="${escapeHTML(imgVariant.image_url)}" alt="${escapeHTML(g.model)}">`
            : ''
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

      <div class="price-row">
        <span>${priceLabel}</span>
        <span class="price">${escapeHTML(fmtPrice(groupPrice))}</span>
      </div>
    `;

    card.addEventListener('click', () => {
      openProductModal(g);
    });

    els.grid.appendChild(card);
  }
}

function buildPills() {
  const categories = PRODUCTS
    .map(p => p.category)
    .filter(c => {
      const category = normalizeText(c);
      return category.startsWith('xe đạp') || category.startsWith('phụ tùng');
    });

  const cats = [
    'Tất cả',
    ...Array.from(new Set(categories)).sort((a, b) => a.localeCompare(b, 'vi'))
  ];

  els.pills.innerHTML = cats.map(c => {
    return `
      <div class="pill ${c === activeCat ? 'active' : ''}" data-cat="${escapeHTML(c)}">
        ${escapeHTML(c)}
      </div>
    `;
  }).join('');

  els.pills.querySelectorAll('.pill').forEach(el => {
    el.addEventListener('click', () => {
      playUISound('click');
      activeCat = el.dataset.cat;

      els.pills.querySelectorAll('.pill').forEach(p => {
        p.classList.remove('active');
      });

      el.classList.add('active');

      render();
    });
  });
}

async function load(includeReorderSuggestions = true) {
  try {
    const res = await fetch(`/api/products/${priceType}`, {
      cache: 'no-store'
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    if (priceType === 'retail' && res.headers.get('X-Retail-Prices-Visible') !== '1') {
      window.location.reload();
      return;
    }

    const data = await res.json();

    PRODUCTS = data.map(prepareProduct);

    buildPills();
    render();
    if (includeReorderSuggestions) loadReorderSuggestions();
  } catch (error) {
    console.error('Không tải được dữ liệu sản phẩm:', error);
    els.grid.innerHTML = '';
    els.empty.style.display = 'block';
    els.empty.textContent = 'Không tải được dữ liệu sản phẩm.';
  }
}

if (els.search) {
  els.search.addEventListener('input', render);
}

if (els.onlyStock) {
  els.onlyStock.addEventListener('change', () => {
    playUISound('click');
    onlyInStock = els.onlyStock.checked;
    render();
  });
}

if (els.sortStock) {
  els.sortStock.addEventListener('change', () => {
    playUISound('click');
    sortStockOrder = els.sortStock.value;
    render();
  });
}

if (els.minPrice) {
  els.minPrice.addEventListener('input', () => {
    minPrice = readPriceFilter(els.minPrice);
    render();
  });
}

if (els.maxPrice) {
  els.maxPrice.addEventListener('input', () => {
    maxPrice = readPriceFilter(els.maxPrice);
    render();
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
          ? `<img src="${escapeHTML(item.image_url)}" alt="${escapeHTML(item.model)}">`
          : '<span aria-hidden="true">□</span>'}
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

async function loadReorderSuggestions() {
  const list = document.getElementById('reorderList');
  if (!list || reorderRefreshInFlight) return;
  reorderRefreshInFlight = true;

  try {
    const response = await fetch('/api/reorder-suggestions', { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
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
const catalogContentLayout = document.querySelector('.catalog-content-layout');
const reorderDesktopToggle = document.getElementById('reorderDesktopToggle');
const reorderMobileTrigger = document.getElementById('reorderMobileTrigger');
const reorderMobileClose = document.getElementById('reorderMobileClose');
const reorderBackdrop = document.getElementById('reorderBackdrop');
const reorderSearch = document.getElementById('reorderSearch');

function setReorderPanelOpen(open) {
  if (!reorderPanel || !reorderMobileTrigger) return;
  reorderPanel.classList.toggle('mobile-open', open);
  document.body.classList.toggle('reorder-sheet-open', open);
  reorderMobileTrigger.setAttribute('aria-expanded', open ? 'true' : 'false');
}

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
  if (event.key === 'Escape') setReorderPanelOpen(false);
});

if (reorderDesktopToggle && catalogContentLayout) {
  reorderDesktopToggle.addEventListener('click', () => {
    const collapsed = catalogContentLayout.classList.toggle('reorder-collapsed');
    reorderDesktopToggle.textContent = collapsed ? '‹' : '›';
    reorderDesktopToggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    reorderDesktopToggle.setAttribute('aria-label', collapsed ? 'Mở gợi ý nhập hàng' : 'Thu gọn gợi ý nhập hàng');
  });
}

setInterval(loadReorderSuggestions, 5 * 60 * 1000);
document.addEventListener('visibilitychange', () => {
  if (!document.hidden && Date.now() - reorderLastLoadedAt >= 5 * 60 * 1000) {
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

setInterval(() => load(false), 30000);
