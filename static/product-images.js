// A missing photo must not hide the product or pretend to be a recovered photo.
window.productImagePlaceholder = function () {
  return '<span class="product-image-missing" role="img" aria-label="Chưa có ảnh sản phẩm">' +
    '<svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">' +
    '<rect x="7" y="10" width="34" height="28" rx="4"/>' +
    '<circle cx="17" cy="19" r="3"/><path d="m9 34 11-10 7 6 6-5 7 9"/></svg>' +
    '<span>Chưa có ảnh</span></span>';
};

document.addEventListener('error', event => {
  const img = event.target;
  if (!(img instanceof HTMLImageElement) || !img.hasAttribute('data-product-image')) return;
  const holder = document.createElement('span');
  holder.innerHTML = window.productImagePlaceholder();
  img.replaceWith(holder.firstElementChild);
}, true);

document.addEventListener('change', event => {
  const input = event.target;
  if (!(input instanceof HTMLInputElement) || input.type !== 'file' || input.name !== 'image') return;
  input.setCustomValidity(input.files[0]?.size > 4 * 1024 * 1024
    ? 'Ảnh tối đa 4 MB. Vui lòng chọn ảnh nhỏ hơn.' : '');
  if (!input.validity.valid) input.reportValidity();
});
