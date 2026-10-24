(() => {
  const video = document.querySelector('.hero-banner-video');
  const button = document.querySelector('.hero-sound-toggle');
  if (!video || !button) return;
  if (window.matchMedia('(max-width: 760px)').matches) {
    video.pause();
    video.removeAttribute('autoplay');
    return;
  }
  video.preload = 'auto';

  function updateButton() {
    const needsSound = video.muted || video.paused;
    const label = needsSound ? 'B\u1eadt \u00e2m thanh' : 'T\u1eaft ti\u1ebfng';
    button.textContent = label;
    button.setAttribute('aria-label', label);
    button.setAttribute('aria-pressed', String(video.muted));
  }

  button.addEventListener('click', () => {
    video.muted = !(video.muted || video.paused);
    video.play().catch(updateButton);
    updateButton();
  });
  video.addEventListener('volumechange', updateButton);
  video.addEventListener('play', updateButton);
  video.addEventListener('pause', updateButton);

  // Set these before the first play attempt, including in embedded browsers.
  video.defaultMuted = true;
  video.muted = true;
  video.autoplay = true;
  video.playsInline = true;
  video.setAttribute('muted', '');
  video.setAttribute('playsinline', '');
  video.setAttribute('webkit-playsinline', '');

  let playPending = false;
  function resumeVideo() {
    if (!video.paused || document.hidden || playPending) return;
    playPending = true;
    video.play().catch(updateButton).finally(() => {
      playPending = false;
      updateButton();
    });
  }
  ['loadedmetadata', 'loadeddata', 'canplay'].forEach(event => {
    video.addEventListener(event, resumeVideo);
  });
  window.addEventListener('pageshow', resumeVideo);
  document.addEventListener('visibilitychange', resumeVideo);
  // If autoplay is restricted, a gesture anywhere on the page can start it.
  ['touchstart', 'touchend', 'pointerdown', 'click'].forEach(event => {
    document.addEventListener(event, resumeVideo, { passive: true });
  });
  resumeVideo();
  updateButton();
})();
