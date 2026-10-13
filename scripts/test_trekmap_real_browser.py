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
    assert driver.find_element(By.ID, "map").is_displayed(), "Main hiking map is hidden"

    def open_and_check(label: str, width: int, height: int):
        driver.set_window_size(width, height)
        opened = driver.execute_script(
            "return window.TrekBrainMapWorkspace.open(arguments[0]);", PLAN
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

    open_and_check("desktop-1440", 1440, 900)
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
    print("REAL CHROME: desktop 1440x900 and mobile 390x844; "
          "route/map, stages, expand, exit, explorer restore PASS")
finally:
    driver.quit()
