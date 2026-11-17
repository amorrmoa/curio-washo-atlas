(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const safeUrl = text => { try { const u = new URL(text); return u.protocol === 'https:' && (u.hostname === 'ndlsearch.ndl.go.jp' || u.hostname === 'www.ndl.go.jp') ? u.href : ''; } catch { return ''; }};
  const session = {books:[],taxonomy:{families:[]},q:'',concept:'',year:'',publisher:'',sort:'discovered',savedOnly:false,limit:18};
  let saved = new Set();
  try { saved = new Set(JSON.parse(localStorage.getItem('washo:saved') || '[]')); } catch (_) {}
  function savePrefs(){try{localStorage.setItem('washo:saved',JSON.stringify([...saved]))}catch(_){}}
  function setOptions(id,values,placeholder){const sel=$(id);sel.innerHTML=`<option value="">${esc(placeholder)}</option>`+values.map(x=>`<option value="${esc(x)}">${esc(x)}</option>`).join('');}
  function uniqueSorted(a){return [...new Set(a.filter(Boolean))].sort((a,b)=>String(a).localeCompare(String(b),'ja'));}
  function updateState(){
    const b=session.books;
    $('stat-total').textContent=String(b.length);
    $('stat-concepts').textContent=String(session.taxonomy.families.length||18);
    const m=session.meta||{};
    if(m.updated_at){const d=new Date(m.updated_at);$('last-update').textContent=isNaN(d)?'更新情報なし':d.toLocaleDateString('ja-JP',{year:'numeric',month:'short',day:'numeric',timeZone:'Asia/Tokyo'}); $('update-note').textContent=`前回追加 ${m.found_last_run||0}冊 · 取込${m.weeks_processed||0}週 · エラー${m.queries_failed||0}件`;}
    else {$('last-update').textContent='初回更新前';}
    setOptions('year',uniqueSorted(b.map(v=>String(v.published||'').slice(0,4))).reverse(),'すべての刊行年');
    setOptions('publisher',uniqueSorted(b.map(v=>v.publisher)),'すべての出版社');
    setOptions('concept',(session.taxonomy.families||[]).map(v=>v.label),'すべての概念');
    const atlas=$('concept-grid');
    atlas.innerHTML=(session.taxonomy.families||[]).map((f,i)=>`<button type="button" class="concept-card" data-topic="${esc(f.label)}"><small>NO. ${String(i+1).padStart(2,'0')} / CONCEPT</small><span class="concept-arrow">↗</span><strong>${esc(f.label)}</strong><span>${esc((f.core||[]).slice(0,2).join(' · '))}</span></button>`).join('');
  }
  const textSearch = (v,q)=>[v.title,(v.authors||[]).join(' '),v.publisher, (v.tags||[]).join(' ')].join(' ').toLocaleLowerCase().includes(q.toLocaleLowerCase());
  function filtered(){
    const q=session.q.trim();
    const a=session.books.filter(b=> (!q||textSearch(b,q))&&(!session.concept||(b.tags||[]).includes(session.concept))&&(!session.year||String(b.published||'').startsWith(session.year))&&(!session.publisher||b.publisher===session.publisher)&&(!session.savedOnly||saved.has(b.id)));
    a.sort((x,y)=>{
      if(session.sort==='score')return (y.score||0)-(x.score||0);
      if(session.sort==='title')return String(x.title).localeCompare(String(y.title),'ja');
      if(session.sort==='publication')return String(y.published).localeCompare(String(x.published));
      return String(y.discovered_at||'').localeCompare(String(x.discovered_at||'')) || (y.score||0)-(x.score||0);
    });
    return a;
  }
  function card(b,i){
    const tags=(b.tags||[]).slice(0,2).map(t=>`<span class="card-tag">${esc(t)}</span>`).join('');
    const author=(b.authors||[]).join(' / ') || '著者情報未確認';
    const pub=b.publisher || '出版社未確認';
    const year=(b.published||'').replace(/-00$/,'') || '刊行日未確認';
    const cover=(b.cover&&/^https:\/\//.test(b.cover))?`<img src="${esc(b.cover)}" alt="${esc(b.title)}の書影" loading="lazy">`:'';
    return `<article class="book-card">
        <div class="card-cover"><span class="cover-issue">CURIO WASHO / ${esc(year)}</span><span class="cover-title">${esc(b.title)}</span><span class="cover-footer">ARS · LIBRI · MIRABILIA</span>${cover}</div>
        <div class="card-info"><div class="card-kicker"><span>自動発見候補</span><span>概念一致 ${Number(b.score)||0}</span></div>
        <h3 class="card-title">${esc(b.title)}</h3><div class="card-sub">${esc(author)}<br>${esc(pub)} · ${esc(year)}</div>
        <div class="card-tags">${tags}</div><div class="card-actions"><button type="button" class="card-open" data-view="${i}">書誌詳細を見る ↗</button><button type="button" class="save-button" data-fave="${esc(b.id)}" data-saved="${saved.has(b.id)}" aria-label="${saved.has(b.id)?'保存を解除':'あとで見るに保存'}">${saved.has(b.id)?'★':'☆'}</button></div></div>
      </article>`;
  }
  let rendered=[];
  function render(){
    rendered=filtered();$('result-count').textContent=String(rendered.length);
    const hasBooks=session.books.length>0;
    const isEmpty=rendered.length===0;
    $('empty-state').hidden=!isEmpty;
    $('book-grid').hidden=isEmpty;
    if(isEmpty){
      $('empty-title').textContent=hasBooks?'条件に合う本が見つかりません。':'航路は、まだ白紙です。';
      $('empty-description').textContent=hasBooks?'検索語や概念、刊行年の指定を変えてみてください。保存した本だけを表示している場合は、その条件も解除できます。':'最初の選書リストはありません。GitHub Actionsが実行され、条件に合う新刊が見つかると、ここに少しずつ本が並びます。';
    }
    $('book-grid').innerHTML=rendered.slice(0,session.limit).map(card).join('');
    $('loadbar').hidden=isEmpty||rendered.length<=session.limit;
    $('toggle-saved').setAttribute('aria-pressed', String(session.savedOnly));
  }
  function openDetail(i){
    const b=rendered[i];if(!b)return;
    const rows=[['著者',(b.authors||[]).join(' / ')||'未確認'],['出版社',b.publisher||'未確認'],['刊行年月',b.published||'未確認'],['ISBN',b.isbn||'未確認'],['出典',b.source||'国立国会図書館 JAPAN/MARC'],['登録日',b.discovered_at||'—'],['概念', (b.tags||[]).join(' / ')||'—'],['一致度',String(b.score||'—')]];
    const link=safeUrl(b.source_url||'');
    $('detail-content').innerHTML=`<div class="dialog-kicker">CURIO WASHO / BIBLIOGRAPHY / 自動発見候補</div><h3 id="detail-title">${esc(b.title)}</h3><p class="dialog-desc">以下は自動照合された書誌情報です。掲載は内容の確認や推薦を意味しません。版・刊行日などは出典でご確認ください。</p><div class="dialog-meta">${rows.map(r=>`<span class="dialog-label">${esc(r[0])}</span><span>${esc(r[1])}</span>`).join('')}</div>${link?`<a class="dialog-link" href="${esc(link)}" target="_blank" rel="noopener noreferrer">国立国会図書館サーチで確認 ↗</a>`:''}`;
    const dlg=$('detail-dialog');if(typeof dlg.showModal==='function')dlg.showModal();else dlg.setAttribute('open','');
  }
  function clearFilters(){session.q='';session.concept='';session.year='';session.publisher='';session.savedOnly=false;session.limit=18;['q','concept','year','publisher'].forEach(id=>$(id).value='');render();}
  async function load(){
    try {
      const [dataR,taxR]=await Promise.all([fetch('./data/books.json',{cache:'no-cache'}),fetch('./data/taxonomy.json',{cache:'no-cache'})]);
      if(!dataR.ok||!taxR.ok)throw new Error('Failed to load site data');
      const d=await dataR.json(),t=await taxR.json();
      session.books=Array.isArray(d.books)?d.books:[];
      session.meta=d.meta||{};
      session.taxonomy=t;
      updateState();render();
    } catch(e) {
      $('empty-state').hidden=false;
      $('empty-title').textContent='書誌データを読み込めませんでした。';
      $('empty-description').textContent='GitHub Pages公開後に再読み込みしてください。ローカルのHTMLファイルを直接開いた場合もデータを取得できません。';
      $('update-note').textContent='データ取得エラー';
    }
  }
  $('q').addEventListener('input',e=>{session.q=e.target.value;session.limit=18;render()});
  for(const id of ['concept','year','publisher','sort'])$(id).addEventListener('change',e=>{session[id]=e.target.value;session.limit=18;render()});
  $('reset-filters').addEventListener('click',clearFilters);
  $('toggle-saved').addEventListener('click',()=>{session.savedOnly=!session.savedOnly;session.limit=18;render()});
  $('load-more').addEventListener('click',()=>{session.limit+=18;render()});
  $('book-grid').addEventListener('click', e=>{
    const view=e.target.closest('[data-view]');if(view){openDetail(Number(view.dataset.view));return;}
    const fave=e.target.closest('[data-fave]');if(fave){const id=fave.dataset.fave;if(saved.has(id))saved.delete(id);else saved.add(id);savePrefs();render();}
  });
  $('concept-grid').addEventListener('click',e=>{const btn=e.target.closest('[data-topic]');if(!btn)return;clearFilters();session.concept=btn.dataset.topic;$('concept').value=session.concept;render();$('discovery').scrollIntoView({behavior:'smooth'});});
  $('close-dialog').addEventListener('click',()=>$('detail-dialog').close());
  $('detail-dialog').addEventListener('click',e=>{if(e.target===$('detail-dialog'))$('detail-dialog').close()});
  load();
})();
