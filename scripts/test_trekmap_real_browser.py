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
from selenium.webdriver.support.ui import WebDriverWait, Select

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

    # The compact filter bar starts collapsed; its real toggle is beside search.
    bar = driver.find_element(By.ID, "tm-inline-filters")
    toggle = driver.find_element(By.ID, "tm-search-filter-toggle")
    assert toggle.is_displayed() and not bar.is_displayed()
    assert driver.find_element(By.ID, "trekmap-map-tools-v2-css"), "Missing final UI layer"
    toggle.click()
    wait.until(lambda d: bar.is_displayed())
    assert toggle.get_attribute("aria-expanded") == "true"
    assert Select(driver.find_element(By.ID, "tm-inline-difficulty")).first_selected_option.text == "Difficulté"
    assert not driver.find_element(By.CSS_SELECTOR, "#tm-desktop-info .tm-info-selected").is_displayed()
    assert driver.find_element(By.CSS_SELECTOR, "#tm-desktop-info .tm-info-overview").is_displayed()
    assert not driver.find_element(By.ID, "sidebar").is_displayed()

    layout = driver.execute_script(
        "const d=document.getElementById('tm-unified-drawer').getBoundingClientRect();"
        "const z=document.querySelector('.leaflet-left').getBoundingClientRect();"
        "const b=document.getElementById('tm-inline-filters').getBoundingClientRect();"
        "const s=document.getElementById('tm-main-search-wrap').getBoundingClientRect();"
        "const t=document.getElementById('tm-search-filter-toggle').getBoundingClientRect();"
        "return {drawerLeft:d.left,zoomLeft:z.left,quickTop:b.top,searchRight:s.right,"
        "toggleLeft:t.left,toggleRight:t.right,viewport:innerWidth};")
    assert layout["drawerLeft"] < 40 and layout["zoomLeft"] < 55, layout
    assert layout["quickTop"] > 70 and layout["toggleLeft"] >= layout["searchRight"] - 1, layout

    # These three popovers must contain ONLY their own source controls.
    for trigger, count, mode, source in [
        ("distance-range", 2, "Distance", "distance-range"),
        ("elevation-range", 2, "Dénivelé", "elevation-range"),
        ("duration-filter", 1, "Durée", "duration-filter")
    ]:
        driver.find_element(By.CSS_SELECTOR, f'[data-filter-target="{trigger}"]').click()
        panel = driver.find_element(By.ID, "tm-map-filter-popover")
        assert panel.is_displayed() and mode in panel.text
        assert len(panel.find_elements(By.CSS_SELECTOR, "input,select")) == count
        assert not driver.find_element(By.ID, "sidebar").is_displayed()
        if source != "duration-filter":
            value = "14" if source == "distance-range" else "350"
            driver.execute_script(
                "let x=document.querySelector('#tm-map-filter-popover input[type=range]');"
                "x.value=arguments[0];x.dispatchEvent(new Event('input',{bubbles:true}));", value)
            actual=driver.find_element(By.ID, source).get_attribute("value")
            popup_value=driver.execute_script(
                "return document.querySelector('#tm-map-filter-popover input[type=range]').value")
            # Existing sliders can define non-unit increments (e.g. 5 km);
            # the contextual slider must mirror the effective stepped value.
            assert actual == popup_value and float(actual) > 0, (
                f"{source}: input={value}, actual={actual}, popup={popup_value}")
        panel.find_element(By.CSS_SELECTOR, ".tm-mini-dismiss").click()
        assert not panel.is_displayed()

    # Both new inline categories control the ORIGINAL selects.
    assert driver.find_element(By.ID, "tm-inline-sort").is_displayed()
    assert driver.find_element(By.ID, "tm-inline-route").is_displayed()
    assert driver.find_element(By.ID, "sort-filter").get_attribute("value") == (
        driver.find_element(By.ID, "tm-inline-sort").get_attribute("value"))
    assert driver.find_element(By.ID, "tm-route-filter").get_attribute("value") == (
        driver.find_element(By.ID, "tm-inline-route").get_attribute("value"))

    # CI PostGIS can have an empty region catalogue: simulate async population.
    quick_region = driver.find_element(By.ID, "tm-inline-region")
    if len(Select(quick_region).options) <= 1:
        driver.execute_script("document.getElementById('region-filter').add("
                              "new Option('Région test CI','region-test-ci'))")
    wait.until(lambda d: len(Select(quick_region).options) > 1)
    first_region = next((o.get_attribute("value") for o in Select(quick_region).options
                         if o.get_attribute("value")), None)
    assert first_region
    Select(quick_region).select_by_value(first_region)
    wait.until(lambda d: d.find_element(By.ID, "region-filter").get_attribute("value") == first_region)
    Select(quick_region).select_by_value("")
    wait.until(lambda d: d.find_element(By.ID, "region-filter").get_attribute("value") == "")
    # Restore untouched defaults before checking the independent map scenarios.
    driver.execute_script("resetFilters();")
    toggle.click()
    wait.until(lambda d: not bar.is_displayed())
    toggle.click()
    wait.until(lambda d: bar.is_displayed())
    assert toggle.get_attribute("aria-expanded") == "true"

    drawer_button = driver.find_element(By.ID, "tm-drawer-head")
    drawer = driver.find_element(By.ID, "tm-unified-drawer")
    prior = "collapsed" in drawer.get_attribute("class").split()
    drawer_button.click()
    wait.until(lambda d: ("collapsed" in drawer.get_attribute("class").split()) != prior)
    drawer_button.click()
    wait.until(lambda d: ("collapsed" in drawer.get_attribute("class").split()) == prior)

    # Reused zoom links and real Carte action now share one compact dock.
    dock = driver.find_element(By.ID, "tm-map-control-dock")
    assert dock.is_displayed(), "Unified map-controls dock is hidden"
    zoom_in = dock.find_element(By.CSS_SELECTOR, ".leaflet-control-zoom-in")
    zoom_out = dock.find_element(By.CSS_SELECTOR, ".leaflet-control-zoom-out")
    assert zoom_in.is_displayed() and zoom_out.is_displayed()
    assert dock.find_element(By.ID, "tm-map-options").is_displayed()
    dock_geometry = driver.execute_script(
        "let d=document.getElementById('tm-map-control-dock').getBoundingClientRect(),"
        "a=document.querySelector('#tm-map-control-dock .leaflet-control-zoom').getBoundingClientRect(),"
        "b=document.getElementById('tm-map-options').getBoundingClientRect();"
        "return {left:d.left,top:d.top,right:d.right,zoomLeft:a.left,buttonLeft:b.left,"
        "zoomBottom:a.bottom,buttonTop:b.top,buttonRight:b.right};")
    assert 0 <= dock_geometry["left"] < 48 and dock_geometry["top"] > 75, dock_geometry
    assert dock_geometry["zoomBottom"] < dock_geometry["buttonTop"], dock_geometry
    assert dock_geometry["buttonRight"] <= dock_geometry["right"] + 1, dock_geometry
    driver.execute_script("map.setZoom(7, {animate:false})")
    wait.until(lambda d: d.execute_script("return map.getZoom()===7 && !map._animatingZoom"))
    zoom_in.click()
    wait.until(lambda d: d.execute_script("return map.getZoom()===8 && !map._animatingZoom"),
               message="Leaflet + did not zoom with the grouped native control")
    zoom_out.click()
    wait.until(lambda d: d.execute_script("return map.getZoom()===7 && !map._animatingZoom"),
               message="Leaflet - did not zoom with the grouped native control")
    map_options = driver.find_element(By.ID, "tm-map-options")
    options_panel = driver.find_element(By.ID, "tm-map-options-panel")
    map_options.click()
    wait.until(lambda d: "tm-show" in options_panel.get_attribute("class").split())
    map_options.click()
    wait.until(lambda d: "tm-show" not in options_panel.get_attribute("class").split())

    # Fullscreen must be useful: a genuine focus mode with controls and a
    # reversible trek drawer, not fullscreening the bare Leaflet canvas.
    zoom_before = driver.execute_script("return map.getZoom()")
    map_options.click()
    fullscreen_option = driver.find_element(
        By.CSS_SELECTOR, '[data-map-action="fullscreen"]')
    assert "Mode carte" in fullscreen_option.text
    fullscreen_option.click()
    wait.until(lambda d: d.execute_script("return window.TrekMapImmersive.isActive()"))
    assert not driver.find_element(By.ID, "tm-unified-topbar").is_displayed()
    assert not driver.find_element(By.ID, "tm-unified-drawer").is_displayed()
    assert driver.find_element(By.ID, "tm-map-control-dock").is_displayed()
    assert driver.find_element(By.ID, "tm-map-immersive-exit").is_displayed()
    immersive_geometry=driver.execute_script(
        "const a=document.getElementById('map').getBoundingClientRect();"
        "return {top:a.top,bottom:a.bottom,width:a.width,screen:innerHeight,"
        "zoom:map.getZoom(),fullscreen:document.fullscreenElement?.id||null}")
    assert immersive_geometry["top"] <= 1 and immersive_geometry["bottom"] >= immersive_geometry["screen"]-1, immersive_geometry
    assert immersive_geometry["zoom"] == zoom_before, immersive_geometry
    immersive_list=driver.find_element(By.ID, "tm-map-immersive-list")
    immersive_list.click()
    wait.until(lambda d: d.find_element(By.ID, "tm-unified-drawer").is_displayed())
    assert driver.execute_script("return window.TrekMapImmersive.isListOpen()")
    # The bottom carrousel chevron must REALLY collapse to its 44px header,
    # without moving the header away from the bottom edge.
    immersive_head=driver.find_element(By.ID, "tm-drawer-head")
    immersive_head.click()
    wait.until(lambda d: "collapsed" in d.find_element(
        By.ID, "tm-unified-drawer").get_attribute("class").split())
    wait.until(lambda d: d.execute_script(
        "return document.getElementById('tm-unified-drawer').getBoundingClientRect().height<=46"))
    geometry=driver.execute_script(
        "let r=document.getElementById('tm-unified-drawer').getBoundingClientRect();"
        "return {top:r.top,bottom:r.bottom,height:r.height,viewport:innerHeight};")
    assert geometry["bottom"]>=geometry["viewport"]-17, geometry
    assert not driver.find_element(By.ID, "tm-drawer-track").is_displayed(), (
        "The collapsed drawer must hide its card list")
    immersive_head.click()
    wait.until(lambda d: "collapsed" not in d.find_element(
        By.ID, "tm-unified-drawer").get_attribute("class").split())
    wait.until(lambda d: d.execute_script(
        "return document.getElementById('tm-unified-drawer').getBoundingClientRect().height>100"))
    assert driver.find_element(By.ID, "tm-drawer-track").is_displayed()
    immersive_list.click()
    wait.until(lambda d: not d.find_element(By.ID, "tm-unified-drawer").is_displayed())
    driver.find_element(By.ID, "tm-map-immersive-exit").click()
    wait.until(lambda d: not d.execute_script("return window.TrekMapImmersive.isActive()"))
    assert driver.find_element(By.ID, "tm-unified-topbar").is_displayed()
    assert driver.find_element(By.ID, "tm-unified-drawer").is_displayed()
    assert driver.execute_script("return map.getZoom()") == zoom_before

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
    scenic=driver.find_elements(By.CSS_SELECTOR, '#tm-drawer-track .tm-tile-landscape')
    assert len(scenic) >= 14 and scenic[0].is_displayed(), (
        "Desktop trek cards should display landscape previews"
    )
    previews=driver.find_elements(By.CSS_SELECTOR, "#tm-drawer-track .tm-mini-route")
    assert len(previews)>=14, "Each trek with valid geometry needs a route preview"
    wait.until(lambda d: d.execute_script(
        "return !!window.TrekMapExplorerFocus && window.TrekMapExplorerFocus.getLayerCount()>=14"))
    # At low zoom nearby routes are grouped into numbered Leaflet markers.
    driver.execute_script("map.setView([45.115,3.2],6);window.TrekMapClusters.refresh();")
    wait.until(lambda d: d.execute_script(
        "return window.TrekMapClusters.getTotal()>=14 && "
        "window.TrekMapClusters.getCounts().some(x=>x>1)"))
    counts = driver.execute_script("return window.TrekMapClusters.getCounts()")
    assert sum(counts) == 14, counts
    assert driver.execute_script("return window.TrekMapClusters.getMarkerCount()") < 14
    assert driver.execute_script(
        "return [...document.querySelectorAll('.tm-trek-cluster')].every("
        "n => Number(n.textContent) > 1)"), "There must never be a numbered singleton"
    assert driver.find_elements(By.CSS_SELECTOR, ".tm-cluster-enter .tm-trek-cluster"), (
        "Cluster badges should have entrance animation")
    # A lone trek must have a real line, not a decorative '1' badge.
    driver.execute_script(
        "window.__tmCIOriginalFiltered=filteredTreks;"
        "filteredTreks=filteredTreks.slice(0,1);window.TrekMapClusters.refresh();")
    wait.until(lambda d: d.execute_script(
        "return window.TrekMapClusters.getTotal()===1"))
    wait.until(lambda d: d.execute_script(
        "return window.TrekMapClusters.getMarkerCount()===0"))
    driver.execute_script(
        "filteredTreks=window.__tmCIOriginalFiltered;map.setZoom(12);"
        "window.TrekMapClusters.refresh();")
    wait.until(lambda d: d.execute_script(
        "return window.TrekMapClusters.getMarkerCount()===0"))


    # Hover the REAL fifth card and verify the map highlights its route.
    hover_card = driver.find_element(By.CSS_SELECTOR, '#tm-drawer-track .tm-trek-tile:nth-child(5)')
    hover_id = int(hover_card.get_attribute('data-id'))
    driver.execute_script("arguments[0].dispatchEvent(new PointerEvent('pointerover',"
                          "{bubbles:true,pointerType:'mouse'}))", hover_card)
    assert driver.execute_script("return window.TrekMapExplorerFocus.getFocused()") == hover_id
    assert driver.execute_script("return window.TrekMapExplorerFocus.getGlowLayerCount()") == 2
    driver.execute_script("arguments[0].dispatchEvent(new PointerEvent('pointerout',"
                          "{bubbles:true,pointerType:'mouse'}))", hover_card)
    assert driver.execute_script("return window.TrekMapExplorerFocus.getGlowLayerCount()") == 0
    actual_path=driver.execute_script(
        "return document.querySelector('#tm-drawer-track .tm-mini-route path').getAttribute('d')"
    )
    assert actual_path.startswith("M") and "L" in actual_path, "Route preview should use route geometry"
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
    # Ensure the target is fully visible within the horizontal carousel.
    # Selenium's default click scrolling may otherwise target a clipped
    # fragment outside the full-width drawer and hit the Leaflet canvas.
    driver.execute_script(
        "arguments[0].scrollIntoView({block:'nearest',inline:'center',behavior:'instant'})", card)
    wait.until(lambda d: d.execute_script(
        "const a=arguments[0].getBoundingClientRect();"
        "const b=document.getElementById('tm-drawer-track').getBoundingClientRect();"
        "return a.left>=b.left-1 && a.right<=b.right+1;", card))
    card.click()
    wait.until(lambda d: d.find_element(By.ID,'modal-backdrop').is_displayed())
    assert name in driver.find_element(By.ID,'modal').text, "Card click opened the wrong trek"
    assert name in info.text, "Side panel did not update to chosen trek"
    # The daily stages legend must sit at the left edge, BELOW the zoom/Carte
    # dock; previously it floated ~80px into the map and overlapped controls.
    wait.until(lambda d: d.find_elements(
        By.CSS_SELECTOR, ".leaflet-top.leaflet-left .tm-route-day-legend"))
    legend_layout = driver.execute_script(
        "const l=document.querySelector('.leaflet-top.leaflet-left .tm-route-day-legend')"
        ".getBoundingClientRect(),"
        "d=document.getElementById('tm-map-control-dock').getBoundingClientRect();"
        "return {left:l.left,top:l.top,right:l.right,dockBottom:d.bottom,"
        "dockLeft:d.left,width:innerWidth};")
    assert legend_layout["left"] < 35, legend_layout
    assert legend_layout["top"] >= legend_layout["dockBottom"] + 8, legend_layout
    assert legend_layout["right"] <= legend_layout["width"] - 10, legend_layout
    wait.until(lambda d: d.execute_script(
        "return window.TrekMapExplorerFocus.getSelected()===Number(arguments[0])", card_id))
    focus_diagnostics = driver.execute_script(
        "return {selected:window.TrekMapExplorerFocus.getSelected(),"
        "focused:window.TrekMapExplorerFocus.getFocused(),"
        "glow:window.TrekMapExplorerFocus.getGlowLayerCount(),"
        "mapLines:window.TrekMapExplorerFocus.getLayerCount(),"
        "allLayers:trekLayerGroup.getLayers().length,"
        "ids:trekLayerGroup.getLayers().slice(0,20).map(x=>x._tmTrekId),"
        "brain:document.body.classList.contains('tm-brain-route-mode')};")
    assert focus_diagnostics["glow"] == 2, (
        f"Selection should keep the active route highlighted: {focus_diagnostics}")
    assert not driver.find_element(By.CSS_SELECTOR, "#tm-desktop-info .tm-info-overview").is_displayed(), (
        "Redundant overview must disappear when a trek is selected")
    assert driver.find_element(By.CSS_SELECTOR, "#tm-desktop-info .tm-info-selected").is_displayed(), (
        "Real selected route info should appear")
    assert 'selected' in driver.find_element(
        By.CSS_SELECTOR, f'#tm-drawer-track .tm-trek-tile[data-id="{card_id}"]'
    ).get_attribute('class'), "Selected card lost its highlight"
    driver.find_element(By.ID,'modal-close').click()
    wait.until(lambda d: not d.find_element(By.ID,'modal-backdrop').is_displayed())
    panel_open=driver.find_element(By.ID,'tm-info-open-detail')
    panel_open.click()
    wait.until(lambda d: d.find_element(By.ID,'modal-backdrop').is_displayed())
    # Wait for the existing asynchronous detail enrichment before closing.
    # A delayed replacement could otherwise race the click on an old close node.
    wait.until(lambda d: d.find_elements(By.CSS_SELECTOR, '#modal .tm-detail-extra'))
    driver.find_element(By.ID,'modal-close').click()
    wait.until(lambda d: not d.find_element(By.ID,'modal-backdrop').is_displayed())
    # Regression: the detail modal is a sibling of #app. Native fullscreen of
    # #app hid it completely; fullscreening the document root keeps it visible.
    map_options.click()
    wait.until(lambda d: "tm-show" in options_panel.get_attribute("class").split())
    driver.find_element(By.CSS_SELECTOR, '[data-map-action="fullscreen"]').click()
    wait.until(lambda d: d.execute_script("return window.TrekMapImmersive.isActive()"))
    wait.until(lambda d: driver.find_element(By.ID, "tm-info-open-detail").is_displayed())
    driver.find_element(By.ID, "tm-info-open-detail").click()
    wait.until(lambda d: d.find_element(By.ID, "modal-backdrop").is_displayed())
    fullscreen_detail=driver.execute_script(
        "const f=document.fullscreenElement,b=document.getElementById('modal-backdrop');"
        "const r=b.getBoundingClientRect();"
        "return {native:f&&f.tagName,modalInTopLayer:!f||f.contains(b),"
        "modalVisible:getComputedStyle(b).display!=='none',height:r.height,"
        "modalText:document.getElementById('modal').textContent.slice(0,300)}")
    assert fullscreen_detail["modalInTopLayer"] and fullscreen_detail["modalVisible"] and (
        fullscreen_detail["height"]>100), fullscreen_detail
    assert name in fullscreen_detail["modalText"], fullscreen_detail
    driver.find_element(By.ID, "modal-close").click()
    wait.until(lambda d: not d.find_element(By.ID, "modal-backdrop").is_displayed())
    driver.find_element(By.ID, "tm-map-immersive-exit").click()
    wait.until(lambda d: not d.execute_script("return window.TrekMapImmersive.isActive()"))
    # Actual pointer hover without a button pressed must not deactivate clicks.
    driver.execute_script(
        "let track=document.getElementById('tm-drawer-track');"
        "track.dispatchEvent(new PointerEvent('pointermove',{bubbles:true,pointerType:'mouse',"
        "clientX:880,clientY:750,buttons:0,pointerId:6}));")
    card=driver.find_element(By.CSS_SELECTOR, '#tm-drawer-track .tm-trek-tile:nth-child(6)')
    second=card.find_element(By.TAG_NAME,'strong').text
    # Ensure the target is fully visible within the horizontal carousel.
    # Selenium's default click scrolling may otherwise target a clipped
    # fragment outside the full-width drawer and hit the Leaflet canvas.
    driver.execute_script(
        "arguments[0].scrollIntoView({block:'nearest',inline:'center',behavior:'instant'})", card)
    wait.until(lambda d: d.execute_script(
        "const a=arguments[0].getBoundingClientRect();"
        "const b=document.getElementById('tm-drawer-track').getBoundingClientRect();"
        "return a.left>=b.left-1 && a.right<=b.right+1;", card))
    card.click()
    wait.until(lambda d: d.find_element(By.ID,'modal-backdrop').is_displayed())
    assert second in driver.find_element(By.ID,'modal').text, "Hover movement blocked second trek"
    driver.find_element(By.ID,'modal-close').click()
    wait.until(lambda d: not d.find_element(By.ID,'modal-backdrop').is_displayed())
    # A click on empty Leaflet background must clear the trek but NOT its filters.
    driver.execute_script("map.fire('click',{sourceTarget:map,latlng:map.getCenter()});")
    wait.until(lambda d: d.execute_script("return window.TrekMapExplorerFocus.getSelected()===null"))
    assert driver.execute_script("return window.TrekMapExplorerFocus.getGlowLayerCount()") == 0
    assert driver.find_element(By.CSS_SELECTOR, "#tm-desktop-info .tm-info-overview").is_displayed()
    assert not driver.find_element(By.CSS_SELECTOR, "#tm-desktop-info .tm-info-selected").is_displayed()
    assert not driver.find_elements(By.CSS_SELECTOR, "#tm-drawer-track .tm-trek-tile.selected")
    driver.save_screenshot(str(OUT / "desktop-carrousel-and-selection.png"))
    # Preserve the original mobile navigation and hide only desktop helper panel.
    driver.set_window_size(390, 844)
    mobile_navigation = driver.find_element(By.ID, "tm-mobile-nav")
    assert mobile_navigation.is_displayed(), "Mobile navigation is hidden"
    assert driver.find_element(By.ID, "tm-map-control-dock").is_displayed(), (
        "The same existing map controls must remain usable on mobile")
    # Mobile focus must have a permanent exit and an optional trek drawer;
    # the standard bottom navigation must come back afterwards.
    driver.execute_script("window.TrekMapImmersive.enter()")
    wait.until(lambda d: d.execute_script("return window.TrekMapImmersive.isActive()"))
    assert driver.find_element(By.ID, "tm-map-immersive-exit").is_displayed()
    assert not mobile_navigation.is_displayed()
    driver.find_element(By.ID, "tm-map-immersive-list").click()
    wait.until(lambda d: d.find_element(By.ID, "tm-unified-drawer").is_displayed())
    driver.execute_script("document.dispatchEvent(new KeyboardEvent('keydown',"
                          "{key:'Escape',bubbles:true}))")
    wait.until(lambda d: not d.execute_script("return window.TrekMapImmersive.isActive()"))
    assert mobile_navigation.is_displayed()
    assert driver.find_element(By.ID, "tm-map-control-dock").is_displayed()
    mobile_filters = mobile_navigation.find_element(By.CSS_SELECTOR, '[data-mobile-action="filters"]')
    mobile_filters.click()
    wait.until(lambda d: "tm-mobile-filters-open" in
               d.find_element(By.TAG_NAME, "body").get_attribute("class").split())
    mobile_close = driver.find_element(By.ID, "tm-filter-toggle")
    mobile_info = driver.execute_script(
        "const t=document.getElementById('tm-filter-toggle'),"
        "s=document.getElementById('sidebar'),f=s.querySelector('.filters'),"
        "h=document.getElementById('tm-filter-head');"
        "const rect=t.getBoundingClientRect();"
        "return {buttonDisplay:getComputedStyle(t).display,"
        "buttonVisibility:getComputedStyle(t).visibility,"
        "buttonRect:{top:rect.top,left:rect.left,width:rect.width,height:rect.height},"
        "sidebarDisplay:getComputedStyle(s).display,sidebarVisibility:getComputedStyle(s).visibility,"
        "panelHeight:f.getBoundingClientRect().height,headDisplay:getComputedStyle(h).display,"
        "body:document.body.className};")
    # CSS mobile bottom-sheet animates visibility for 180 ms; wait until it
    # is actually interactable rather than checking immediately after class change.
    wait.until(lambda d: mobile_close.is_displayed(),
               message=f"Mobile filter close remained hidden: {mobile_info}")
    mobile_close.click()
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
    # Profile v2 runs against an in-memory HTTP fixture, never a real user or Neon.
    driver.set_window_size(1440, 900)
    driver.execute_script("""
      window.__profileCalls=[];
      window.__profileFixture={
        user:{id:999,username:'ChromeTest',email:'test@example.org',is_admin:false},
        settings:{bio:'Marche en montagne',avatar:'compass',public_profile:false,share_completed:false,
          preferences:{daily_km:17,difficulty:'medium',lodging:'camping',route_type:'Boucle',
                       transit:true,water:true,food:true,sleep:true}},
        stats:{total:1,public:1,private:0,favorites:1,completed:1,
               actual_km:12.5,actual_ascent_m:450},
        achievements:['Premier trek terminé'],
        treks:[{id:910001,name:'Sentier test',region:'Alpes',distance:18,elevation:300,is_public:true},
           {id:910002,name:'Sentier à découvrir',region:'Massif central',distance:9,elevation:120,is_public:true}],
        favorites:[{id:910001,name:'Sentier test',region:'Alpes',distance:18,elevation:300,is_public:true}],
        journeys:[{trek_id:910001,status:'completed',name:'Sentier test',region:'Alpes',
             distance:18,elevation:300,completed_on:'2026-08-09',actual_distance_km:12.5,
             actual_ascent_m:450,rating:5,notes:'Belle sortie',photo_urls:[]}],
        collections:[{id:1,name:'Montagnes',treks:[
          {id:910001,name:'Sentier test',region:'Alpes'},
          {id:910099,name:'Parcours de collection',region:'Vosges'}]}]
      };
      currentUser=window.__profileFixture.user;
      window.__profileRealFetch=window.fetch;
      window.fetch=function(url,init){
        const u=String(url);
        if(u.startsWith('/profile/')||u.endsWith('/treks/910001/plan')||u==='/treks/910099'){
          window.__profileCalls.push({url:u,method:(init&&init.method)||'GET'});
          let body={};
          if(u==='/profile/v2')body=window.__profileFixture;
          if(u==='/treks/910099')body={id:910099,name:'Parcours de collection',region:'Vosges',
            difficulty:'easy',distance:14,elevation:220,is_public:true,owner_id:999,
            coords:[[48.4,7.1],[48.41,7.11]]};
          if(u.indexOf('/profile/public/')===0)body={
             username:'ChromeTest',avatar:'compass',bio:'Marche en montagne',
             treks:window.__profileFixture.treks,completed:[]};
          if(u.endsWith('/treks/910001/plan'))body={notes:'Préparation existante',
             checklist:[{text:'Remplir gourde',done:false}]};
          if(u==='/profile/v2/collections'&&init&&init.method==='POST')body={id:2};
          return Promise.resolve(new Response(JSON.stringify(body),{
            status:200,headers:{'Content-Type':'application/json'}}));
        }
        return window.__profileRealFetch(url,init);
      };
      window.openProfile();
    """)
    wait.until(lambda d: d.find_element(By.ID, "tm-profile-v2").is_displayed())
    assert "12.5" in driver.find_element(By.ID, "tm-p-content").text, (
        "Real completed hiking km missing from account dashboard"
    )
    driver.find_element(By.CSS_SELECTOR, '[data-p-tab="projects"]').click()
    # Reproduce reported bug: "À découvrir" must expose and focus the actual editor.
    discover=driver.find_element(By.CSS_SELECTOR, '[data-p-select="910002"]')
    assert "À découvrir" in discover.text
    driver.execute_script(
        "window.__profileErrors=[];"
        "window.addEventListener('error',e=>__profileErrors.push(String(e.message)));"
        "window.addEventListener('unhandledrejection',e=>__profileErrors.push(String(e.reason)));"
    )
    discover.click()
    wait.until(lambda d: d.find_element(By.ID, "tm-p-journey-card").is_displayed())
    assert not driver.execute_script("return window.__profileErrors"), (
        "The first-time adventure editor raised a JavaScript exception"
    )
    assert not driver.find_element(By.ID,"tm-p-completion").is_displayed(), (
        "Completion-only metrics must stay hidden on an unstarted trek"
    )
    assert "18.0 km" in driver.find_element(By.CSS_SELECTOR,
        '[data-p-select="910001"]').find_element(By.XPATH,"..").text, (
        "Sparse collection membership must not overwrite the trek distance"
    )
    assert "Sentier à découvrir" in driver.find_element(By.ID, "tm-p-journey-card").text
    assert driver.execute_script(
        "return document.activeElement?.id==='tm-p-journey-card'"
    ), "Adventure click did not bring its detail editor into focus"
    assert driver.find_element(By.CSS_SELECTOR, '[data-p-select="910002"]').get_attribute("aria-pressed")=="true"
    driver.find_element(By.CSS_SELECTOR, '[data-p-select="910001"]').click()
    assert driver.find_element(By.ID, "tm-p-journey-form").is_displayed()
    driver.find_element(By.CSS_SELECTOR, '[data-p-plan="910001"]').click()
    wait.until(lambda d: d.find_element(By.ID, "tm-p-plan-editor").is_displayed())
    assert "Remplir gourde" in driver.find_element(By.ID, "tm-p-plan-editor").text
    driver.find_element(By.CSS_SELECTOR, '[data-p-checklist-save]').click()
    wait.until(lambda d: d.execute_script(
        "return window.__profileCalls.some(x=>x.url.endsWith('/treks/910001/plan')&&x.method==='PUT')"))
    driver.find_element(By.CSS_SELECTOR, '[data-p-tab="preferences"]').click()
    form=driver.find_element(By.ID, "tm-p-settings-form")
    assert form.is_displayed()
    assert form.find_element(By.NAME, "daily_km").get_attribute("value")=="17"
    form.find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()
    wait.until(lambda d: d.execute_script(
        "return window.__profileCalls.some(x=>x.url==='/profile/v2'&&x.method==='PUT')"))
    driver.find_element(By.CSS_SELECTOR, '[data-p-tab="collections"]').click()
    assert "Montagnes" in driver.find_element(By.ID, "tm-p-content").text
    driver.find_element(By.CSS_SELECTOR, '[data-p-collection="1"]').click()
    assert "Parcours de collection" in driver.find_element(By.ID,"tm-p-collection-content").text
    assert driver.execute_script(
        "return document.activeElement?.id==='tm-p-collection-content'"
    ), "Collection did not visibly open when clicked"
    # A collection can retain public treks not owned or favorited by this user.
    driver.find_element(By.CSS_SELECTOR, '[data-p-open-trek="910099"]').click()
    wait.until(lambda d: d.find_element(By.ID,"modal-backdrop").is_displayed())
    assert "Parcours de collection" in driver.find_element(By.ID,"modal").text
    assert driver.execute_script(
        "return window.__profileCalls.some(c=>c.url==='/treks/910099'&&c.method==='GET')"
    ), "Collection-only trek was not loaded before opening details"
    driver.find_element(By.ID,"modal-close").click()
    wait.until(lambda d: not d.find_element(By.ID,"modal-backdrop").is_displayed())
    driver.execute_script("window.openProfile()")
    wait.until(lambda d: d.find_element(By.ID,"tm-profile-v2").is_displayed())
    driver.find_element(By.CSS_SELECTOR, '[data-p-tab="collections"]').click()
    driver.find_element(By.CSS_SELECTOR, '[data-p-collection="1"]').click()
    driver.find_element(By.CSS_SELECTOR, '[data-p-collection-manage="910001"]').click()
    assert "Sentier test" in driver.find_element(By.ID,"tm-p-journey-card").text, (
        "Collection's prepare button must open its journey editor"
    )
    driver.find_element(By.CSS_SELECTOR, '[data-p-tab="collections"]').click()
    driver.find_element(By.CSS_SELECTOR, '[data-p-collection="1"]').click()
    driver.save_screenshot(str(OUT / "profile-v2-desktop-collection-open.png"))
    driver.find_element(By.ID, "tm-p-exit").click()
    assert not driver.find_element(By.ID, "tm-profile-v2").is_displayed()
    driver.set_window_size(390, 844)
    driver.execute_script("window.openProfile()")
    wait.until(lambda d: d.find_element(By.ID,"tm-profile-v2").is_displayed())
    assert driver.find_element(By.CSS_SELECTOR,'[data-p-tab="preferences"]').is_displayed()
    driver.find_element(By.CSS_SELECTOR,'[data-p-tab="projects"]').click()
    driver.find_element(By.CSS_SELECTOR,'[data-p-select="910002"]').click()
    assert driver.execute_script(
        "const el=document.getElementById('tm-p-journey-card');"
        "const r=el.getBoundingClientRect(); return r.top>=0&&r.top<innerHeight;"
    ), "Mobile journey editor is still off-screen after clicking À découvrir"
    driver.find_element(By.CSS_SELECTOR,'[data-p-tab="collections"]').click()
    driver.find_element(By.CSS_SELECTOR,'[data-p-collection="1"]').click()
    assert driver.execute_script(
        "const r=document.getElementById('tm-p-collection-content').getBoundingClientRect();"
        "return r.top>=0&&r.top<innerHeight;"
    ), "Mobile collection contents are still off-screen after opening"
    driver.find_element(By.CSS_SELECTOR,'[data-p-tab="home"]').click()
    assert driver.execute_script(
        "return document.querySelector('#tm-profile-v2 .tm-p-nav').scrollLeft<=2"
    ), "Mobile profile navigation must open at the dashboard tab"
    layout=driver.execute_script(
        "const r=document.querySelector('.tm-p-shell').getBoundingClientRect();"
        "return {right:r.right,window:innerWidth};"
    )
    assert layout["right"]<=layout["window"]+2, (
        f"Phone profile overflows horizontally: {layout}"
    )
    driver.save_screenshot(str(OUT / "profile-v2-mobile.png"))
    driver.find_element(By.ID,"tm-p-exit").click()
    driver.set_window_size(1440,900)
    driver.find_element(By.ID,"tm-ai-launch").click()
    wait.until(lambda d: d.find_element(By.ID,"tm-ai-overlay").is_displayed())
    pref_button=driver.find_element(By.ID,"tm-ai-profile-defaults")
    pref_button.click()
    wait.until(lambda d: d.find_element(By.ID,"tm-ai-km").get_attribute("value")=="17")
    assert "Hébergement souhaité : camping" in driver.find_element(
        By.ID, "tm-ai-prompt").get_attribute("value"), (
        "Personal lodging preference did not reach TrekBrain's request"
    )
    driver.find_element(By.ID,"tm-ai-close").click()
    wait.until(lambda d: not d.find_element(By.ID,"tm-ai-overlay").is_displayed())
    driver.execute_script("window.fetch=window.__profileRealFetch;currentUser=null;")
    print("REAL CHROME: desktop 1440x900, mobile 390x844 and short phones 390/320x640; "
          "route/map, long preparation scroll, native expand/collapse, exit, explorer restore PASS")
finally:
    driver.quit()
