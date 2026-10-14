"""Real Chromium smoke: TrekBrain workspace on desktop and mobile.

Runs against the local FastAPI process in GitHub Actions. No real route plan,
account creation, ORS requests, or writes to the production database.
"""
from __future__ import annotations

from pathlib import Path
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get("TREKMAP_BROWSER_BASE", "http://127.0.0.1:10000")
OUT = Path("trekmap-browser-checks")
OUT.mkdir(parents=True, exist_ok=True)

PLAN = {
    "title": "Vérification Chrome : boucle de contrôle",
    "region": "Zone de test",
    "duration_days": 2,
    "route_type": "Boucle",
    "start": {"name": "Départ", "lat": 45.18, "lon": 5.72},
    "end": {"name": "Retour", "lat": 45.18, "lon": 5.72},
    "route_preview": {
        "coords": [[45.18, 5.72], [45.19, 5.74], [45.18, 5.72]],
        "distance_km": 6.5, "fallback": False, "routing_mode": "ors",
    },
    "stages": [
        {"day": 1, "distance_km": 3.4, "from_name": "Départ", "to_name": "Repère"},
        {"day": 2, "distance_km": 3.1, "from_name": "Repère", "to_name": "Retour"},
    ],
    "logistics": {"nights_missing": 1, "nights_transfer_required": 0},
    "map_resources": {"coverage": {"water": "partial", "days_without_water": [2]}},
}
LONG_PREPARATION_PLAN = {
    **PLAN,
    "trip_readiness": {
        "version": 1, "status": "incomplete", "route_validated": True,
        "issues": [
            {"requirement": "water", "days": [1, 2],
             "detail": "Points d'eau potable encore à confirmer pour chaque journée de marche."},
            {"requirement": "food", "days": [1, 2],
             "detail": "Ravitaillement à organiser et horaires des commerces à vérifier avant le départ."},
            {"requirement": "accommodation", "days": [1],
             "detail": "Hébergement sans accès pédestre aller et retour confirmé depuis la fin d'étape."},
            {"requirement": "distance", "days": [2],
             "detail": "Distance de marche avec les accès à ajuster à l'objectif journalier demandé."},
            {"requirement": "objective", "days": [2],
             "detail": "Point de passage obligatoire encore absent du tracé proposé pour ce trek."},
            {"requirement": "transit", "days": [1, 2],
             "detail": "Accès en transport au départ et retour à confirmer avant de réserver."},
        ],
        "actions": [{"type": "edit_request", "label": "Modifier la requête",
                     "detail": "Adapter la durée et les étapes dans le formulaire de préparation."}],
    },
}

options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-gpu")
options.add_argument("--window-size=1440,900")
options.page_load_strategy = "eager"

driver = webdriver.Chrome(options=options)
try:
    driver.set_page_load_timeout(45)
    driver.get(BASE + "/")
    wait = WebDriverWait(driver, 25)
    wait.until(lambda d: d.execute_script("return document.readyState === 'complete'"))
    wait.until(lambda d: d.execute_script(
        "return !!(document.getElementById('map') && window.TrekBrainMapWorkspace && "
        "typeof window.TrekBrainMapWorkspace.open === 'function')"
    ))
    # A real user enters the Explorer before opening TrekBrain. Opening the
    # workspace programmatically from the landing page is not a valid journey:
    # the homepage is intentionally above the map (z-index 15000).
    home = driver.find_element(By.ID, "tm-home")
    if home.is_displayed():
        entries = [x for x in driver.find_elements(By.CSS_SELECTOR, "[data-home-explore]")
                   if x.is_displayed()]
        assert entries, "Homepage has no visible Explorer entry"
        entries[0].click()
        wait.until(lambda d: "tm-hidden" in d.find_element(By.ID, "tm-home").get_attribute("class").split())
    assert not home.is_displayed(), "Explorer navigation did not close homepage"
    assert driver.find_element(By.ID, "map").is_displayed(), "Main hiking map is hidden"

    # Sitewide UX: exercise the original actions with native Chromium clicks.
    # No mutations to the live database, no account registration, no AI calls.
    assert driver.find_element(By.ID, "trekmap-sitewide-ux-css"), (
        "Sitewide UX stylesheet was not assembled into the served HTML"
    )
    search = driver.find_element(By.ID, "tm-main-search")
    search.click()
    search.send_keys("Vercors")
    assert search.get_attribute("value") == "Vercors", "Header search cannot receive typing"
    driver.find_element(By.ID, "tm-main-search-clear").click()
    assert search.get_attribute("value") == "", "Search clear action is broken"

    filter_button = driver.find_element(By.ID, "tm-filter-toggle")
    filters = driver.find_element(By.CSS_SELECTOR, "#sidebar .filters")
    was_collapsed = "tm-collapsed" in filters.get_attribute("class").split()
    filter_button.click()
    wait.until(lambda d: ("tm-collapsed" in filters.get_attribute("class").split()) != was_collapsed)
    filter_button.click()
    wait.until(lambda d: ("tm-collapsed" in filters.get_attribute("class").split()) == was_collapsed)

    drawer_button = driver.find_element(By.ID, "tm-drawer-head")
    drawer = driver.find_element(By.ID, "tm-unified-drawer")
    prior = "collapsed" in drawer.get_attribute("class").split()
    drawer_button.click()
    wait.until(lambda d: ("collapsed" in drawer.get_attribute("class").split()) != prior)
    drawer_button.click()
    wait.until(lambda d: ("collapsed" in drawer.get_attribute("class").split()) == prior)

    map_options = driver.find_element(By.ID, "tm-map-options")
    options_panel = driver.find_element(By.ID, "tm-map-options-panel")
    map_options.click()
    wait.until(lambda d: "tm-show" in options_panel.get_attribute("class").split())
    map_options.click()
    wait.until(lambda d: "tm-show" not in options_panel.get_attribute("class").split())

    topbar_layout = driver.execute_script(
        "const s=document.getElementById('tm-main-search-wrap').getBoundingClientRect();"
        "const b=document.getElementById('tm-ai-launch').getBoundingClientRect();"
        "return {searchRight:s.right,brainLeft:b.left,brainRight:b.right,"
        "viewport:innerWidth};"
    )
    assert topbar_layout["brainLeft"] >= topbar_layout["searchRight"] - 1, (
        f"Desktop search overlaps TrekBrain button: {topbar_layout}"
    )
    assert topbar_layout["brainRight"] <= topbar_layout["viewport"], (
        f"TrekBrain button out of desktop viewport: {topbar_layout}"
    )
    # Import, create, favorites and profile remain functional for a visitor:
    # clicking should open the existing login dialog, never a dead button.
    for action_id in ("tm-import-btn", "tm-create-btn",
                      "tm-favorites-btn", "tm-account-btn"):
        control = driver.find_element(By.ID, action_id)
        control.click()
        wait.until(lambda d: d.find_element(By.ID, "modal-backdrop").is_displayed())
        driver.execute_script("closeModal();")
        wait.until(lambda d: not d.find_element(By.ID, "modal-backdrop").is_displayed())

    ai_launcher = driver.find_element(By.ID, "tm-ai-launch")
    ai_launcher.click()
    wait.until(lambda d: d.find_element(By.ID, "tm-ai-overlay").is_displayed())
    assert driver.find_element(By.ID, "tm-ai-prompt").is_displayed()
    driver.find_element(By.ID, "tm-ai-close").click()
    wait.until(lambda d: not d.find_element(By.ID, "tm-ai-overlay").is_displayed())
    driver.save_screenshot(str(OUT / "sitewide-desktop-actions.png"))

    # Reproduce desktop carousel bugs without creating records in Neon or CI DB.
    # Only in-memory browser data is used: original JS still opens the real modal.
    driver.execute_script(
        "for(let i=0;i<14;i++)allTreks.push({id:910000+i,"
        "name:'Randonnée de contrôle '+i,region:'Auvergne',"
        "description:'Circuit de contrôle sans écriture en base',"
        "distance:12+i,elevation:320+i*10,difficulty:'easy',"
        "duration_days:2,is_public:true,coords:[[45.1,3.0+i*.02],[45.13,3.05+i*.02]]});"
        "document.getElementById('tm-main-search').dispatchEvent(new Event('input',{bubbles:true}));"
    )
    wait.until(lambda d: len(d.find_elements(
        By.CSS_SELECTOR, '#tm-drawer-track .tm-trek-tile')) >= 14)
    logo=driver.find_element(By.CSS_SELECTOR, '#tm-brand .tm-brand-mark img')
    wait.until(lambda d: d.execute_script(
        "return document.querySelector('#tm-brand .tm-brand-mark img').naturalWidth>0"))
    assert logo.get_attribute('src').endswith('/brand-pin.svg'), "Wrong header logo"
    info=driver.find_element(By.ID, 'tm-desktop-info')
    assert info.is_displayed(), "Selected-trek information panel hidden on desktop"
    right=driver.execute_script(
        "return document.getElementById('tm-desktop-info').getBoundingClientRect().right")
    assert right<=1440, "Information panel leaves screen"
    next_button=driver.find_element(By.CSS_SELECTOR, '.tm-drawer-nav [data-scroll-dir="1"]')
    assert next_button.is_enabled(), "Desktop carousel cannot move right"
    next_button.click()
    track=driver.find_element(By.ID,'tm-drawer-track')
    wait.until(lambda d: d.execute_script(
        "return document.getElementById('tm-drawer-track').scrollLeft>100"))
    card=driver.find_element(By.CSS_SELECTOR, '#tm-drawer-track .tm-trek-tile:nth-child(5)')
    name=card.find_element(By.TAG_NAME,'strong').text
    card_id=card.get_attribute('data-id')
    card.click()
    wait.until(lambda d: d.find_element(By.ID,'modal-backdrop').is_displayed())
    assert name in driver.find_element(By.ID,'modal').text, "Card click opened the wrong trek"
    assert name in info.text, "Side panel did not update to chosen trek"
    assert 'selected' in driver.find_element(
        By.CSS_SELECTOR, f'#tm-drawer-track .tm-trek-tile[data-id="{card_id}"]'
    ).get_attribute('class'), "Selected card lost its highlight"
    driver.find_element(By.ID,'modal-close').click()
    wait.until(lambda d: not d.find_element(By.ID,'modal-backdrop').is_displayed())
    panel_open=driver.find_element(By.ID,'tm-info-open-detail')
    panel_open.click()
    wait.until(lambda d: d.find_element(By.ID,'modal-backdrop').is_displayed())
    driver.find_element(By.ID,'modal-close').click()
    wait.until(lambda d: not d.find_element(By.ID,'modal-backdrop').is_displayed())
    # Actual pointer hover without a button pressed must not deactivate clicks.
    driver.execute_script(
        "let track=document.getElementById('tm-drawer-track');"
        "track.dispatchEvent(new PointerEvent('pointermove',{bubbles:true,pointerType:'mouse',"
        "clientX:880,clientY:750,buttons:0,pointerId:6}));")
    card=driver.find_element(By.CSS_SELECTOR, '#tm-drawer-track .tm-trek-tile:nth-child(6)')
    second=card.find_element(By.TAG_NAME,'strong').text
    card.click()
    wait.until(lambda d: d.find_element(By.ID,'modal-backdrop').is_displayed())
    assert second in driver.find_element(By.ID,'modal').text, "Hover movement blocked second trek"
    driver.find_element(By.ID,'modal-close').click()
    wait.until(lambda d: not d.find_element(By.ID,'modal-backdrop').is_displayed())
    driver.save_screenshot(str(OUT / "desktop-carrousel-and-selection.png"))
    # Preserve the original mobile navigation and hide only desktop helper panel.
    driver.set_window_size(390, 844)
    mobile_navigation = driver.find_element(By.ID, "tm-mobile-nav")
    assert mobile_navigation.is_displayed(), "Mobile navigation is hidden"
    mobile_filters = mobile_navigation.find_element(By.CSS_SELECTOR, '[data-mobile-action="filters"]')
    mobile_filters.click()
    wait.until(lambda d: "tm-mobile-filters-open" in
               d.find_element(By.TAG_NAME, "body").get_attribute("class").split())
    driver.find_element(By.ID, "tm-filter-toggle").click()
    wait.until(lambda d: "tm-mobile-filters-open" not in
               d.find_element(By.TAG_NAME, "body").get_attribute("class").split())
    mobile_ai = mobile_navigation.find_element(By.CSS_SELECTOR, '[data-mobile-action="ai"]')
    mobile_ai.click()
    wait.until(lambda d: d.find_element(By.ID, "tm-ai-overlay").is_displayed())
    driver.find_element(By.ID, "tm-ai-close").click()
    wait.until(lambda d: not d.find_element(By.ID, "tm-ai-overlay").is_displayed())
    driver.save_screenshot(str(OUT / "sitewide-mobile-actions.png"))
    driver.set_window_size(1440, 900)

    def open_and_check(label: str, width: int, height: int, plan=PLAN):
        driver.set_window_size(width, height)
        opened = driver.execute_script(
            "return window.TrekBrainMapWorkspace.open(arguments[0]);", plan
        )
        assert opened is True, f"{label}: valid synthetic hike rejected"
        active = driver.execute_script(
            "return window.TrekBrainMapWorkspace.isActive() && "
            "document.body.classList.contains('tm-brain-route-mode');"
        )
        assert active, f"{label}: map workspace did not open"
        panel = driver.find_element(By.ID, "tm-brain-route-panel")
        assert panel.is_displayed(), f"{label}: route panel hidden"
        assert "Vérification Chrome" in panel.text, f"{label}: stages not rendered"
        rect = driver.execute_script(
            "const r=document.getElementById('tm-brain-route-panel').getBoundingClientRect();"
            "return {left:r.left,right:r.right,width:innerWidth};"
        )
        assert rect["right"] > 0 and rect["left"] < rect["width"], (
            f"{label}: route sheet entirely outside viewport: {rect}"
        )
        driver.save_screenshot(str(OUT / (label + ".png")))
        return panel

    panel = open_and_check("desktop-1440", 1440, 900)
    # Every existing day can open the *same* editing dialog, preserving the
    # original map, data and save/export controls until regeneration.
    edit_day = wait.until(lambda d: d.find_element(
        By.CSS_SELECTOR, '#tm-brain-route-panel [data-tm-adjust-day="1"]'
    ))
    edit_day.click()
    wait.until(lambda d: d.find_element(By.ID, "tm-ai-overlay").is_displayed())
    assert "étape 1" in driver.find_element(By.ID, "tm-ai-prompt").get_attribute("value"), (
        "Day edit did not prepare an editable TrekBrain request"
    )
    driver.find_element(By.ID, "tm-ai-close").click()
    wait.until(lambda d: not d.find_element(By.ID, "tm-ai-overlay").is_displayed())
    driver.execute_script("window.TrekBrainMapWorkspace.exit();")
    assert not driver.execute_script(
        "return document.body.classList.contains('tm-brain-route-mode');"
    ), "Desktop exit did not restore explorer"

    panel = open_and_check("mobile-390", 390, 844)
    expand = panel.find_elements(By.CSS_SELECTOR, '[data-workspace-action="expand"]')
    assert expand, "Phone route steps cannot be expanded"
    expand[0].click()
    assert "expanded" in panel.get_attribute("class").split(), (
        "Phone expand did not reveal stage list"
    )
    driver.execute_script("window.TrekBrainMapWorkspace.exit();")
    assert not driver.execute_script(
        "return window.TrekBrainMapWorkspace.isActive();"
    ), "Phone exit left route mode active"
    assert not panel.is_displayed(), "Route panel remains on phone after exit"

    # Many unmet needs must remain readable on a short phone, without the
    # always-visible action footer covering the native expand click target.
    for width in (390, 320):
        label = f"mobile-long-preparation-{width}"
        panel = open_and_check(label, width, 640, LONG_PREPARATION_PLAN)
        layout = driver.execute_script(
            "const p=document.getElementById('tm-brain-route-panel');"
            "const c=p.querySelector('.tm-brain-content');"
            "const a=p.querySelector('.tm-brain-actions');"
            "const pr=p.getBoundingClientRect(), cr=c.getBoundingClientRect(), ar=a.getBoundingClientRect();"
            "return {scrolls:c.scrollHeight>c.clientHeight, overlap:cr.bottom>ar.top+1,"
            "footerInside:ar.bottom<=pr.bottom+1, separate:!c.contains(a)};"
        )
        assert layout["scrolls"], f"{label}: long preparation does not have a scrollable body"
        assert layout["separate"] and not layout["overlap"] and layout["footerInside"], (
            f"{label}: footer overlaps or leaves the available route panel: {layout}"
        )
        expand = panel.find_element(By.CSS_SELECTOR, '[data-workspace-action="expand"]')
        expand.click()
        assert "expanded" in panel.get_attribute("class").split(), (
            f"{label}: native expand click cannot reveal the stage list"
        )
        # The expanded CSS class is synchronous, but Chromium may still be
        # applying the responsive slide/scroll layout on a short viewport.
        # Wait for actual visibility instead of failing on a transient frame.
        # Do not weaken the assertion: a permanently hidden list still fails.
        wait.until(lambda d: d.find_element(By.ID, "tm-brain-route-detail").is_displayed())
        assert panel.find_element(By.ID, "tm-brain-route-detail").is_displayed(), (
            f"{label}: expanded stage list is hidden"
        )
        expand.click()
        assert "expanded" not in panel.get_attribute("class").split(), (
            f"{label}: native collapse click cannot fold the stage list"
        )
        driver.save_screenshot(str(OUT / (label + "-after-click.png")))
        driver.execute_script("window.TrekBrainMapWorkspace.exit();")
    print("REAL CHROME: desktop 1440x900, mobile 390x844 and short phones 390/320x640; "
          "route/map, long preparation scroll, native expand/collapse, exit, explorer restore PASS")
finally:
    driver.quit()
