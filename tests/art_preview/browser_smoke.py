"""Optional actual Chromium smoke. Requires externally provided Playwright/Chromium.
Does not install dependencies, publish, or establish artistic acceptance.
"""
import argparse
import json
from pathlib import Path
import tempfile
import functools
import http.server
import threading
from playwright.sync_api import sync_playwright
from tools.art.preview.example import create

p=argparse.ArgumentParser();p.add_argument('--chromium',required=True);p.add_argument('--report',type=Path,required=True);args=p.parse_args()
checks=[]
def check(value,name):
    if not value: raise AssertionError(name)
    checks.append(name)
with tempfile.TemporaryDirectory() as name:
    root=Path(name)/'fixture';create(root)
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(root/'site')))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    with sync_playwright() as driver:
        browser=driver.chromium.launch(executable_path=args.chromium,headless=True,args=['--no-sandbox'])
        page=browser.new_page(viewport={'width':390,'height':844})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(f'http://127.0.0.1:{server.server_port}/index.html');page.wait_for_function("document.querySelector('canvas').width === 8")
        check(page.locator('#play').inner_text()=='Play','animation defaults paused')
        for width in (390,1440):
            page.set_viewport_size({'width':width,'height':844})
            layout=page.evaluate("""() => {
                const box=id=>document.getElementById(id).getBoundingClientRect();
                const a=box('assets'),i=box('identity'),d=box('direct');
                const n=document.querySelector('label[for="notes"]').getBoundingClientRect();
                return {width:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth,
                    assetLeft:a.left,assetRight:a.right,identityLeft:i.left,identityRight:i.right,
                    identityOverflow:document.getElementById('identity').scrollWidth>i.width+1,
                    gap:n.top-d.bottom};
            }""")
            check(layout['scroll']<=layout['width'] and layout['assetLeft']>=0 and layout['assetRight']<=width
                  and layout['identityLeft']>=0 and layout['identityRight']<=width and not layout['identityOverflow']
                  and layout['gap']>=8, f'{width}px controls/hash fit and feedback label separated')
        page.set_viewport_size({'width':390,'height':844})

        page.locator('#scale').select_option('8');page.locator('#canvas').click(position={'x':20,'y':20})
        page.locator('#next').click();page.locator('#notes').fill('Check frame contact');page.locator('#feedback').click()
        text=page.locator('#output').input_value();link=page.locator('#direct').evaluate('(a)=>a.href')
        check('Frame (zero-based): 1' in text and 'Check frame contact' in text,'precise feedback from real controls')
        page.goto(link);page.wait_for_function("document.querySelector('#position').textContent.includes('Frame 1')")
        check(page.locator('#play').inner_text()=='Play','direct frame opens paused')
        page.locator('#assets').select_option('1');page.wait_for_function("document.querySelector('canvas').width === 12")
        page.locator('#play').click();page.wait_for_timeout(600)
        check(page.locator('#play').inner_text()=='Play' and 'Frame 2' in page.locator('#position').inner_text(),'nonloop animation settles at last frame')
        page.locator('#assets').select_option('2');page.wait_for_function("document.querySelector('#play').disabled")
        check(page.locator('#canvas').evaluate('(c)=>c.width')==36,'character still shown uncropped')
        page.locator('#assets').select_option('3');page.wait_for_function("document.querySelector('#identity').textContent.includes('fixture_scene_still')")
        check(page.locator('#canvas').evaluate('(c)=>c.width')==36,'scene still adapter shown')
        pending=[]
        page.route('**/*.png',lambda route:pending.append(route))
        page.locator('#assets').select_option('0');page.wait_for_timeout(50)
        check(page.locator('#canvas').evaluate('(c)=>c.width')==0 and page.locator('#feedback').is_disabled() and page.locator('#direct').get_attribute('href') is None,'loading asset cannot show old pixels or emit feedback')
        check(bool(pending),'image loading intentionally held')
        pending.pop().abort();page.wait_for_function("document.querySelector('#error').textContent.includes('failed to load')")
        check(page.locator('#canvas').evaluate('(c)=>c.width')==0 and page.locator('#feedback').is_disabled(),'failed image remains unavailable')
        page.unroute('**/*.png');page.locator('#assets').select_option('1');page.wait_for_function("!document.querySelector('#feedback').disabled")
        page.goto(link.replace('frame=1','frame=999'));page.wait_for_function("document.querySelector('#error').textContent.includes('outside')")
        check(page.locator('#canvas').evaluate('(c)=>c.width')==0,'bad deep link fails closed')
        page.locator('#assets').select_option('2');page.wait_for_function("!document.querySelector('#feedback').disabled")
        check(not errors,'no browser script errors')
        check(page.evaluate('localStorage.length')==0,'viewer writes no localStorage')
        browser.close()
    server.shutdown();server.server_close()
args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps({'passed':True,'checks':checks,'scope':'actual headless Chromium controls; synthetic fixtures, not aesthetic approval or hosted-device QA'},indent=2)+'\n')
print(args.report.read_text())
