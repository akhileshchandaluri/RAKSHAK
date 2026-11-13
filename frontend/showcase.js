"use strict";
let continuitySeries = [], continuityBuilding = null, continuityTime = -1;
function applyPreset() {
  const name = document.getElementById('preset').value;
  const settings = {
    normal:['generation_loss',0,100,2,45], generation_loss:['generation_loss',18,100,2,45],
    demand_surge:['demand_surge',18,100,2,45], severe:['generation_loss',35,5,2,90],
    stress:['generation_loss',35,100,2,90],
    feeder_fault:['feeder_fault',0,100,2,45], backup_exhaustion:['feeder_fault',0,100,.25,90],
    restoration:['generation_loss',18,100,2,45], solar_surplus:['solar_surplus',12,100,2,45],
  }[name];
  ['disturbance','loss','participation','backup','trec'].forEach((id,i)=>{
    document.getElementById(id).value=settings[i];
    document.getElementById(id).dispatchEvent(new Event('input'));
  });
  reset();
}
function updateContinuity(building) {
  const box = document.getElementById('continuity-box');
  const data = building.snapshot?.continuity;
  const priorityControl = ['rakshak', 'rakshak_unstaggered'].includes(S.live?.mode);
  box.hidden = !priorityControl || !data || data.requested_w <= 0;
  document.getElementById('request-appliance').href='appliances.html?building='+building.i;
  document.getElementById('inventory-revision').textContent = S.live ? 'Frozen inventory revision '+S.live.inventory_revision+' · Reset applies approved changes.' : 'Waiting for backend inventory';
  document.getElementById('water-values').textContent=building.snapshot?.tank_l != null
    ? 'Water tank: '+building.snapshot.tank_l.toFixed(1)+' / 500 L · unmet service '+building.snapshot.water_shortfall_l.toFixed(2)+' L. Capacity and flows are declared assumptions.' : '';
  if (box.hidden) {
    continuityBuilding = null;
    return;
  }
  const supply = building.snapshot.on_backup ? 'backup' : building.energized && !S.collapsed ? 'grid' : 'unavailable';
  document.getElementById('continuity-values').textContent =
    data.requested_w.toFixed(0)+' W requested / '+data.supplied_w.toFixed(0)+' W supplied · '+supply+
    ' · '+data.interruption_s.toFixed(2)+' s interrupted · '+data.unserved_wh.toFixed(3)+' Wh unserved · '+data.backup_remaining_wh.toFixed(2)+' Wh backup remaining';
  if(continuityBuilding!==building.i || S.t<continuityTime) continuitySeries=[];
  if(continuityBuilding!==building.i || S.t!==continuityTime) continuitySeries.push([S.t,data.requested_w,data.supplied_w]);
  continuitySeries=continuitySeries.filter(point => point[0] >= S.t-60).slice(-280); continuityBuilding=building.i; continuityTime=S.t;
  const canvas=document.getElementById('continuity-chart'), c=canvas.getContext('2d');
  c.clearRect(0,0,canvas.width,canvas.height);
  const max=Math.max(1,...continuitySeries.flatMap(p=>p.slice(1)));
  ['#38bdf8','#22c55e'].forEach((color,index)=>{
    c.strokeStyle=color;c.lineWidth=2;c.beginPath();
    continuitySeries.forEach((point,i)=>{const x=5+(point[0]-continuitySeries[0][0])*270/Math.max(.05,S.t-continuitySeries[0][0]), y=52-point[index+1]/max*44;i?c.lineTo(x,y):c.moveTo(x,y);});c.stroke();
  });
  c.fillStyle='#94a3b8';c.font='10px system-ui';c.fillText(max.toFixed(0)+' W',5,9);c.fillText(continuitySeries[0][0].toFixed(1)+' s → '+S.t.toFixed(1)+' s',5,64);
}
