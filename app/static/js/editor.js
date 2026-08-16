(()=>{
  const cfg = window.FILTER_CONFIG;
  const canvas = document.getElementById('editorCanvas');
  const ctx = canvas?.getContext('2d');
  if (!cfg || !canvas || !ctx) return;

  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const overlay = new Image();
  overlay.crossOrigin = 'anonymous';
  overlay.src = cfg.overlay;

  let photo = null;
  let submission = null;
  let scale = 1;
  let minScale = 1;
  let x = 0;
  let y = 0;
  let drag = false;
  let last = {x: 0, y: 0};

  const hint = document.getElementById('stageHint');
  const input = document.getElementById('photoInput');
  const zoom = document.getElementById('zoomRange');
  const zoomVal = document.getElementById('zoomValue');
  const choosePhoto = document.getElementById('choosePhoto');
  const finishPhoto = document.getElementById('finishPhoto');
  const changePhoto = document.getElementById('changePhoto');
  const centerPhoto = document.getElementById('centerPhoto');
  const makeAnother = document.getElementById('makeAnother');
  const downloadPhoto = document.getElementById('downloadPhoto');

  function event(type){
    fetch('/api/events', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
      body: JSON.stringify({type, filter_id: cfg.id})
    }).catch(()=>{});
  }

  function setStep(n){
    document.querySelectorAll('.control-step').forEach(el => el.classList.toggle('active', Number(el.dataset.step) === n));
    document.querySelectorAll('.progress-dots i').forEach((el, i) => el.classList.toggle('active', i < n));
    document.getElementById('stepLabel').textContent = `${n} de 3`;
  }

  function draw(){
    ctx.clearRect(0, 0, 1080, 1080);
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, 1080, 1080);
    if (photo) ctx.drawImage(photo, x, y, photo.naturalWidth * scale, photo.naturalHeight * scale);
    if (overlay.complete) ctx.drawImage(overlay, 0, 0, 1080, 1080);
  }

  function resetPosition(){
    if (!photo) return;
    minScale = Math.max(1080 / photo.naturalWidth, 1080 / photo.naturalHeight);
    scale = minScale;
    x = (1080 - photo.naturalWidth * scale) / 2;
    y = (1080 - photo.naturalHeight * scale) / 2;
    zoom.value = 100;
    zoomVal.textContent = '100%';
    draw();
  }

  function clamp(){
    if (!photo) return;
    const w = photo.naturalWidth * scale;
    const h = photo.naturalHeight * scale;
    x = Math.min(0, Math.max(1080 - w, x));
    y = Math.min(0, Math.max(1080 - h, y));
  }

  function pointer(e){
    const r = canvas.getBoundingClientRect();
    return {
      x: (e.clientX - r.left) * 1080 / r.width,
      y: (e.clientY - r.top) * 1080 / r.height,
    };
  }

  async function handleFile(file){
    if (!file) return;
    choosePhoto.textContent = 'Enviando...';
    choosePhoto.disabled = true;
    const fd = new FormData();
    fd.append('filter_id', cfg.id);
    fd.append('photo', file);

    try {
      event('upload_click');
      const res = await fetch('/api/upload', {method:'POST', headers:{'X-CSRFToken': csrf}, body: fd});
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Erro no envio');
      submission = data;
      photo = new Image();
      photo.onload = () => {
        hint.classList.add('hidden');
        resetPosition();
        setStep(2);
        choosePhoto.textContent = 'Escolher foto';
        choosePhoto.disabled = false;
      };
      photo.src = data.photo_url;
    } catch (err) {
      alert(err.message);
      choosePhoto.textContent = 'Escolher foto';
      choosePhoto.disabled = false;
    }
  }

  choosePhoto?.addEventListener('click', () => input.click());
  changePhoto?.addEventListener('click', () => input.click());
  input?.addEventListener('change', e => handleFile(e.target.files[0]));

  zoom?.addEventListener('input', () => {
    if (!photo) return;
    const old = scale;
    scale = minScale * (Number(zoom.value) / 100);
    const cx = 540, cy = 540;
    x = cx - (cx - x) * (scale / old);
    y = cy - (cy - y) * (scale / old);
    clamp();
    zoomVal.textContent = `${zoom.value}%`;
    draw();
  });

  centerPhoto?.addEventListener('click', resetPosition);

  canvas.addEventListener('pointerdown', e => {
    if (!photo) return;
    drag = true;
    canvas.setPointerCapture(e.pointerId);
    last = pointer(e);
  });

  canvas.addEventListener('pointermove', e => {
    if (!drag || !photo) return;
    const p = pointer(e);
    x += p.x - last.x;
    y += p.y - last.y;
    last = p;
    clamp();
    draw();
  });

  const stopDrag = () => drag = false;
  canvas.addEventListener('pointerup', stopDrag);
  canvas.addEventListener('pointercancel', stopDrag);
  canvas.addEventListener('pointerleave', stopDrag);

  finishPhoto?.addEventListener('click', async () => {
    if (!photo || !submission) return;
    finishPhoto.textContent = 'Finalizando...';
    finishPhoto.disabled = true;
    try {
      const res = await fetch(`/api/complete/${submission.submission_id}`, {
        method: 'POST',
        headers: {'Content-Type':'application/json', 'X-CSRFToken': csrf},
        body: JSON.stringify({
          token: submission.token,
          transform: {x, y, scale}
        })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Erro ao finalizar');
      downloadPhoto.href = data.download_url;
      setStep(3);
    } catch (e) {
      alert(e.message);
    } finally {
      finishPhoto.innerHTML = 'Finalizar foto <span>→</span>';
      finishPhoto.disabled = false;
    }
  });

  makeAnother?.addEventListener('click', () => {
    photo = null;
    submission = null;
    input.value = '';
    hint.classList.remove('hidden');
    setStep(1);
    draw();
  });

  overlay.onload = draw;
  draw();
})();
