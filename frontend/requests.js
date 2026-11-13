"use strict";
const el=id=>document.getElementById(id), reviewer=Boolean(el('credential'));
async function loadRequests(){
  try {
    const response=await fetch('api/appliance-requests'); if(!response.ok) throw Error('Cannot load requests');
    const data=await response.json(); el('requests').replaceChildren();
    for(const request of data.requests){
      const p=request.payload;
      if(!reviewer && p.building_id!==Number(el('building').value)) continue;
      const card=document.createElement('article'), heading=document.createElement('h3'), detail=document.createElement('p'), link=document.createElement('a');
      heading.textContent=p.name+' · '+request.status;
      detail.textContent='Building '+p.building_id+' · '+p.quantity+' × '+p.power_w+' W · '+['Critical','Essential','Flexible','Ordinary'][p.tier]+
        ' · '+(p.consent?'Control consent':'No control consent')+' · '+(p.requested?'Requested on':'Idle')+' · '+p.justification;
      link.textContent='Submitted evidence';link.href=p.source;link.target='_blank';link.rel='noopener noreferrer';
      card.append(heading,detail,link);
      if(request.reason){const reason=document.createElement('p');reason.textContent='Review: '+request.reason+' · '+request.reviewed;card.append(reason);}
      if(reviewer && request.status==='pending'){
        const reason=document.createElement('textarea');reason.placeholder='Review reason (at least 10 characters)';reason.setAttribute('aria-label','Review reason');card.append(reason);
        for(const decision of ['approved','rejected']){
          const button=document.createElement('button');button.textContent=decision==='approved'?'Approve':'Reject';
          button.onclick=async()=>{
            button.disabled=true;
            try{
              const result=await fetch('api/appliance-requests/'+request.id+'/review',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+el('credential').value},body:JSON.stringify({decision,reason:reason.value})});
              const body=await result.json();if(!result.ok)throw Error(typeof body.detail==='string'?body.detail:'Review needs a valid reason');
              el('status').textContent='Decision recorded. Reset simulation to apply approved changes.';await loadRequests();
            }catch(error){el('status').textContent=error.message;button.disabled=false;}
          };card.append(button);
        }
      }
      el('requests').append(card);
    }
    if(!el('requests').children.length) el('requests').textContent='No requests.';
  }catch(error){el('status').textContent=error.message;}
}
if(reviewer) el('refresh').onclick=loadRequests;
else{
  el('building').value=new URLSearchParams(location.search).get('building')||0;
  for(const [key,spec] of Object.entries(APPLIANCE_CATALOG)) el('catalog').add(new Option(spec.name,key));
  el('catalog').add(new Option('Custom appliance (manual control only)','custom'));
  el('catalog').onchange=()=>{
    const spec=APPLIANCE_CATALOG[el('catalog').value];
    el('name').value=spec?.name||'';el('watts').value=spec?.power_w||'';el('source').value=spec?.source||'';el('tier').value=spec?.tier??3;
  };el('catalog').onchange();el('building').onchange=loadRequests;
  const existing=new URLSearchParams(location.search).get('appliance');
  if(existing){
    el('appliance-id').value=existing;
    el('appliance-id').readOnly = true;
    el('building').readOnly = true;
    const submit = el('request-form').querySelector('button[type="submit"]');
    submit.disabled = true;
    el('status').textContent = 'Loading installed appliance…';
    fetch('api/status').then(r=>{
      if(!r.ok) throw new Error('Inventory unavailable');
      return r.json();
    }).then(snapshot=>{
      const a=snapshot.buildings.find(b=>b.i===Number(el('building').value))?.appliances[existing];
      if(!a) throw new Error('Appliance not found in the current inventory');
      el('catalog').value=a.catalog_key || (APPLIANCE_CATALOG[existing]?existing:'custom');
      el('name').value=a.name;el('watts').value=a.unit_power_w;el('quantity').value=a.quantity;
      el('tier').value=a.tier;el('source').value=a.source;el('requested').checked=a.requested;el('consent').checked=a.consent;
      el('status').textContent='Edit the details, then submit for review. Approved changes apply on simulation reset.';
      submit.disabled = false;
    }).catch(error=>{el('status').textContent=error.message + '. Return to the simulator and reopen the appliance.';});
  }
  el('request-form').onsubmit=async event=>{
    event.preventDefault();const button=event.submitter;button.disabled=true;
    try{
      const body={building_id:Number(el('building').value),appliance_id:el('appliance-id').value||null,catalog_key:el('catalog').value,name:el('name').value,quantity:Number(el('quantity').value),power_w:Number(el('watts').value),tier:Number(el('tier').value),requested:el('requested').checked,consent:el('consent').checked,source:el('source').value,justification:el('justification').value};
      const response=await fetch('api/appliance-requests',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const data=await response.json();
      if(!response.ok) {
        const detail = Array.isArray(data.detail)
          ? data.detail.map(issue => issue.loc.at(-1) + ': ' + issue.msg).join(' · ')
          : data.detail;
        throw Error(detail || 'Check the required fields and evidence URL');
      }
      el('status').textContent='Request '+data.id+' is pending. Active inventory is unchanged.';await loadRequests();
    }catch(error){el('status').textContent=error.message;}finally{button.disabled=false;}
  };
}
loadRequests();
