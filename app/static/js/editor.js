(()=>{
  const cfg = window.FILTER_CONFIG;
  const filters = Array.isArray(window.FILTERS) ? window.FILTERS : [];
  const canvas = document.getElementById('editorCanvas');
  const ctx = canvas?.getContext('2d');
  if (!cfg || !canvas || !ctx) return;

  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const input = document.getElementById('photoInput');
  const hint = document.getElementById('stageHint');
  const controls = document.getElementById('liveControls');
  const doneState = document.getElementById('doneState');
  const finishPhoto = document.getElementById('finishPhoto');
  const downloadPhoto = document.getElementById('downloadPhoto');
  const makeAnother = document.getElementById('makeAnother');
  const zoomIn = document.getElementById('zoomIn');
  const zoomOut = document.getElementById('zoomOut');
  const prev = document.getElementById('filterPrev');
  const next = document.getElementById('filterNext');
  const filterName = document.getElementById('filterName');

  let activeIndex = Math.max(0, filters.findIndex(f => Number(f.id) === Number(cfg.id)));
  let activeFilter = filters[activeIndex] || {id: cfg.id, name: cfg.name, overlay: cfg.overlay};
  let overlay = new Image();
  overlay.crossOrigin = 'anonymous';
  let photo = null;
  let submission = null;
  let scale = 1;
  let minScale = 1;
  let x = 0;
  let y = 0;
  let drag = false;
  let last = {x:0,y:0};
  let pointers = new Map();
  let pinchDistance = 0;

  async function readJson(res, fallbackMessage){
    const text=await res.text();
    let data={};
    try{ data=text ? JSON.parse(text) : {}; }
    catch(_err){
      // Railway/proxy and CSRF errors may arrive as HTML. Do not expose the
      // confusing "Unexpected token <" message to the visitor.
      const message = res.status === 502 || res.status === 503 || res.status === 504
        ? 'O servidor demorou para responder. Tente novamente em alguns segundos.'
        : fallbackMessage;
      throw new Error(message);
    }
    if(!res.ok) throw new Error(data.error||fallbackMessage);
    return data;
  }

  function event(type){
    fetch('/api/events', {method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf},body:JSON.stringify({type,filter_id:activeFilter.id})}).catch(()=>{});
  }

  function loadOverlay(){
    const nextOverlay = new Image();
    nextOverlay.crossOrigin = 'anonymous';
    nextOverlay.onload = () => { overlay = nextOverlay; draw(); };
    nextOverlay.src = activeFilter.overlay;
    if (filterName) filterName.textContent = activeFilter.name;
  }

  function draw(){
    ctx.clearRect(0,0,1080,1080);
    ctx.fillStyle='#fff';
    ctx.fillRect(0,0,1080,1080);
    if(photo) ctx.drawImage(photo,x,y,photo.naturalWidth*scale,photo.naturalHeight*scale);
    if(overlay.complete && overlay.naturalWidth) ctx.drawImage(overlay,0,0,1080,1080);
  }

  function resetPosition(){
    if(!photo) return;
    minScale=Math.max(1080/photo.naturalWidth,1080/photo.naturalHeight);
    scale=minScale;
    x=(1080-photo.naturalWidth*scale)/2;
    y=(1080-photo.naturalHeight*scale)/2;
    draw();
  }

  function clamp(){
    if(!photo) return;
    const w=photo.naturalWidth*scale,h=photo.naturalHeight*scale;
    x=Math.min(0,Math.max(1080-w,x));
    y=Math.min(0,Math.max(1080-h,y));
  }

  function pointerPos(e){
    const r=canvas.getBoundingClientRect();
    return {x:(e.clientX-r.left)*1080/r.width,y:(e.clientY-r.top)*1080/r.height};
  }

  function zoomBy(factor, center={x:540,y:540}){
    if(!photo) return;
    const old=scale;
    const max=minScale*3.2;
    scale=Math.max(minScale,Math.min(max,scale*factor));
    if(scale===old) return;
    x=center.x-(center.x-x)*(scale/old);
    y=center.y-(center.y-y)*(scale/old);
    clamp();
    draw();
  }

  function switchFilter(direction){
    if(filters.length<2) return;
    activeIndex=(activeIndex+direction+filters.length)%filters.length;
    activeFilter=filters[activeIndex];
    loadOverlay();
  }

  async function handleFile(file){
    if(!file) return;
    hint.innerHTML='<div class="upload-spinner"></div><b>Preparando sua foto...</b><small>Isso leva só alguns segundos</small>';
    hint.disabled=true;
    const fd=new FormData();
    fd.append('filter_id',activeFilter.id);
    fd.append('photo',file);
    try{
      event('upload_click');
      const res=await fetch('/api/upload',{method:'POST',headers:{'X-CSRFToken':csrf},body:fd});
      const data=await readJson(res,'Não foi possível enviar a foto. Tente novamente.');
      submission=data;
      photo=new Image();
      photo.onload=()=>{
        hint.hidden=true;
        controls.hidden=false;
        doneState.hidden=true;
        resetPosition();
      };
      photo.src=data.photo_url;
    }catch(err){
      alert(err.message);
      hint.disabled=false;
      hint.hidden=false;
      hint.innerHTML='<div>↑</div><b>Escolha uma foto para começar</b><small>JPG, PNG ou WEBP • até 15 MB</small>';
    }
  }

  hint?.addEventListener('click',()=>input.click());
  input?.addEventListener('change',e=>handleFile(e.target.files[0]));
  zoomIn?.addEventListener('click',()=>zoomBy(1.12));
  zoomOut?.addEventListener('click',()=>zoomBy(1/1.12));
  prev?.addEventListener('click',()=>switchFilter(-1));
  next?.addEventListener('click',()=>switchFilter(1));

  canvas.addEventListener('wheel',e=>{
    if(!photo) return;
    e.preventDefault();
    zoomBy(e.deltaY<0?1.08:1/1.08,pointerPos(e));
  },{passive:false});

  canvas.addEventListener('pointerdown',e=>{
    if(!photo) return;
    canvas.setPointerCapture(e.pointerId);
    pointers.set(e.pointerId,pointerPos(e));
    if(pointers.size===1){drag=true;last=pointerPos(e)}
    if(pointers.size===2){
      const [a,b]=[...pointers.values()];
      pinchDistance=Math.hypot(a.x-b.x,a.y-b.y);
      drag=false;
    }
  });

  canvas.addEventListener('pointermove',e=>{
    if(!photo||!pointers.has(e.pointerId)) return;
    const p=pointerPos(e);
    pointers.set(e.pointerId,p);
    if(pointers.size===2){
      const [a,b]=[...pointers.values()];
      const dist=Math.hypot(a.x-b.x,a.y-b.y);
      if(pinchDistance>0){
        const center={x:(a.x+b.x)/2,y:(a.y+b.y)/2};
        zoomBy(dist/pinchDistance,center);
      }
      pinchDistance=dist;
      return;
    }
    if(drag){
      x+=p.x-last.x;y+=p.y-last.y;last=p;clamp();draw();
    }
  });

  function releasePointer(e){
    pointers.delete(e.pointerId);
    if(pointers.size===0){drag=false;pinchDistance=0}
    else if(pointers.size===1){drag=true;last=[...pointers.values()][0]}
  }
  canvas.addEventListener('pointerup',releasePointer);
  canvas.addEventListener('pointercancel',releasePointer);

  finishPhoto?.addEventListener('click',async()=>{
    if(!photo||!submission) return;
    finishPhoto.textContent='Finalizando...';
    finishPhoto.disabled=true;
    try{
      const res=await fetch(`/api/complete/${submission.submission_id}`,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf},body:JSON.stringify({token:submission.token,filter_id:activeFilter.id,transform:{x,y,scale}})});
      const data=await readJson(res,'Não foi possível finalizar a imagem. Tente novamente.');
      downloadPhoto.href=data.download_url;
      controls.hidden=true;
      doneState.hidden=false;
    }catch(e){alert(e.message)}finally{
      finishPhoto.textContent='Finalizar foto';
      finishPhoto.disabled=false;
    }
  });

  makeAnother?.addEventListener('click',()=>{
    photo=null;submission=null;input.value='';
    controls.hidden=true;doneState.hidden=true;hint.hidden=false;hint.disabled=false;
    hint.innerHTML='<div>↑</div><b>Escolha uma foto para começar</b><small>JPG, PNG ou WEBP • até 15 MB</small>';
    draw();
  });

  loadOverlay();
  draw();
})();
