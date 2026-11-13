const assert=require('node:assert/strict');
const {chromium}=require(process.env.RAKSHAK_PLAYWRIGHT_MODULE||'playwright');
(async()=>{
const browser=await chromium.launch({channel:process.env.RAKSHAK_BROWSER_CHANNEL});
try{
 const context=await browser.newContext({viewport:{width:1100,height:800}}), errors=[];
 context.on('page',p=>p.on('pageerror',e=>errors.push(e.message)));
 const base=process.env.RAKSHAK_TEST_URL||'http://127.0.0.1:8001';
 const grid=await context.newPage();await grid.goto(base+'/');
 await grid.waitForFunction(()=>Boolean(S.live),null,{timeout:45000});
 const original=await grid.evaluate(()=>S.live.inventory_revision);await grid.locator('#btn-play').click();
 const resident=await context.newPage();await resident.goto(base+'/appliances.html?building=0');
 await resident.selectOption('#catalog','custom');
 const name='Reviewed <b>custom</b> appliance '+Date.now();
 await resident.fill('#name',name);await resident.fill('#watts','125');await resident.selectOption('#tier','0');
 await resident.fill('#source','https://mepdcl.in/Pages/ConsumptionCalculator');
 await resident.fill('#justification','Isolated browser test: explicit assumed custom power and reviewed continuity role.');
 await resident.locator('#request-form button').click();await resident.waitForFunction(()=>document.getElementById('status').textContent.includes('pending'));
 assert.equal(await grid.evaluate(()=>S.live.inventory_revision),original);
 const review=await context.newPage();await review.goto(base+'/reviewer.html');
 const card=review.locator('article').filter({hasText:name});await card.locator('textarea').fill('Isolated workflow verification; not a clinical certification.');
 await card.getByRole('button',{name:'Approve',exact:true}).click();
 await review.waitForFunction(()=>document.getElementById('status').textContent.includes('credential required'));
 await review.fill('#credential',process.env.RAKSHAK_TEST_REVIEWER_TOKEN);
 await card.getByRole('button',{name:'Approve',exact:true}).click();
 await review.waitForFunction(()=>document.getElementById('status').textContent.includes('Decision recorded'));
 assert.equal(await grid.evaluate(()=>S.live.inventory_revision),original);
 await grid.locator('#btn-restart').click();
 await grid.waitForFunction(old=>S.live?.inventory_revision>old,original,{timeout:45000});
 await grid.locator('#building-choice').selectOption('0');
 await grid.waitForFunction(n=>document.getElementById('device-list-container').textContent.includes(n),name);
 assert.equal(await grid.locator('#device-list-container b').count(),0);
 assert.equal(await grid.locator('#continuity-box').isVisible(),true);
 console.log(JSON.stringify({approval:'passed',unauthorized:'rejected',frozenRevision:'passed',customInventory:'visible',htmlEscaping:'passed',errors}));
 assert.deepEqual(errors,[]);
}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
