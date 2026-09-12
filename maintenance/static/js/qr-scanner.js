/* QR decoding: locally hosted jsQR 1.4.0 (Apache-2.0; see vendor license). */
(() => {
  'use strict';
  const dialog = document.getElementById('qr-scanner');
  const video = document.getElementById('qr-scanner-video');
  const status = document.getElementById('qr-scanner-status');
  const retry = document.getElementById('qr-scanner-retry');
  const canvas = document.createElement('canvas');
  const context = canvas.getContext('2d', { willReadFrequently: true });
  let stream;
  let timer;
  let generation = 0;
  let decoder;

  function loadDecoder() {
    if (!decoder) {
      decoder = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = dialog.dataset.decoderUrl;
        script.onload = resolve;
        script.onerror = () => {
          script.remove();
          decoder = null;
          reject(new Error('Decoder unavailable'));
        };
        document.head.appendChild(script);
      });
    }
    return decoder;
  }

  function stop() {
    generation++;
    clearTimeout(timer);
    if (stream) stream.getTracks().forEach(track => track.stop());
    stream = null;
    video.srcObject = null;
  }

  function pianoPath(value) {
    try {
      const url = new URL(value, window.location.origin);
      if (url.origin !== window.location.origin || url.username || url.password) return null;
      if (/^\/maintenance_request\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\/$/i.test(url.pathname)
          || /^\/pianos\/[1-9]\d*\/$/.test(url.pathname)) return url.pathname;
    } catch (_) { /* Non-URL codes are not piano links. */ }
    return null;
  }

  function scan(session) {
    if (session !== generation || !dialog.open) return;
    try {
      if (video.readyState >= 2 && video.videoWidth && video.videoHeight) {
        const scale = Math.min(1, 800 / video.videoWidth);
        canvas.width = Math.round(video.videoWidth * scale);
        canvas.height = Math.round(video.videoHeight * scale);
        context.drawImage(video, 0, 0, canvas.width, canvas.height);
        const pixels = context.getImageData(0, 0, canvas.width, canvas.height);
        const code = window.jsQR(pixels.data, pixels.width, pixels.height);
        if (code) {
          const path = pianoPath(code.data);
          if (path) {
            stop();
            status.textContent = 'Opening piano…';
            window.location.assign(path);
            return;
          }
          status.textContent = 'This is not a piano QR code for this app. Point the camera at another code.';
        }
      }
      timer = setTimeout(() => scan(session), 150);
    } catch (_) {
      stop();
      status.textContent = 'The camera preview could not be read. Please try again.';
      retry.hidden = false;
    }
  }

  async function start() {
    stop();
    const session = generation;
    retry.hidden = true;
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      status.textContent = 'Camera scanning needs a secure (HTTPS) connection and a browser with camera support.';
      return;
    }
    status.textContent = 'Allow camera access, then point it at the piano’s QR code.';
    try {
      const camera = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 720 } }
      });
      if (session !== generation || !dialog.open) {
        camera.getTracks().forEach(track => track.stop());
        return;
      }
      stream = camera;
      video.srcObject = camera;
      await video.play();
      await loadDecoder();
      if (session !== generation || !dialog.open) return;
      status.textContent = 'Point your camera at the piano’s QR code.';
      scan(session);
    } catch (error) {
      if (session !== generation || !dialog.open) return;
      stop();
      status.textContent = error.name === 'NotAllowedError'
        ? 'Camera access was blocked. Allow camera access in your browser settings, then try again.'
        : error.name === 'NotFoundError'
          ? 'No camera was found on this device.'
          : 'Could not start the scanner. Close other apps using the camera and try again.';
      retry.hidden = false;
    }
  }

  document.getElementById('scan-code').addEventListener('click', () => {
    dialog.showModal();
    start();
  });
  retry.addEventListener('click', start);
  document.getElementById('qr-scanner-close').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', stop);
  dialog.addEventListener('cancel', stop);
  window.addEventListener('pagehide', stop);
  document.addEventListener('visibilitychange', () => {
    if (document.hidden && dialog.open) {
      stop();
      dialog.close();
    }
  });
})();
