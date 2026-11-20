const fs = require('fs');
const {chromium} = require(process.env.RAKSHAK_PLAYWRIGHT_MODULE || 'playwright');
(async()=>{
 const browser=await chromium.launch({headless:true, channel:process.env.RAKSHAK_BROWSER_CHANNEL});
 const page=await browser.newPage({viewport:{width:1600,height:1000}});
 const errors=[]; page.on('pageerror', e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:8000/street.html');
 await page.waitForFunction(()=>document.getElementById('badge-conn').textContent.includes('LIVE'),null,{timeout:45000});
 await page.locator('#btn-play').click();
 const inventory=[];
 for(let i=0;i<12;i++){
   await page.locator('#building-choice').selectOption(String(i));
   await page.waitForTimeout(120);
   inventory.push(await page.evaluate(()=>({i:sel,visible:document.querySelectorAll('#device-list-container .device-row').length,expected:S.B[sel].devs.filter(d=>d.own).length,continuity:!document.getElementById('continuity-box').hidden})));
 }
 await page.locator('#building-choice').selectOption('1');
 await page.waitForTimeout(250);
 await page.locator('#btn-street-view').click(); await page.waitForTimeout(1500);
 await page.screenshot({path:'var/showcase-desktop.png',fullPage:true});
 console.log(JSON.stringify({errors,inventory,ecg:await page.locator('#ecg-canvas').count(),title:await page.title()}));
 await page.locator('#preset').selectOption('feeder_fault');
 await page.waitForFunction(()=>S.t>6,null,{timeout:45000});
 if(errors.length || inventory.some(x=>x.visible!==x.expected)) throw Error('UI verification failed');
 console.log('fault',await page.evaluate(()=>S.live.buildings.slice(0,3).map(b=>({i:b.i,energized:b.energized,backup:b.on_backup}))));
 await page.locator('#building-choice').selectOption('2'); await page.locator('#continuity-box').scrollIntoViewIfNeeded(); await page.waitForTimeout(500);
 await page.screenshot({path:'var/showcase-continuity.png',fullPage:true});
 await page.setViewportSize({width:390,height:844}); await page.locator('#toggle-inspector').click(); await page.screenshot({path:'var/showcase-mobile.png',fullPage:true});
 await page.evaluate(()=>{ws.onclose=null;ws.close();wsConnected=false;}); const before=await page.evaluate(()=>S.t); await page.waitForTimeout(800); if(await page.evaluate(()=>S.t)!==before) throw Error('Disconnected telemetry advanced');
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
