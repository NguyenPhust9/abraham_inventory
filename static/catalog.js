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
let activeCat = 'Tất cả';
let onlyInStock = false;
let sortPriceOrder = '';

const els = {
  search: document.getElementById('search'),
  pills: document.getElementById('catpills'),
  grid: document.getElementById('grid'),
  empty: document.getElementById('emptyState'),
  summaryText: document.getElementById('summaryText'),
  summaryStock: document.getElementById('summaryStock'),
  onlyStock: document.getElementById('onlyStock'),
  sortPrice: document.getElementById('sortPrice'),
  modal: document.getElementById('productModal'),
  modalTitle: document.getElementById('modalTitle'),
  modalSub: document.getElementById('modalSub'),
  modalBody: document.getElementById('modalBody'),
  modalClose: document.getElementById('modalClose'),
};

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

function getGroupImage(variants) {
  return variants.find(v => v.image_url) || variants[0] || null;
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
  const totalAvailable = group.variants.reduce((sum, v) => {
    return sum + Number(v.available || 0);
  }, 0);

  const lines = [
    `${group.model}${group.category ? ' - ' + group.category : ''}`,
    `Tổng còn: ${totalAvailable} chiếc`,
    ''
  ];

  sortVariants(group.variants).forEach(v => {
    const colorName = v.color || 'Chưa có màu';
    lines.push(`- ${colorName}: còn ${v.available} | Mã: ${v.code}`);
  });

  const price = fmtPrice(getGroupPrice(group.variants));
  lines.push('');
  lines.push(`Giá bán: ${price}`);

  return lines.join('\n');
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

function openProductModal(group) {
  const variants = sortVariants(group.variants);
  const imgVariant = getGroupImage(variants);
  const groupPrice = getGroupPrice(variants);

  const totalStock = variants.reduce((sum, v) => sum + Number(v.stock || 0), 0);
  const totalReserved = variants.reduce((sum, v) => sum + Number(v.reserved || 0), 0);
  const totalAvailable = variants.reduce((sum, v) => sum + Number(v.available || 0), 0);

  els.modalTitle.textContent = group.model;
  els.modalSub.textContent = group.category || 'Chưa phân loại';

  const imageHTML = imgVariant && imgVariant.image_url
    ? `<img class="modal-image" src="${escapeHTML(imgVariant.image_url)}" alt="${escapeHTML(group.model)}">`
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
          <div class="modal-stat-label">Giá bán</div>
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

      <button type="button" class="copy-all-btn" id="copyProductSummary">
        Copy danh sách gửi khách
      </button>

      <div class="modal-note">
        Gợi ý: dùng nút copy để gửi nhanh mã hàng hoặc danh sách màu còn hàng cho khách qua Zalo/Facebook.
      </div>
    </div>
  `;

  els.modalBody.querySelectorAll('.copy-btn').forEach(btn => {
    btn.addEventListener('click', event => {
      event.stopPropagation();
      copyText(btn.dataset.copy || '');
    });
  });

  const copyAllBtn = document.getElementById('copyProductSummary');
  if (copyAllBtn) {
    copyAllBtn.addEventListener('click', event => {
      event.stopPropagation();
      copyText(buildShareText(group));
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

    return matchesCat && matchesQ && matchesStock;
  });

  const groups = groupByModel(filtered);

  if (sortPriceOrder === 'asc' || sortPriceOrder === 'desc') {
    groups.sort((a, b) => {
      const priceA = getGroupPrice(a.variants);
      const priceB = getGroupPrice(b.variants);

      // Sản phẩm chưa có giá ("Liên hệ") luôn xếp cuối, bất kể chiều sắp xếp
      if (priceA === null && priceB === null) return 0;
      if (priceA === null) return 1;
      if (priceB === null) return -1;

      return sortPriceOrder === 'asc' ? priceA - priceB : priceB - priceA;
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
        <span>Giá bán</span>
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
    .filter(c => c && String(c).trim());

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
      activeCat = el.dataset.cat;

      els.pills.querySelectorAll('.pill').forEach(p => {
        p.classList.remove('active');
      });

      el.classList.add('active');

      render();
    });
  });
}

async function load() {
  try {
    const res = await fetch('/api/products', {
      cache: 'no-store'
    });

    const data = await res.json();

    PRODUCTS = data.map(prepareProduct);

    buildPills();
    render();
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
    onlyInStock = els.onlyStock.checked;
    render();
  });
}

if (els.sortPrice) {
  els.sortPrice.addEventListener('change', () => {
    sortPriceOrder = els.sortPrice.value;
    render();
  });
}

if (els.modalClose) {
  els.modalClose.addEventListener('click', () => {
    els.modal.close();
  });
}

if (els.modal) {
  els.modal.addEventListener('click', event => {
    if (event.target === els.modal) {
      els.modal.close();
    }
  });
}

document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && els.modal && els.modal.open) {
    els.modal.close();
  }
});

load();

setInterval(load, 30000);