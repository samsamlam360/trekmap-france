"""Real browser regression for checklist typing and private per-day preparation.

No real authentication, Neon writes, or third-party calls: the plan API is
intercepted in the isolated Chrome test page.
"""
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE=os.environ.get("TREKMAP_BROWSER_BASE","http://127.0.0.1:10000")
options=Options()
for arg in ("--headless=new","--no-sandbox","--disable-dev-shm-usage","--window-size=1440,900"):
    options.add_argument(arg)
driver=webdriver.Chrome(options=options)
try:
    driver.get(BASE+"/")
    wait=WebDriverWait(driver,20)
    wait.until(lambda d:d.execute_script("return !!window.TrekMapJourneyPlanner && document.readyState==='complete'"))

    driver.execute_script("document.getElementById('tm-home')?.classList.add('tm-hidden')")
    # Real shortcut: only the km/day selector opens, not the entire advanced pane.
    toggle=wait.until(lambda d:d.find_element(By.ID,"tm-search-filter-toggle"))
    toggle.click()
    wait.until(lambda d:d.find_element(By.ID,"tm-inline-filters").is_displayed())
    button=wait.until(lambda d:d.find_element(By.ID,"tm-inline-pace"))
    driver.execute_script("arguments[0].scrollIntoView({block:'nearest',inline:'center'})",button)
    visible=driver.execute_script("""
      let b=arguments[0],r=b.getBoundingClientRect(),nav=b.closest('#tm-inline-filters');
      let s=getComputedStyle(b),n=getComputedStyle(nav);
      let el=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);
      return {viewport:innerWidth,display:s.display,visibility:s.visibility,
        rect:{left:r.left,top:r.top,width:r.width,height:r.height},navDisplay:n.display,
        navWidth:nav.clientWidth,navScrollWidth:nav.scrollWidth,
        atPoint:el?.id||el?.className||el?.tagName};
    """,button)
    assert button.is_displayed() and visible["rect"]["width"]>=40, (
        f"Km/jour shortcut hidden from user: {visible}"
    )
    button.click()
    assert driver.find_element(By.ID,"tm-quick-pace-popover").is_displayed()
    assert not driver.execute_script(
        "return document.body.classList.contains('tm-inline-filters-open')"
    ), "Km/day shortcut opened every advanced filter"
    shortcut=driver.find_element(By.ID,"tm-quick-pace-select")
    from selenium.webdriver.support.ui import Select
    Select(shortcut).select_by_value("15-20")
    assert driver.execute_script("return document.getElementById('tm-daily-pace-filter').value")=="15-20"
    assert not driver.find_element(By.ID,"tm-quick-pace-popover").is_displayed()
    assert driver.execute_script("""
       const chips=document.getElementById('tm-journey-active-filters');
       const label=chips?.textContent||'';
       return chips?.parentElement===document.body && label.includes('Km / jour')
              && !label.includes('Avis : Toutes');
    """), "Filter chips should live up in the folded toolbar, without a fake Avis Toutes"
    old_top=driver.execute_script("return document.getElementById('tm-journey-active-filters').getBoundingClientRect().top")
    toggle.click()
    wait.until(lambda d:d.execute_script("return document.body.classList.contains('tm-filterstrip-closed')"))
    new_top=driver.execute_script("return document.getElementById('tm-journey-active-filters').getBoundingClientRect().top")
    assert new_top<old_top-25 and driver.find_element(By.ID,"tm-journey-active-filters").is_displayed(), (
       f"Active chips must move up when filters fold: expanded={old_top}, collapsed={new_top}"
    )
    driver.execute_script("""
      let select=document.getElementById('tm-daily-pace-filter');
      select.value='';select.dispatchEvent(new Event('change',{bubbles:true}));
    """)

    def verify_checklist_geometry(where):
        state=driver.execute_script("""
          const modal=document.getElementById('modal'),
            row=document.querySelector('#checklist .check-row'),
            cb=row.querySelector('input[type=checkbox]'),
            txt=row.querySelector('input[type=text]');
          const m=modal.getBoundingClientRect(),r=row.getBoundingClientRect(),
            c=cb.getBoundingClientRect(),t=txt.getBoundingClientRect();
          return {modalWidth:modal.clientWidth,modalScroll:modal.scrollWidth,
            rowWidth:row.clientWidth,rowScroll:row.scrollWidth,checkboxWidth:c.width,
            textWidth:t.width,modalLeft:m.left,modalRight:m.right,
            rowLeft:r.left,rowRight:r.right,textLeft:t.left,textRight:t.right};
        """)
        assert state["modalScroll"]<=state["modalWidth"]+3, f"{where}: horizontal modal overflow: {state}"
        assert state["rowScroll"]<=state["rowWidth"]+3, f"{where}: checklist row overflow: {state}"
        assert 17<=state["checkboxWidth"]<=28, f"{where}: checkbox stole available width: {state}"
        assert state["textWidth"]>=max(130,state["rowWidth"]*.52), f"{where}: text input squeezed: {state}"
        assert state["textLeft"]>=state["modalLeft"] and state["textRight"]<=state["modalRight"]+1, (
            f"{where}: checklist text editor outside dialog: {state}"
        )

    driver.execute_script("""
      document.getElementById('tm-home')?.classList.add('tm-hidden');
      currentUser={id:4321,username:'test'};
      allTreks=[{id:900001,name:'Test privé préparation',region:'Test',is_public:true,
        distance:39.3,duration_days:3,coords:[[45.0,2.0],[45.1,2.2]],difficulty:'medium'}];
      window.__planRecorded=null;
      const original=window.fetch.bind(window);
      window.fetch=function(input,init={}){
        const url=String(input);
        if(url.includes('/treks/900001/plan')){
          if((init.method||'GET').toUpperCase()==='PUT'){
            window.__planRecorded=JSON.parse(init.body);
            return Promise.resolve(new Response(JSON.stringify({message:'Plan enregistré'}),{
              status:200,headers:{'Content-Type':'application/json'}}));
          }
          return Promise.resolve(new Response(JSON.stringify(window.__planRecorded||{
            notes:'Anciennes notes',checklist:[{text:'Eau avant le départ',done:false}],
            days:[{day:2,water:'Source à vérifier',sleep:'Refuge prévu'}]
          }),{status:200,headers:{'Content-Type':'application/json'}}));
        }
        return original(input,init);
      };
      openDetail(900001);
    """)
    wait.until(lambda d:d.find_element(By.ID,"plan-detail").is_displayed())
    driver.find_element(By.ID,"plan-detail").click()
    wait.until(lambda d:d.find_element(By.ID,"tm-journey-days"))
    assert driver.find_element(By.CSS_SELECTOR,"#modal h2").text=="Préparer le trek", (
        "The trek fiche's real Préparer button did not open the planner"
    )
    verify_checklist_geometry("desktop")
    first=driver.find_element(By.CSS_SELECTOR,"#checklist .check-row input[type=text]")
    first.click()
    is_clickable=driver.execute_script("""
      const i=arguments[0],r=i.getBoundingClientRect(),x=r.left+r.width/2,y=r.top+r.height/2;
      const top=document.elementFromPoint(x,y);
      return {reachable:top===i||i.contains(top),blocker:top?.id||top?.className||top?.tagName,
              focused:document.activeElement===i,rect:{x,y,w:r.width,h:r.height}};
    """,first)
    assert is_clickable["reachable"] and is_clickable["focused"], (
        f"The fiche's checkbox text field is obstructed: {is_clickable}"
    )
    first.send_keys(Keys.END," et potabilité")
    assert first.get_attribute("value")=="Eau avant le départ et potabilité",first.get_attribute("value")
    driver.find_element(By.ID,"add-check").click()
    new=driver.find_elements(By.CSS_SELECTOR,"#checklist .check-row input[type=text]")[-1]
    new.send_keys("Ma réserve 2 litres")
    assert new.get_attribute("value")=="Ma réserve 2 litres"
    driver.find_element(By.CSS_SELECTOR,"#checklist .check-row input[type=checkbox]").click()
    assert "1 / 2" in driver.find_element(By.ID,"tm-journey-progress").text
    driver.find_element(By.CSS_SELECTOR,"#tm-journey-plan-tools button").click()
    assert len(driver.find_elements(By.CSS_SELECTOR,"#checklist .check-row"))>=5
    day2=driver.find_element(By.CSS_SELECTOR,'#tm-journey-days details[data-day="2"]')
    driver.execute_script("arguments[0].open=true",day2)
    water=day2.find_element(By.CSS_SELECTOR,'[data-day-field="water"]')
    assert water.get_attribute("value")=="Source à vérifier"
    water.send_keys(Keys.END," et débit")
    sleep=day2.find_element(By.CSS_SELECTOR,'[data-day-field="sleep"]')
    assert sleep.get_attribute("value")=="Refuge prévu"
    driver.find_element(By.ID,"save-plan").click()
    wait.until(lambda d:d.execute_script("return window.__planRecorded!==null"))
    body=driver.execute_script("return window.__planRecorded")
    assert any(x["text"]=="Eau avant le départ et potabilité" and x["done"] for x in body["checklist"])
    assert any(x["text"]=="Ma réserve 2 litres" for x in body["checklist"])
    assert body["days"][1]["water"]=="Source à vérifier et débit",body["days"]
    # The PUT fixture resolves asynchronously. Wait for save to close the
    # preceding modal before reopening the real fiche, as a human would.
    wait.until(lambda d:d.execute_script(
        "return document.getElementById('modal-backdrop').style.display==='none'"
    ))
    driver.execute_script("""
      allTreks=[{id:900001,name:'Test privé préparation',region:'Test',is_public:true,
        distance:39.3,duration_days:3,coords:[[45.0,2.0],[45.1,2.2]],difficulty:'medium'}];
      openDetail(900001);
    """)
    wait.until(lambda d:d.find_element(By.ID,"plan-detail").is_displayed())
    driver.find_element(By.ID,"plan-detail").click()
    wait.until(lambda d:d.find_element(By.ID,"tm-journey-days"))
    assert driver.find_element(By.CSS_SELECTOR,'#tm-journey-days details[data-day="2"] [data-day-field="water"]').get_attribute("value")=="Source à vérifier et débit"
    driver.set_window_size(390,844)
    verify_checklist_geometry("mobile")
    first=driver.find_element(By.CSS_SELECTOR,"#checklist .check-row input[type=text]")
    driver.execute_script("arguments[0].scrollIntoView()",first)
    first.send_keys(Keys.END," ok")
    assert first.get_attribute("value").endswith(" ok")
    assert driver.execute_script("return document.querySelector('#tm-journey-days').scrollWidth <= document.querySelector('#tm-journey-days').clientWidth+2")
    print("JOURNEY CHROME PASS: editable checklist, rehydration, templates, persisted day fields, responsive typing")
finally:
    driver.quit()
