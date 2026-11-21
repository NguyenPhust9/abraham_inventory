/* One editor for the current page; no hidden form per product. */
(() => {
  if (window.lucide) window.lucide.createIcons();
  const menuButton = document.querySelector('.mobile-nav-toggle');
  const backdrop = document.querySelector('.nav-backdrop');
  function setNavigation(open) {
    document.body.classList.toggle('navigation-open', open);
    menuButton.setAttribute('aria-expanded', String(open));
    backdrop.hidden = !open;
    if (open) document.querySelector('.mobile-nav-close').focus();
    else menuButton.focus();
  }
  menuButton.addEventListener('click', () => setNavigation(menuButton.getAttribute('aria-expanded') !== 'true'));
  backdrop.addEventListener('click', () => setNavigation(false));
  document.querySelector('.mobile-nav-close').addEventListener('click', () => setNavigation(false));
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && document.body.classList.contains('navigation-open')) setNavigation(false);
  });
  document.querySelectorAll('.dismiss-flash').forEach(button => button.addEventListener('click', () => button.closest('.flash').remove()));
  document.querySelectorAll('form[data-confirm]').forEach(form => form.addEventListener('submit', event => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  }));
  function formatVndPrice(value) {
    const digits = String(value).replace(/\D/g, '').replace(/^0+(?=\d)/, '');
    return digits.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  }
  document.querySelectorAll('[data-vnd-price]').forEach(input => {
    input.value = formatVndPrice(input.value);
    input.addEventListener('beforeinput', event => {
      const caret = input.selectionStart;
      if (caret !== input.selectionEnd) return;
      // Skip a grouping dot so Backspace/Delete still removes a digit.
      if (event.inputType === 'deleteContentBackward' && input.value[caret - 1] === '.') {
        input.setSelectionRange(caret - 1, caret - 1);
      } else if (event.inputType === 'deleteContentForward' && input.value[caret] === '.') {
        input.setSelectionRange(caret + 1, caret + 1);
      }
    });
    input.addEventListener('input', () => {
      const digitsBeforeCaret = input.value.slice(0, input.selectionStart).replace(/\D/g, '').length;
      const formatted = formatVndPrice(input.value);
      if (input.value === formatted) return;
      input.value = formatted;
      let caret = 0;
      let digits = 0;
      while (caret < formatted.length && digits < digitsBeforeCaret) {
        if (formatted[caret] !== '.') digits++;
        caret++;
      }
      input.setSelectionRange(caret, caret);
    });
  });
  if (location.hash === '#khuyen-mai' && !document.getElementById('khuyen-mai')) {
    location.replace('/admin?section=promotions#khuyen-mai');
    return;
  }
  const data = document.getElementById('editorProducts');
  if (!data) return;
  const products = new Map(JSON.parse(data.textContent).map(product => [String(product.id), product]));
  const dialog = document.getElementById('productEditor');
  const form = document.getElementById('productEditForm');
  const deleteImage = document.getElementById('deleteImageForm');
  const preview = document.getElementById('editorImage');
  const saveImage = document.getElementById('saveImageOnly');
  let trigger;
  document.getElementById('productTableBody').addEventListener('click', event => {
    const button = event.target.closest('[data-edit-product]');
    if (!button) return;
    const product = products.get(button.dataset.editProduct);
    if (!product) return;
    trigger = button;
    form.reset();
    for (const name of ['code', 'model', 'color', 'category', 'unit', 'stock', 'reserved', 'price', 'retail_price']) {
      const input = form.elements.namedItem(name);
      const value = product[name];
      input.value = input.hasAttribute('data-vnd-price')
        ? (value == null ? '' : formatVndPrice(Math.round(value)))
        : (value ?? '');
    }
    form.elements.namedItem('image').setCustomValidity('');
    form.action = product.edit_url;
    saveImage.formAction = product.image_url_save;
    deleteImage.action = product.image_url_delete;
    deleteImage.hidden = !product.image_url;
    document.getElementById('editorDescription').textContent = 'Mã hàng ' + product.code;
    document.getElementById('editorModel').textContent = product.model;
    document.getElementById('editorCode').textContent = product.color || 'Chưa có màu';
    preview.replaceChildren();
    if (product.image_url) {
      const img = document.createElement('img');
      img.src = product.image_url;
      img.alt = product.model;
      img.setAttribute('data-product-image', '');
      preview.appendChild(img);
    } else {
      preview.innerHTML = window.productImagePlaceholder();
    }
    dialog.showModal();
  });
  document.querySelectorAll('[data-close-editor]').forEach(button => button.addEventListener('click', () => dialog.close()));
  dialog.addEventListener('close', () => trigger?.focus({preventScroll:true}));
  dialog.addEventListener('click', event => {
    const rect = dialog.getBoundingClientRect();
    if (event.target === dialog && (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom)) dialog.close();
  });
})();
