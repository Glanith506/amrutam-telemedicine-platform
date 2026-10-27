'use strict';
// Same-origin API, no external assets and no browser-persisted credentials.
const $ = (selector, parent = document) => parent.querySelector(selector);
const icons = {
  home:'<path d="m3 10 9-7 9 7v10H3Z"/><path d="M9 20v-7h6v7"/>',
  doctors:'<path d="M6 3v6a6 6 0 0 0 12 0V3M4 3h4m8 0h4M12 15v3a3 3 0 0 0 6 0v-2"/><circle cx="18" cy="13" r="3"/>',
  calendar:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 11h18m-13 4h2m4 0h2"/>',
  shield:'<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6Z"/><path d="m8 12 3 3 5-6"/>',
  arrow:'<path d="M4 12h16m-6-6 6 6-6 6"/>',
  video:'<rect x="3" y="6" width="12" height="12" rx="2"/><path d="m15 10 6-3v10l-6-3"/>',
  leaf:'<path d="M20 4C10 2 3 8 5 15c6 7 15-1 15-11Z"/><path d="m4 21 11-12"/>',
  list:'<path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01"/>',
  plus:'<path d="M12 5v14M5 12h14"/>',
  user:'<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
  refresh:'<path d="M20 7v5h-5M4 17v-5h5"/><path d="M6 6a8 8 0 0 1 14 6M4 12a8 8 0 0 0 14 6"/>',
  check:'<path d="m5 12 4 4L19 6"/>',
  lock:'<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2"/>',
};
const icon = name => `<svg aria-hidden="true" viewBox="0 0 24 24">${icons[name] || icons.leaf}</svg>`;
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = paise => new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:2}).format(paise/100);
const dateTime = value => value ? new Date(value).toLocaleString(undefined,{day:'numeric',month:'short',year:'numeric',hour:'numeric',minute:'2-digit'}) : 'Time unavailable';
const initials = text => String(text || 'A').split(/[\s@._-]+/).filter(Boolean).slice(0,2).map(s=>s[0]).join('').toUpperCase();
const shortId = text => String(text || '').slice(0,8);
const modal = $('#modal');
const state = {token:null,user:null,page:'overview',doctors:[],consultations:[],directoryOffset:0,consultationOffset:0,auditOffset:0,search:{specialty:'',fee:''},renderId:0,afterLogin:null};
let modalReturnFocus = null;
let modalRevision = 0;

class ApiError extends Error { constructor(message,status){super(message);this.status=status;} }
async function api(path,{method='GET',body,auth=true,retry=true}={}) {
  const headers = {'Accept':'application/json'};
  if(body !== undefined) headers['Content-Type']='application/json';
  if(auth && state.token) headers.Authorization=`Bearer ${state.token}`;
  if(!['GET','HEAD'].includes(method) && path!=='/auth/login') headers['Idempotency-Key']=crypto.randomUUID();
  const requestToken=state.token;
  const options={method,headers,body:body===undefined?undefined:JSON.stringify(body),cache:'no-store',credentials:'omit'};
  const attempts = retry && path!=='/auth/login' ? 2 : 1;
  for(let attempt=0;attempt<attempts;attempt++) {
    let response;
    try { response=await fetch(path,{...options,signal:AbortSignal.timeout(20000)}); }
    catch(error) {
      if(attempt+1<attempts){await new Promise(resolve=>setTimeout(resolve,600));continue;}
      throw new ApiError('Cannot reach the server. Check Docker is running, then try again.',0);
    }
    if([502,503,504].includes(response.status) && attempt+1<attempts){await new Promise(resolve=>setTimeout(resolve,600));continue;}
    const data=await response.json().catch(()=>({}));
    if(!response.ok) {
      let message=data.detail || 'The request could not be completed.';
      if(Array.isArray(message)) message=message.map(x=>`${x.loc?.filter(y=>y!=='body').join(' · ') || 'Input'}: ${x.msg}`).join('; ');
      if(response.status===429) message='Too many requests. Please wait a minute before trying again.';
      // MFA code rejection must not invalidate the login session.
      if(response.status===401 && auth && requestToken && state.token===requestToken
         && !(path==='/auth/mfa/confirm' && data.detail==='Invalid or replayed MFA code')) {
        state.token=null;state.user=null;state.consultations=[];closeModal();render();
        message='Your session has expired. Please sign in again.';
      }
      throw new ApiError(String(message),response.status);
    }
    return data;
  }
}
function toast(message,error=false) {
  const node=document.createElement('div');node.className=`toast${error?' error-toast':''}`;
  const messageNode=document.createElement('span');messageNode.textContent=message;node.append(messageNode);
  const close=document.createElement('button');close.type='button';close.setAttribute('aria-label','Dismiss notification');close.textContent='×';close.onclick=()=>node.remove();node.append(close);
  $('#toasts').append(node);setTimeout(()=>node.remove(),7500);
}
function openModal(title,content) {
  modalRevision++;
  modalReturnFocus=document.activeElement;
  $('#modal-body').innerHTML=`<div class="modal-head"><h2 id="modal-title">${esc(title)}</h2><button class="close-modal" type="button" aria-label="Close dialog">×</button></div><div class="modal-inner">${content}</div>`;
  $('.close-modal',modal).onclick=closeModal;
  if(!modal.open) modal.showModal();
}
function closeModal(){modalRevision++;if(modal.open)modal.close();$('#modal-body').replaceChildren();modalReturnFocus?.focus?.();}
modal.addEventListener('cancel',event=>{event.preventDefault();closeModal();});
modal.addEventListener('click',event=>{if(event.target===modal){const r=modal.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)closeModal();}});
function errorBox(container,error){let box=$('.error',container);if(!box){box=document.createElement('div');box.className='error';box.setAttribute('role','alert');container.prepend(box);}box.textContent=error.message || String(error);}
async function formAction(form,callback) {
  $('.error',form)?.remove();const buttons=[...form.querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);
  try{await callback(new FormData(form));}catch(error){errorBox(form,error);}finally{buttons.forEach(b=>b.disabled=false);}
}
const empty=(title,description,action='')=>`<div class="empty"><div class="empty-icon">${icon('leaf')}</div><h3>${esc(title)}</h3><p>${esc(description)}</p>${action}</div>`;
const loading=()=>'<div class="doctor-grid"><div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div></div>';
const btn=(text,action,style='')=>`<button class="btn ${style}" type="button" data-action="${action}">${text}</button>`;
function pageHeading(title,description,action='') {
  return `<div class="page-title"><div><p class="eyebrow">THE AMRUTAM WAY</p><h1>${esc(title)}</h1><p class="subtext">${esc(description)}</p></div>${action || `<span class="date-pill">${icon('calendar')}${esc(new Date().toLocaleDateString(undefined,{weekday:'short',day:'numeric',month:'short',year:'numeric'}))}</span>`}</div>`;
}
function stat(label,value,detail,ico){return `<div class="stat"><div class="stat-icon">${icon(ico)}</div><div><div class="stat-label">${esc(label)}</div><div class="stat-value">${esc(value)}</div><div class="stat-foot">${esc(detail)}</div></div></div>`;}
function nav() {
  const role=state.user?.role;
  const items = [['overview','home','Overview']];
  if (!role || role === 'patient') items.push(['doctors','doctors','Find a doctor']);
  if (role === 'patient') items.push(['appointments','calendar','My appointments']);
  if (role === 'doctor') {
    items.push(['appointments','calendar','Consultations']);
    items.push(['availability','plus','Availability']);
  }
  if (role === 'admin') items.push(['admin','list','Admin workspace']);
  if (state.user) items.push(['settings','shield','Account & security']);
  $('#navigation').innerHTML=items.map(([id,ico,name])=>`<button type="button" class="nav-item${state.page===id?' active':''}" data-page="${id}" ${state.page===id?'aria-current="page"':''}>${icon(ico)}${name}</button>`).join('');
  $('#navigation').querySelectorAll('[data-page]').forEach(b=>b.onclick=()=>navigate(b.dataset.page));
  $('#page-label').textContent=items.find(x=>x[0]===state.page)?.[2] || 'Overview';
  $('#account-label').textContent=state.user ? state.user.name || state.user.email.split('@')[0] : 'Sign in';
  $('#account-button').classList.toggle('signed-in',Boolean(state.user));
  $('#register-button').classList.toggle('hidden',Boolean(state.user));
  $('#top-avatar').textContent=initials(state.user?.name || state.user?.email || 'Amrutam');
}
function navigate(page){state.page=page;render();window.scrollTo({top:0,behavior:'auto'});}
function bindActions(parent=document) {
  parent.querySelectorAll('[data-action]').forEach(b=>b.onclick=()=>{
    const a=b.dataset.action;
    if(a==='public-home')navigate('overview');
    else if(a==='public-how'){
      state.page='overview';
      render().then(()=>document.getElementById('public-how-it-works')?.scrollIntoView({behavior:'smooth'}));
    }
    else if(a==='doctors')navigate('doctors');
    else if(a==='appointments')navigate('appointments');
    else if(a==='signin')authModal('login');
    else if(a==='signup')authModal('register');
    else if(a==='settings')navigate('settings');
    else if(a==='refresh')render();
    else if(a==='availability')navigate('availability');
    else if(a==='logout')logout();
  });
}
function logout(){state.token=null;state.user=null;state.consultations=[];state.afterLogin=null;closeModal();state.page='overview';render();toast('You have signed out.');}
async function render() {
  const id=++state.renderId;nav();
  try {
    if(state.page==='overview')await overview(id);
    else if(state.page==='doctors')await directory(id);
    else if(state.page==='appointments')await appointments(id);
    else if(state.page==='settings')settingsPage();
    else if(state.page==='availability')await availability(id);
    else if(state.page==='admin')await adminPage(id);
  }catch(error){if(id===state.renderId){$('#main').innerHTML=pageHeading('Let’s try that again','We couldn’t load this page.')+empty('Something interrupted the connection',error.message,btn('Try again','refresh'));bindActions();}}
}
async function getDoctors(offset=0,filtered=false) {
  const q=new URLSearchParams({limit:'12',offset:String(offset)});
  if(filtered && state.search.specialty.trim())q.set('specialty',state.search.specialty.trim());
  if(filtered && state.search.fee!=='')q.set('max_fee_paise',String(Math.round(Number(state.search.fee)*100)));
  const rows=await api('/doctors?'+q,{auth:false});rows.forEach(d=>{const i=state.doctors.findIndex(x=>x.id===d.id);if(i<0)state.doctors.push(d);else state.doctors[i]=d;});return rows;
}
function doctorCard(d) {
  return `<article class="doctor-card"><div class="doctor-profile"><span class="avatar">${esc(initials(d.name))}</span><div><h3 class="doctor-name">${esc(d.name)}</h3><div class="specialty">${esc(d.specialty)}</div></div></div><div class="card-separator"><span class="fee"><span class="currency-medallion">₹</span>${esc(money(d.fee_paise))}<small>/ consultation</small></span></div><button class="btn full" type="button" data-doctor="${esc(d.id)}">View available times ${icon('arrow')}</button></article>`;
}
function guestStats() {
  return [
    ['calendar','Your appointments','Sign in to view your appointments and upcoming consultations.'],
    ['check','Completed consultations','Sign in to view your consultation history.'],
    ['user','Your account','Sign in or create an account to manage your care.']
  ].map(([ico,title,text])=>`<button class="guest-stat" type="button" data-action="signin"><span class="stat-icon">${icon(ico)}</span><span class="guest-stat-copy"><strong>${title}</strong>${title==='Your account'?'<span class="guest-account">Guest</span>':''}<span>${text}</span></span><span class="guest-chevron">›</span></button>`).join('');
}

function bindDoctors(parent=document){parent.querySelectorAll('[data-doctor]').forEach(b=>b.onclick=()=>slotsModal(state.doctors.find(d=>d.id===b.dataset.doctor)));}
async function overview(id) {
  if (state.user?.role === 'admin') { await adminPage(id); return; }
  if (state.user?.role === 'doctor') { await doctorOverview(id); return; }

  const person=state.user?.name || state.user?.email.split('@')[0];
  $('#main').innerHTML=pageHeading(person?`Welcome back, ${person}.`:'A healthier you starts here.','A little clarity, a little connection, and care that fits your day.')+
    `<section class="hero"><div class="hero-copy"><p class="eyebrow">MAKE SPACE FOR YOUR WELLBEING</p><h2>Good care.<br>A simple beginning.</h2><p>Connect with a doctor, choose a time that works for you, and keep your care in one place.</p>${btn(`Find a doctor ${icon('arrow')}`,'doctors')}</div><div class="hero-art" aria-hidden="true"><img class="botanical-art" src="/assets/botanical-hero.png" alt="" width="1536" height="1024"><div class="hero-stamp">${icon('leaf')} A MORE THOUGHTFUL APPROACH</div></div></section><div id="overview-stats" class="stats">${guestStats()}</div><div class="section-heading directory-heading"><div><h2>Find your care connection</h2><p class="subtext">Browse the doctors in your consultation directory.</p></div><form id="overview-search" class="overview-filters"><label class="search-control"><span aria-hidden="true">⌕</span><input name="specialty" aria-label="Search by specialty" maxlength="100" placeholder="Search by specialty (e.g. Ayurveda)"></label><label class="search-control fee-control"><span aria-hidden="true">₹</span><input name="fee" aria-label="Maximum consultation fee in rupees" type="number" min="0" step="0.01" placeholder="Maximum fee"></label><button class="filter-submit" type="submit" aria-label="Search doctors">${icon('arrow')}</button></form></div><p class="subtext" style="margin-bottom:14px;">Sample profiles for demonstration only.</p><div id="overview-doctors">${loading()}</div><div class="page-note">${icon('lock')}Your prescription is accessible only to you and your consulting doctor.</div>`;
  bindActions();
  $('#overview-search').onsubmit=event=>{event.preventDefault();const f=new FormData(event.target);state.search={specialty:String(f.get('specialty')||''),fee:String(f.get('fee')||'')};state.directoryOffset=0;navigate('doctors');};
  const directoryPromise=getDoctors().then(rows=>{if(id!==state.renderId)return;$('#overview-doctors').innerHTML=rows.length?`<div class="doctor-grid">${rows.slice(0,3).map(doctorCard).join('')}</div>`:empty('Your doctor directory is getting started','An administrator can add doctors after they have registered and enabled MFA.');bindDoctors();});
  const user=state.user;
  const accountPromise=user ? api('/consultations?limit=100&offset=0').then(rows=>{if(id!==state.renderId)return;state.consultations=rows;const active=rows.filter(c=>['booked','in_progress'].includes(c.status)).length;$('#overview-stats').innerHTML=stat('Active appointments',active,rows.length===100?'Within latest 100 consultations':'Your current care plans','calendar')+stat('Completed consultations',rows.filter(c=>c.status==='completed').length,rows.length===100?'Within latest 100 consultations':'Care, one step at a time','check')+stat('Your account',user.role[0].toUpperCase()+user.role.slice(1),user.mfa_enabled?'MFA protection enabled':'Visit security to enable MFA','shield');}) : Promise.resolve();
  await Promise.all([directoryPromise,accountPromise]);
}
async function doctorOverview(id) {
  const user = state.user;
  $('#main').innerHTML = pageHeading(`Welcome back, ${user.name || user.email.split('@')[0]}.`, 'Manage your schedule and assigned consultations.') +
    `<div class="stats" id="doctor-overview-stats">${loading()}</div>
    <div class="two-cols">
      <section class="panel"><h2>Your consultation schedule</h2><p class="subtext">View bookings, start consultations and issue prescriptions.</p>${btn('View consultations','appointments')}</section>
      <section class="panel"><h2>Make time for your patients</h2><p class="subtext">Publish future consultation slots so patients can book with you.</p>${btn('Manage availability','availability')}</section>
    </div>`;
  bindActions();
  const rows = await api('/consultations?limit=100&offset=0');
  if (id !== state.renderId) return;
  state.consultations = rows;
  const active = rows.filter(c => ['booked','in_progress'].includes(c.status)).length;
  $('#doctor-overview-stats').innerHTML =
    stat('Active consultations', active, 'Within latest 100 consultations','calendar') +
    stat('Completed consultations', rows.filter(c => c.status === 'completed').length, 'Within latest 100 consultations','check') +
    stat('Your account','Doctor',user.mfa_enabled ? 'MFA protection enabled' : 'Enable MFA in account security','shield');
}

async function directory(id) {
  $('#main').innerHTML=pageHeading('Find your care connection.','Browse specialties and choose a consultation that fits your needs.')+
    `<form id="doctor-filter" class="filters"><input aria-label="Filter by specialty" name="specialty" placeholder="Specialty, e.g. Ayurveda" maxlength="100" value="${esc(state.search.specialty)}"><input aria-label="Maximum fee in rupees" name="fee" type="number" min="0" step="0.01" placeholder="Max fee ₹" value="${esc(state.search.fee)}"><button class="btn" type="submit">Apply filters ${icon('arrow')}</button></form><div id="directory-results">${loading()}</div><div id="directory-pages"></div><div class="page-note">${icon('calendar')}Available times are shown in your device’s timezone.</div>`;
  $('#doctor-filter').onsubmit=event=>{event.preventDefault();const f=new FormData(event.target);state.search={specialty:f.get('specialty'),fee:f.get('fee')};state.directoryOffset=0;render();};
  const rows=await getDoctors(state.directoryOffset,true);if(id!==state.renderId)return;
  $('#directory-results').innerHTML=rows.length?`<div class="doctor-grid">${rows.map(doctorCard).join('')}</div>`:empty('No doctors match these filters','Try another specialty or increase the maximum fee.');
  pagination($('#directory-pages'),state.directoryOffset,12,rows.length,offset=>{state.directoryOffset=offset;render();});bindDoctors();
}
function pagination(node,offset,limit,count,callback){node.innerHTML=`<div class="pagination"><button type="button" class="btn secondary" ${offset===0?'disabled':''} data-prev>← Previous</button><span>Page ${Math.floor(offset/limit)+1}</span><button type="button" class="btn secondary" ${count<limit?'disabled':''} data-next>Next →</button></div>`;$('[data-prev]',node).onclick=()=>callback(Math.max(0,offset-limit));$('[data-next]',node).onclick=()=>callback(offset+limit);}
async function slotsModal(doctor) {
  if(!doctor)return;
  openModal('Choose a time for your care',`<div class="subtext"><strong>${esc(doctor.name)}</strong> · ${esc(doctor.specialty)}<br>${esc(money(doctor.fee_paise))} per consultation · Times shown locally</div><div id="slot-results" class="loading-text">Finding available times…</div>`);
  const revision=modalRevision;
  let offset=0;let selected=null;
  async function load(){
    try{
      const rows=await api(`/doctors/${encodeURIComponent(doctor.id)}/slots?limit=20&offset=${offset}`,{auth:false});if(revision!==modalRevision||!modal.open||!$('#slot-results'))return;
      $('#slot-results').className='';
      if(!rows.length){$('#slot-results').innerHTML=empty('No open times on this page',offset?'Go back to see earlier times.':'This doctor has no available future slots. Please check another doctor or ask the doctor to publish availability.')+'<div id="slot-pages"></div>';pagination($('#slot-pages'),offset,20,0,next=>{offset=next;load();});return;}
      $('#slot-results').innerHTML=`<div class="slot-list">${rows.map(s=>`<button class="slot-button" type="button" data-slot="${esc(s.id)}">${esc(new Date(s.starts_at).toLocaleDateString(undefined,{weekday:'short',day:'numeric',month:'short'}))}<small>${esc(new Date(s.starts_at).toLocaleTimeString(undefined,{hour:'numeric',minute:'2-digit'}))} – ${esc(new Date(s.ends_at).toLocaleTimeString(undefined,{hour:'numeric',minute:'2-digit'}))}</small></button>`).join('')}</div><div id="slot-pages"></div><div class="notice">Booking reserves an appointment. No payment is collected through this demo.</div><form id="booking-form"><div id="booking-summary" class="subtext" style="margin:17px 0">Select a time to continue.</div><button class="btn full" type="submit" disabled id="confirm-booking">${state.user?'Confirm appointment':'Sign in to book'} ${icon('arrow')}</button></form>`;
      pagination($('#slot-pages'),offset,20,rows.length,next=>{selected=null;offset=next;load();});
      document.querySelectorAll('[data-slot]').forEach(b=>b.onclick=()=>{selected=rows.find(s=>s.id===b.dataset.slot);document.querySelectorAll('[data-slot]').forEach(x=>{x.classList.toggle('selected',x===b);x.setAttribute('aria-pressed',String(x===b));});$('#confirm-booking').disabled=false;$('#booking-summary').textContent=dateTime(selected.starts_at);});
      $('#booking-form').onsubmit=event=>{event.preventDefault();const form=event.target;if(!selected)return;
        if(!state.user){state.afterLogin=()=>slotsModal(doctor);authModal('login');return;}
        if(state.user.role!=='patient'){errorBox(form,new Error('Only a patient account can book an appointment. Sign in as a patient.'));return;}
        formAction(form,async()=>{await api('/consultations',{method:'POST',body:{slot_id:selected.id}});closeModal();toast('Your appointment is booked.');navigate('appointments');});};
    }catch(error){if(revision===modalRevision && $('#slot-results')){$('#slot-results').className='error';$('#slot-results').textContent=error.message;}}
  }
  await load();
}
function authModal(mode='login') {
  openModal(mode==='login'?'Welcome back.':'Your care starts here.',`<div class="auth-tabs"><button type="button" class="${mode==='login'?'active':''}" id="login-tab">Sign in</button><button type="button" class="${mode==='register'?'active':''}" id="register-tab">Create account</button></div><form id="auth-form">${mode==='register'?'<div class="field"><label for="auth-name">Your name</label><input id="auth-name" name="name" required maxlength="100" autocomplete="name" placeholder="How should we call you?"></div>':''}<div class="field"><label for="auth-email">Email address</label><input id="auth-email" name="email" type="email" required maxlength="254" autocomplete="email" placeholder="you@example.com"></div><div class="field"><label for="auth-password">Password</label><input id="auth-password" name="password" type="password" required ${mode==='register'?'minlength="12"':''} maxlength="128" autocomplete="${mode==='register'?'new-password':'current-password'}" placeholder="${mode==='register'?'At least 12 characters':'Your account password'}"></div>${mode==='login'?'<div class="field"><label for="auth-otp">Authenticator code <span style="color:#a3aa99">(if MFA is enabled)</span></label><input id="auth-otp" name="otp" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" autocomplete="one-time-code" placeholder="6-digit code"><small>Doctors and admins must use MFA. Each code can be used once.</small></div>':''}<button type="submit" class="btn full">${mode==='login'?'Sign in securely':'Create patient account'} ${icon('arrow')}</button></form><p class="inline-note">${mode==='register'?'All new accounts start as patients. Doctor access is assigned by an administrator.':'Sessions stay in this browser tab and end when you reload or sign out.'}</p>`);
  $('#login-tab').onclick=()=>authModal('login');$('#register-tab').onclick=()=>authModal('register');
  $('#auth-form').onsubmit=event=>{event.preventDefault();formAction(event.target,async f=>{
    const email=String(f.get('email')).trim(),password=String(f.get('password'));
    if(mode==='register'){
      await api('/auth/register',{method:'POST',body:{email,password,name:String(f.get('name')).trim()},auth:false});
      authModal('login');$('#auth-email').value=email;toast('Account created. Sign in to continue.');return;
    }
    const otp=String(f.get('otp')||'').trim();
    const result=await api('/auth/login',{method:'POST',body:{email,password,...(otp?{otp}:{})},auth:false,retry:false});
    state.token=result.access_token;
    try{state.user=await api('/me');}catch(error){state.token=null;throw error;}
    const next=state.afterLogin;state.afterLogin=null;closeModal();render();toast('Welcome. You are signed in.');if(next)next();
  });};
}
async function appointments(id) {
  const title=state.user?.role==='doctor'?'Your consultations.':'Your appointments.';
  $('#main').innerHTML=pageHeading(title,'Keep your care plans, consultation updates and prescriptions together.',btn(`${icon('refresh')} Refresh`,'refresh','secondary'))+'<div id="appointments-results"></div><div id="appointment-pages"></div>';
  bindActions();
  if(!state.user){$('#appointments-results').innerHTML=empty('Your care has a home here','Sign in to see your appointments and prescriptions.',btn('Sign in','signin'));bindActions();return;}
  $('#appointments-results').innerHTML='<div class="skeleton loading-line"></div>';
  const rows=await api(`/consultations?limit=20&offset=${state.consultationOffset}`);if(id!==state.renderId)return;state.consultations=rows;
  $('#appointments-results').innerHTML=rows.length?rows.map(c=>{
    const title=state.user.role==='doctor'?(c.patient_name||`Patient · ${shortId(c.patient_id)}`):(c.doctor_name||state.doctors.find(d=>d.id===c.doctor_id)?.name||`Doctor · ${shortId(c.doctor_id)}`);
    return `<article class="appointment-card"><div class="avatar">${esc(initials(title))}</div><div class="appointment-content"><h3>${esc(title)}</h3><div class="appointment-meta">${esc(dateTime(c.starts_at))}<br>Reference <span class="mono">${esc(shortId(c.id))}</span></div></div><div class="appointment-actions"><span class="badge ${esc(c.status)}">${esc(c.status.replaceAll('_',' '))}</span><button class="btn secondary" type="button" data-consultation="${esc(c.id)}">View details ${icon('arrow')}</button></div></article>`;
  }).join(''):empty('No appointments yet',state.user.role==='doctor'?'Publish availability so patients can book time with you.':'Find a doctor and choose an available time to begin.',btn(state.user.role==='doctor'?'Add availability':'Find a doctor',state.user.role==='doctor'?'availability':'doctors'));
  pagination($('#appointment-pages'),state.consultationOffset,20,rows.length,offset=>{state.consultationOffset=offset;render();});bindActions();
  document.querySelectorAll('[data-consultation]').forEach(b=>b.onclick=()=>consultationModal(rows.find(c=>c.id===b.dataset.consultation)));
}
async function consultationModal(c) {
  openModal('Consultation details',`<div class="info-row"><span>Status</span><span class="badge ${esc(c.status)}">${esc(c.status.replaceAll('_',' '))}</span></div><div class="info-row"><span>Appointment</span><span class="info-value">${esc(dateTime(c.starts_at))}</span></div><div class="info-row"><span>Consultation ID</span><span class="info-value mono">${esc(c.id)}</span></div><div class="info-row"><span>Doctor ID</span><span class="info-value mono">${esc(c.doctor_id)}</span></div><div id="clinical-content"></div><div id="consult-actions" style="margin-top:20px;display:flex;gap:10px;flex-wrap:wrap"></div>`);
  const revision=modalRevision;
  const assignedDoctor=state.user?.id===c.doctor_id;
  const actions=$('#consult-actions');
  if(c.status==='booked'){
    if(assignedDoctor)actions.insertAdjacentHTML('beforeend','<button class="btn" type="button" id="start-consultation">Start consultation</button>');
    actions.insertAdjacentHTML('beforeend','<button class="btn danger" type="button" id="cancel-consultation">Cancel appointment</button>');
  }
  let hasPrescription=false;
  if(['in_progress','completed'].includes(c.status)){
    $('#clinical-content').innerHTML='<p class="loading-text">Loading prescription…</p>';
    try{
      const p=await api(`/consultations/${encodeURIComponent(c.id)}/prescription`);
      if(revision!==modalRevision || !$('#clinical-content'))return;hasPrescription=true;
      $('#clinical-content').innerHTML='<h3 style="margin-top:22px">Prescription</h3><div class="prescription"></div>';
      $('.prescription').textContent=p.text;
    }catch(error){
      if(revision!==modalRevision || !$('#clinical-content'))return;
      if(error.status!==404){$('#clinical-content').innerHTML=`<div class="error">${esc(error.message)}</div>`;}
      else if(assignedDoctor && c.status==='in_progress'){
        $('#clinical-content').innerHTML='<form id="prescription-form" style="margin-top:23px"><div class="field"><label for="prescription-text">Write prescription</label><textarea id="prescription-text" name="text" required maxlength="10000" placeholder="Enter the consultation prescription…"></textarea><small>A prescription cannot be edited after saving in this assignment.</small></div><button class="btn full" type="submit">Save prescription</button></form>';
        $('#prescription-form').onsubmit=event=>{event.preventDefault();formAction(event.target,async f=>{await api(`/consultations/${encodeURIComponent(c.id)}/prescription`,{method:'POST',body:{text:f.get('text')}});toast('Prescription saved securely.');consultationModal(c);});};
      }else $('#clinical-content').innerHTML='<div class="notice">Your doctor has not issued a prescription yet.</div>';
    }
  }
  if(revision!==modalRevision || !$('#consult-actions'))return;
  if(assignedDoctor && c.status==='in_progress' && hasPrescription)$('#consult-actions').insertAdjacentHTML('beforeend','<button class="btn" type="button" id="complete-consultation">Complete consultation</button>');
  async function update(status,b){b.disabled=true;try{await api(`/consultations/${encodeURIComponent(c.id)}`,{method:'PATCH',body:{status}});closeModal();toast(status==='cancelled'?'Appointment cancelled.':'Consultation updated.');render();}catch(error){toast(error.message,true);b.disabled=false;}}
  if($('#start-consultation'))$('#start-consultation').onclick=event=>update('in_progress',event.currentTarget);
  if($('#complete-consultation'))$('#complete-consultation').onclick=event=>update('completed',event.currentTarget);
  if($('#cancel-consultation'))$('#cancel-consultation').onclick=()=>{
    openModal('Cancel this appointment?',`<p class="subtext">This releases the appointment slot so another patient can book it.</p><button class="btn danger full" id="confirm-cancel" type="button">Yes, cancel appointment</button>`);
    $('#confirm-cancel').onclick=event=>update('cancelled',event.currentTarget);
  };
}
function settingsPage() {
  $('#main').innerHTML=pageHeading('Your account. Your peace of mind.','Manage your profile and add an extra layer of protection.');
  if(!state.user){$('#main').insertAdjacentHTML('beforeend',empty('Make yourself at home','Sign in to manage your account and security settings.',btn('Sign in','signin')));bindActions();return;}
  const u=state.user;
  $('#main').insertAdjacentHTML('beforeend',`<div class="two-cols"><section class="panel"><div class="section-heading"><h2>Your profile</h2><span class="avatar avatar-small">${esc(initials(u.name||u.email))}</span></div><div class="info-row"><span>Name</span><span class="info-value">${esc(u.name||'Your account')}</span></div><div class="info-row"><span>Email</span><span class="info-value">${esc(u.email)}</span></div><div class="info-row"><span>Account type</span><span class="badge">${esc(u.role)}</span></div><div class="info-row"><span>User ID</span><span class="info-value mono" id="profile-user-id">${esc(u.id)}</span></div><button class="btn secondary" type="button" id="copy-user" style="margin-top:17px">Copy user ID</button><div class="notice">Keep your user ID handy if an administrator is setting up your doctor access.</div></section><section class="panel"><div class="section-heading"><h2>A little extra security</h2>${icon('shield')}</div><p class="subtext">Multi-factor authentication (MFA) adds a six-digit authenticator code to your password.</p><div class="info-row"><span>MFA status</span><span class="badge">${u.mfa_enabled?'Enabled':'Not enabled'}</span></div>${u.mfa_enabled?'<div class="notice">Use a fresh authenticator code each time you sign in. Account recovery is not included in this demo.</div>':'<button class="btn full" type="button" id="setup-mfa" style="margin-top:19px">Set up authenticator '+icon('arrow')+'</button>'}<div class="notice">Your session is held only in this tab. Refreshing the page signs you out. Signing out clears this tab’s token; it does not revoke a token already copied elsewhere.</div><button class="btn secondary full" type="button" data-action="logout" style="margin-top:18px">Sign out</button></section></div>`);
  bindActions();$('#copy-user').onclick=async()=>{try{await navigator.clipboard.writeText(u.id);toast('User ID copied.');}catch{toast('Select and copy the user ID shown above.',true);}};
  if($('#setup-mfa'))$('#setup-mfa').onclick=mfaSetup;
}
async function mfaSetup() {
  openModal('Set up your authenticator',`<p class="subtext">Use an authenticator app on your phone. Add a new time-based account using the setup key below.</p><div id="mfa-content" class="loading-text">Preparing your setup key…</div>`);
  const revision=modalRevision;
  try{
    const result=await api('/auth/mfa/setup',{method:'POST'});if(revision!==modalRevision || !$('#mfa-content'))return;
    $('#mfa-content').className='';$('#mfa-content').innerHTML=`<div class="field-label">Setup key · keep this private</div><div class="secret-box"></div><p class="subtext">Account: ${esc(state.user.email)}<br>Issuer: Amrutam · Type: time-based (TOTP)</p><form id="mfa-form"><div class="field"><label for="mfa-code">Enter the code from your authenticator</label><input id="mfa-code" name="otp" required pattern="[0-9]{6}" maxlength="6" inputmode="numeric" autocomplete="one-time-code" placeholder="6-digit code"></div><button class="btn full" type="submit">Enable MFA ${icon('shield')}</button></form><div class="notice">After enabling, sign in again with the next code. Each code is accepted once.</div>`;
    $('.secret-box').textContent=result.secret;
    $('#mfa-form').onsubmit=event=>{event.preventDefault();formAction(event.target,async f=>{await api('/auth/mfa/confirm',{method:'POST',body:{otp:f.get('otp')}});state.token=null;state.user=null;closeModal();render();authModal('login');toast('MFA enabled. Wait for the next authenticator code, then sign in.');});};
  }catch(error){if(revision===modalRevision && $('#mfa-content')){$('#mfa-content').className='error';$('#mfa-content').textContent=error.message;}}
}
async function availability(id) {
  if(state.user?.role!=='doctor'){state.page='settings';await render();return;}
  $('#main').innerHTML=pageHeading('Make room for your patients.','Publish available consultation times. Overlapping slots are prevented.')+`<div class="two-cols"><section class="panel"><div class="section-heading"><h2>Add an available time</h2>${icon('calendar')}</div><form id="availability-form"><div class="field"><label for="slot-start">Starts at · your local time</label><input id="slot-start" name="start" type="datetime-local" required></div><div class="field"><label for="slot-end">Ends at · your local time</label><input id="slot-end" name="end" type="datetime-local" required></div><button class="btn full" type="submit">Publish availability ${icon('plus')}</button></form><div class="notice">Times are converted to UTC when saved. Only future, non-overlapping slots are accepted.</div></section><section class="panel"><div class="section-heading"><h2>Your open slots</h2><button class="text-link" type="button" data-action="refresh">Refresh ${icon('refresh')}</button></div><div id="my-slots" class="loading-text">Loading availability…</div><div class="page-note">The earliest 100 future, unbooked slots are shown here.</div></section></div>`;
  bindActions();
  $('#availability-form').onsubmit=event=>{event.preventDefault();formAction(event.target,async f=>{const start=new Date(f.get('start')),end=new Date(f.get('end'));if(start<=new Date() || end<=start)throw new Error('Choose a future start time and an end after the start.');await api('/doctors/me/slots',{method:'POST',body:{starts_at:start.toISOString(),ends_at:end.toISOString()}});toast('Your availability is published.');render();});};
  const rows=await api(`/doctors/${encodeURIComponent(state.user.id)}/slots?limit=100`);if(id!==state.renderId)return;
  $('#my-slots').className='';$('#my-slots').innerHTML=rows.length?`<div class="slot-list" style="margin-top:0">${rows.map(s=>`<div class="slot-button">${esc(dateTime(s.starts_at))}<small>Ends ${esc(new Date(s.ends_at).toLocaleTimeString(undefined,{hour:'numeric',minute:'2-digit'}))}</small></div>`).join('')}</div>`:'<p class="subtext">No open slots yet. Add your first time using the form.</p>';
}
async function adminPage(id) {
  if(state.user?.role!=='admin'){state.page='settings';await render();return;}
  $('#main').innerHTML=pageHeading('A clear view of your care network.','Manage doctor access and review operational activity.',btn(`${icon('refresh')} Refresh`,'refresh','secondary'))+`<div id="admin-stats" class="stats">${stat('Patients','—','Registered patient accounts','user')}${stat('Doctors','—','Doctor profiles','doctors')}${stat('Consultations','—','Across the care network','calendar')}</div><div class="two-cols"><section class="panel"><div class="section-heading"><h2>Consultation activity</h2>${icon('list')}</div><div id="status-bars" class="loading-text">Loading activity…</div></section><section class="panel"><div class="section-heading"><h2>Approve doctor access</h2>${icon('plus')}</div><p class="subtext" style="margin-bottom:20px">Grant doctor access to a registered account with MFA enabled. Enter the applicant’s user ID, specialty and consultation fee.</p><form id="doctor-create-form"><div class="field"><label for="doctor-user-id">Registered user ID</label><input id="doctor-user-id" name="user_id" required placeholder="Paste the user ID"></div><div class="form-row"><div class="field"><label for="doctor-specialty">Specialty</label><input id="doctor-specialty" name="specialty" required maxlength="100" placeholder="Ayurveda"></div><div class="field"><label for="doctor-fee">Consultation fee · ₹</label><input id="doctor-fee" name="fee" required type="number" min="0" max="100000" step="0.01" placeholder="500"></div></div><button class="btn full" type="submit">Approve doctor access ${icon('arrow')}</button></form></section></div><section class="panel"><div class="section-heading"><div><h2>Audit trail</h2><p class="subtext">Operational metadata. Clinical records stay with participants.</p></div>${icon('shield')}</div><div id="audit-results" class="loading-text">Loading events…</div><div id="audit-pages"></div></section>`;
  bindActions();
  $('#doctor-create-form').onsubmit=event=>{event.preventDefault();formAction(event.target,async f=>{await api('/admin/doctors',{method:'POST',body:{user_id:String(f.get('user_id')).trim(),specialty:String(f.get('specialty')).trim(),fee_paise:Math.round(Number(f.get('fee'))*100)}});toast('Doctor access approved. They can sign in again with MFA.');render();});};
  const [a,rows]=await Promise.all([api('/admin/analytics'),api(`/admin/audit?limit=20&offset=${state.auditOffset}`)]);if(id!==state.renderId)return;
  const total=Object.values(a.consultations_by_status).reduce((sum,x)=>sum+x,0);
  $('#admin-stats').innerHTML=stat('Patients',a.patients,'Registered patient accounts','user')+stat('Doctors',a.doctors,'Doctor profiles','doctors')+stat('Consultations',total,'Across the care network','calendar');
  $('#status-bars').className='status-bars';$('#status-bars').innerHTML=['booked','in_progress','completed','cancelled'].map(status=>`<div><div class="bar-label"><span>${esc(status.replaceAll('_',' '))}</span><strong>${a.consultations_by_status[status]||0}</strong></div><div class="bar-track"><div class="bar-fill" style="width:${total?100*(a.consultations_by_status[status]||0)/total:0}%"></div></div></div>`).join('');
  $('#audit-results').className='table-wrap';$('#audit-results').innerHTML=rows.length?`<table><thead><tr><th>Time</th><th>Action</th><th>Actor ID</th><th>Resource ID</th></tr></thead><tbody>${rows.map(row=>`<tr><td>${esc(dateTime(row.created_at))}</td><td>${esc(row.action.replaceAll('_',' '))}</td><td class="mono">${esc(row.actor_id)}</td><td class="mono">${esc(row.resource_id)}</td></tr>`).join('')}</tbody></table>`:'<p class="subtext">No events on this page.</p>';
  pagination($('#audit-pages'),state.auditOffset,20,rows.length,offset=>{state.auditOffset=offset;render();});
}
$('#register-button').onclick=()=>authModal('register');
$('#account-button').onclick=()=>{
  if(!state.user){authModal('login');return;}
  openModal('Your workspace',`<p class="subtext">${esc(state.user.email)} · ${esc(state.user.role)}</p><div class="account-menu">${btn(`${icon('shield')} Account & security`,'settings','secondary')}${btn('Sign out','logout','secondary')}</div>`);
  $('[data-action="settings"]',modal).onclick=()=>{closeModal();navigate('settings');};$('[data-action="logout"]',modal).onclick=logout;
};
async function checkHealth(){try{await api('/health/ready',{auth:false});$('#service-state').textContent='System online';$('.service-state').classList.add('online');}catch{$('#service-state').textContent='Backend unavailable';}}
checkHealth();
// Separate public website layout from signed-in workspaces.
const originalPortalNav = nav;

nav = function () {
  originalPortalNav();

  const guest = !state.user;
  document.body.classList.toggle('guest-home', guest);

  let header = document.getElementById('public-header');

  if (!guest) {
    if (header) header.remove();
    return;
  }

  if (!header) {
    header = document.createElement('header');
    header.id = 'public-header';
    document.querySelector('.workspace').prepend(header);
  }

  header.innerHTML = `
    <button class="public-brand" data-action="public-home">
      amrutam<span>YOUR CARE, CONNECTED</span>
    </button>

    <nav class="public-links" aria-label="Visitor navigation">
      <button data-action="doctors">Find a doctor</button>
      <button data-action="public-how">How it works</button>
      <button data-action="signin">Sign in</button>
      <button class="btn" data-action="signup">Create account</button>
    </nav>
  `;

  bindActions(header);

  header.querySelector('[data-action="public-home"]').onclick =
    () => navigate('overview');

  header.querySelector('[data-action="public-how"]').onclick =
    async () => {
      state.page = 'overview';
      await render();
      document.getElementById('public-how-it-works')
        ?.scrollIntoView({ behavior: 'smooth' });
    };
};

const originalPortalOverview = overview;

overview = async function (id) {
  await originalPortalOverview(id);

  // Do not change a different page or a signed-in workspace.
  if (id !== state.renderId || state.user) return;

  const main = document.getElementById('main');
  const hero = main.querySelector('.hero');

  if (!hero) return;

  hero.querySelector('.eyebrow').textContent =
    'A LITTLE TIME FOR YOURSELF';

  hero.querySelector('h2').innerHTML =
    'Your wellbeing starts<br>with a conversation.';

  hero.querySelector('.hero-copy > p:not(.eyebrow)').textContent =
    'Explore doctors, choose a convenient time, and manage your consultation in one place.';

  const exploreButton = hero.querySelector('[data-action="doctors"]');
  if (exploreButton) exploreButton.textContent = 'Explore doctors →';

  hero.querySelector('.hero-copy').insertAdjacentHTML(
    'beforeend',
    `<button class="public-secondary" data-action="signup">
      Create an account
    </button>`
  );

  hero.insertAdjacentHTML('afterend', `
    <section id="public-how-it-works" class="public-how">
      <p class="eyebrow">CARE, MADE SIMPLE</p>
      <h2>Three steps to your next consultation.</h2>

      <div class="public-steps">
        <article>
          <span>01</span>
          <h3>Find your doctor</h3>
          <p>Browse specialties and consultation fees.</p>
        </article>

        <article>
          <span>02</span>
          <h3>Choose your time</h3>
          <p>Sign in and book an available consultation slot.</p>
        </article>

        <article>
          <span>03</span>
          <h3>Keep your care together</h3>
          <p>View your appointments and prescriptions in your account.</p>
        </article>
      </div>
    </section>
  `);

  const directoryTitle = main.querySelector('.directory-heading h2');
  if (directoryTitle) directoryTitle.textContent = 'Meet your care team';

  const directory = document.getElementById('overview-doctors');
  if (directory) {
    const previous = directory.previousElementSibling;
    if (!previous?.textContent.includes('Sample profiles')) {
      directory.insertAdjacentHTML(
        'beforebegin',
        '<p class="subtext">Sample profiles for demonstration only.</p>'
      );
    }
  }

  bindActions(main);
};
// Render again after installing the visitor layout.
render();