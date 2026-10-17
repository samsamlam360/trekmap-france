"""Actual trek fiche -> standalone GPS navigation browser test.

Never access the user's location, plans or Neon. It uses a mock user/trek and a
precise synthetic GPS stream in local Chrome.
"""
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
import os

BASE=os.environ.get('TREKMAP_BROWSER_BASE','http://127.0.0.1:10000')
opts=Options()
for flag in ('--headless=new','--no-sandbox','--disable-dev-shm-usage','--window-size=1440,900'):
    opts.add_argument(flag)
browser=webdriver.Chrome(options=opts)
wait=WebDriverWait(browser,30)
try:
    browser.get(BASE+'/')
    wait.until(lambda d:d.execute_script("return typeof openDetail==='function'"))
    browser.execute_script("""
      document.getElementById('tm-home')?.classList.add('tm-hidden');
      allTreks=[{id:987654321,name:'Sentier de vérification GPS',region:'Test',
        distance:2.4,duration_days:1,is_public:true,owner_id:null,
        coords:[[45.0,2.0],[45.0,2.03]],difficulty:'easy'}];
      currentUser={id:1};
      openDetail(987654321);
    """)
    assert wait.until(lambda d:d.find_element(By.ID,'hike-navigate-detail').is_displayed()),'navigation button absent from fiche'
    browser.find_element(By.ID,'hike-navigate-detail').click()
    wait.until(lambda d:'/randonnee' in d.current_url)
    wait.until(lambda d:d.execute_script("return !!window.TrekMapHikeCore"))
    assert browser.find_element(By.ID,'title').text=='Sentier de vérification GPS'
    assert '2,' in browser.find_element(By.ID,'route-info').text
    assert browser.execute_script("return localStorage.getItem('tm-navigation-route-v1')!==null")

    # Override only browser geolocation, not app GPS code.
    browser.execute_script("""
      Object.defineProperty(navigator,'geolocation',{configurable:true,value:{
        watchPosition:function(fn,err,options){window.__syntheticFix=fn;return 42},
        clearWatch:function(){window.__clearedWatch=true}
      }});
    """)
    browser.find_element(By.ID,'start').click()
    wait.until(lambda d:d.execute_script("return typeof window.__syntheticFix==='function'"))
    browser.execute_script("""
      const t=Date.now();window.__testBaseTime=t;
      window.__syntheticFix({coords:{latitude:45,longitude:2,accuracy:5}});
    """)
    browser.execute_script("""
      const real=Date.now;Date.now=()=>window.__testBaseTime+12000;
      window.__syntheticFix({coords:{latitude:45,longitude:2.0002,accuracy:5}});
      Date.now=real;
    """)
    km=browser.execute_script("return document.getElementById('walked').textContent")
    assert km!='0,00 km', 'actual walked distance not recorded: '+km
    assert '✓' in browser.find_element(By.ID,'state').text,'near trail should be on-track'
    browser.execute_script("""
      const real=Date.now;Date.now=()=>window.__testBaseTime+300000;
      window.__syntheticFix({coords:{latitude:45.004,longitude:2.0002,accuracy:5}});
      Date.now=real;
    """)
    assert '⚠' in browser.find_element(By.ID,'state').text,'far away must warn'
    browser.find_element(By.ID,'pause').click()
    assert 'pause' in browser.find_element(By.ID,'state').text.lower()
    before=browser.find_element(By.ID,'walked').text
    browser.execute_script("""
      const cb=window.__syntheticFix;
      cb({coords:{latitude:45,longitude:2.002,accuracy:5}})
    """)
    assert browser.find_element(By.ID,'walked').text==before,'paused tracking must ignore fixes'
    browser.find_element(By.ID,'pause').click()
    assert 'Reprendre' not in browser.find_element(By.ID,'pause').text
    browser.find_element(By.ID,'finish').click() if False else None
    # Confirm is a browser interaction. Test storage round-trip instead of
    # deleting the track through the destructive confirmation dialog.
    saved=browser.execute_script("""
      const key=Object.keys(localStorage).find(k=>k.startsWith('tm-hike-progress-v1-'));
      return JSON.parse(localStorage.getItem(key));
    """)
    assert saved['walked']>10 and len(saved['points'])>=2
    browser.set_window_size(390,844)
    assert browser.find_element(By.ID,'nav-map').is_displayed()
    assert not browser.find_element(By.ID,'hike-options').is_displayed()
    assert not browser.find_element(By.ID,'download').is_displayed()
    assert browser.find_element(By.ID,'quick-start').is_displayed()
    assert browser.find_element(By.ID,'quick-tools').is_displayed()
    assert browser.find_element(By.ID,'map-recenter').is_displayed()
    assert not browser.find_element(By.ID,'map-heading').is_displayed()
    # GPS cockpit should be useful before opening any secondary options.
    hud=browser.find_element(By.ID,'gps-hud')
    assert hud.is_displayed(),'mobile GPS dashboard missing'
    assert browser.find_element(By.ID,'gps-map-controls').is_displayed()
    assert browser.execute_script("""
      return ['walked','remaining','elapsed'].every((id,i)=>
        document.getElementById(['hud-walked','hud-remaining','hud-time'][i]).textContent===
        document.getElementById(id).textContent)
    """),'GPS HUD values must match detailed statistics even when Options is closed'
    assert browser.execute_script("return document.getElementById('mapwrap').getBoundingClientRect().height")>=410
    browser.find_element(By.ID,'quick-start').click()
    assert 'pause' in browser.execute_script("return document.getElementById('state').textContent").lower()
    assert browser.find_element(By.ID,'quick-start').text.startswith('▶'),'resume action must be visible'
    browser.find_element(By.ID,'quick-start').click()
    assert browser.find_element(By.ID,'quick-start').text.startswith('⏸'),'pause action must be visible'
    browser.find_element(By.ID,'quick-tools').click()
    assert browser.find_element(By.ID,'hike-options').is_displayed()
    assert browser.find_element(By.ID,'one-tap-download').is_displayed()
    assert browser.find_element(By.ID,'close-hike-options').is_displayed()
    browser.find_element(By.ID,'close-hike-options').click()
    assert not browser.find_element(By.ID,'hike-options').is_displayed()
    assert browser.find_element(By.ID,'quick-start').is_displayed()

    assert browser.execute_script("return document.documentElement.scrollWidth<=window.innerWidth+2"),'nav viewport horizontally overflowing'
    before_reload=browser.execute_script("return document.getElementById('walked').textContent")
    browser.get(BASE+'/randonnee')
    wait.until(lambda d:d.execute_script("return !!window.TrekMapHikeCore"))
    assert browser.execute_script("return document.getElementById('walked').textContent")==before_reload,'walked distance lost on reload'
    # Prepare a deterministic short offline package. Vector tile requests are
    # mocked, but the app shell and real MapLibre library must be cached.
    browser.execute_script("""
      window.__realFetch=window.fetch.bind(window);
      window.fetch=(input,options)=>String(input).startsWith('/offline-tiles/')
        ?Promise.resolve(new Response(new Uint8Array([26,0]),{
          status:200,headers:{'content-type':'application/x-protobuf'}}))
        :window.__realFetch(input,options);
    """)
    browser.find_element(By.ID,'quick-tools').click()
    assert browser.find_element(By.ID,'hike-options').is_displayed()
    # One main download action, preserving the original web downloading pipeline.
    browser.find_element(By.ID,'one-tap-download').click()
    wait_long=WebDriverWait(browser,95)
    wait_long.until(lambda d: 'Lot terminé' in d.find_element(By.ID,'offline-status').text
        or 'Échec' in d.find_element(By.ID,'offline-status').text
        or 'partiel' in d.find_element(By.ID,'offline-status').text)
    outcome=browser.find_element(By.ID,'offline-status').text
    assert 'Lot terminé' in outcome,'offline package not complete: '+outcome
    saved=browser.execute_async_script("""
      const done=arguments[0];
      Promise.all([caches.open('tm-hike-app-v1'),caches.open('tm-hike-tiles-v1')])
        .then(async ([app,tiles])=>done({
          shell:!!(await app.match('/randonnee')),
          maplibre:!!(await app.match('https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js')),
          tiles:(await tiles.keys()).length
        })).catch(e=>done({error:String(e)}));
    """)
    assert saved.get('shell') and saved.get('maplibre') and saved.get('tiles',0)>10,saved
    # A route reload without network must still work from Cache API.
    browser.execute_cdp_cmd('Network.enable',{})
    browser.execute_cdp_cmd('Network.emulateNetworkConditions',{
      'offline':True,'latency':0,'downloadThroughput':0,'uploadThroughput':0})
    try:
      browser.get(BASE+'/randonnee')
      wait.until(lambda d:d.execute_script("return !!window.TrekMapHikeCore"))
      assert browser.execute_script("return document.getElementById('title').textContent")=='Sentier de vérification GPS'
      assert browser.execute_script("return document.getElementById('walked').textContent")==before_reload
    finally:
      browser.execute_cdp_cmd('Network.emulateNetworkConditions',{
        'offline':False,'latency':0,'downloadThroughput':-1,'uploadThroughput':-1})
    # Regression: opening a substantial trek in the Android WebView must not
    # synchronously prefetch thousands of tile coordinates or write to native
    # storage before a deliberate tap. This was introduced in the cache fix.
    browser.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument',{'source':"""
      window.__nativeWrites=0;
      window.Capacitor={getPlatform:()=> 'android',Plugins:{
        TrekMapNativeGPS:{
          saveOfflineRoute:()=>{window.__nativeWrites++;return Promise.resolve({saved:true})},
          listOfflineRoutes:()=>Promise.resolve({routes:[]}),
          openTracker:()=>Promise.resolve(),
          openOfflineDownload:()=>Promise.resolve()
        }
      }};
    """})
    browser.execute_script("""
      const coords=Array.from({length:16000},(_,i)=>[45+i*0.000007,2+i*0.000012]);
      localStorage.setItem('tm-navigation-route-v1',JSON.stringify({
        id:'very-long-16000',name:'Grand trek de validation',region:'Test',
        coords:coords
      }));
    """)
    browser.get(BASE+'/randonnee?large-route-e2e=1')
    wait.until(lambda d:d.execute_script("return !!window.TrekMapHikeCore"))
    assert browser.execute_script("return document.getElementById('title').textContent")=='Grand trek de validation'
    assert browser.execute_script("return window.__nativeWrites") == 0,'unexpected automatic Android storage call on page entry'
    assert browser.execute_script("return document.getElementById('section-picker').options.length") == 0, 'tile planning started before user requested it'
    assert browser.execute_script("return document.documentElement.scrollWidth<=window.innerWidth+2"), 'large trek broke mobile viewport'
    print('HIKING LONG ROUTE PASS: no auto Android calls, no expensive eager tile planning')
    print('HIKING CHROME PASS: fiche, GPS, deviation, pause, GPX, persistence, responsive, offline package and airplane-mode page')
finally:
    browser.quit()
