import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any, List
from urllib.parse import urljoin

import requests
from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from selenium.common.exceptions import WebDriverException

# Para rodar local no Windows/macOS sem chromium instalado
try:
    from webdriver_manager.chrome import ChromeDriverManager
except Exception:
    ChromeDriverManager = None

from zoneinfo import ZoneInfo

BR_TZ = ZoneInfo("America/Sao_Paulo")


def now_br() -> datetime:
    return datetime.now(BR_TZ)


# =========================
# CONFIG / CONSTANTS
# =========================

BLAZE_DOUBLE_URL_DEFAULT = "https://www.tipminer.com/br/historico/blaze/double"
HISTORY_BUTTONS_SELECTOR = ".round-history button"

RE_NUM = re.compile(r"\b(0|[1-9]|1[0-4])\b")
RE_TIME = re.compile(r"\b([01]\d|2[0-3]):([0-5]\d)\b")


# =========================
# DATA CLASSES
# =========================

@dataclass
class HorariosState:
    ativo: bool
    horarios: List[str]
    fetched_at: float


@dataclass
class BetState:
    ativo: bool = False
    aguardando_rodada: bool = False
    gale_atual: int = 0
    cor_alvo: str = "red"
    max_gales: int = 1
    hora_sinal: Optional[str] = None


# =========================
# HELPERS
# =========================

def log(msg: str) -> None:
    print(msg, flush=True)


def env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on")


def safe_get_text(el) -> str:
    try:
        return (el.text or "").strip()
    except Exception:
        return ""


def cor_do_numero(n: int) -> str:
    if n == 0:
        return "white"
    if 1 <= n <= 7:
        return "red"
    return "black"


def build_round_signature(round_data: Dict[str, Any]) -> str:
    n = round_data.get("numero")
    h = round_data.get("hora")
    src = round_data.get("hora_source")

    if h and src == "dom":
        return f"{n}@{h}"
    return f"{n}"


def build_api_url(path: str) -> str:
    """
    Prioridade:
    1) Variável específica (ex: STATUS_UPDATE, HORARIOS_API_URL)
    2) API_BASE_URL + path
    3) fallback local (apenas para DEV) -> http://127.0.0.1:8000
    """
    path = path.lstrip("/")
    base = os.getenv("API_BASE_URL")

    if base:
        base = base.rstrip("/") + "/"
        return urljoin(base, path)

    # fallback DEV (local)
    return f"http://127.0.0.1:8000/{path}"


# =========================
# EXTRAÇÃO DE HORÁRIO
# =========================

def find_time_near_element(el) -> Optional[str]:
    try:
        inner_elements = el.find_elements(By.XPATH, ".//*")
        for child in inner_elements:
            txt = safe_get_text(child)
            mt = RE_TIME.search(txt)
            if mt:
                return f"{mt.group(1)}:{mt.group(2)}"
    except Exception:
        pass
    return None


def parse_pedra_from_element(el) -> Optional[Dict[str, Any]]:
    text = safe_get_text(el)
    if not text:
        return None

    mnum = RE_NUM.search(text)
    if not mnum:
        return None

    n = int(mnum.group(1))
    if not (0 <= n <= 14):
        return None

    hora = find_time_near_element(el)
    if not hora:
        return None  # ignora rodada sem horário real

    return {
        "numero": n,
        "cor": cor_do_numero(n),
        "hora": hora,
        "hora_source": "dom",
        "raw": text,
    }


# =========================
# HORÁRIOS API
# =========================

class HorariosClient:
    def __init__(self, url: str, cache_ttl_sec: int = 10):
        self.url = url.rstrip("/")
        self.cache_ttl_sec = cache_ttl_sec
        self._cache: Optional[HorariosState] = None

    def get_state(self) -> HorariosState:
        now = time.time()

        if self._cache and (now - self._cache.fetched_at) <= self.cache_ttl_sec:
            return self._cache

        try:
            r = requests.get(self.url, timeout=8)
            r.raise_for_status()
            data = r.json()

            ativo = bool(data.get("ativo", False))
            horarios = data.get("horarios", []) or []

            st = HorariosState(
                ativo=ativo,
                horarios=[str(x).strip() for x in horarios],
                fetched_at=now,
            )
            self._cache = st
            return st

        except Exception:
            return HorariosState(False, [], now)


# =========================
# DRIVER
# =========================

def make_driver(headless: bool) -> webdriver.Chrome:
    chrome_options = Options()

    # Render/Linux
    if headless:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    # Se existir chromium no sistema (Docker)
    chromium_bin = os.getenv("CHROME_BIN", "/usr/bin/chromium")
    chromedriver_path = os.getenv("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")

    service = None

    if os.path.exists(chromium_bin):
        chrome_options.binary_location = chromium_bin

    # Se existir chromedriver do sistema (Docker/Render)
    if os.path.exists(chromedriver_path):
        service = Service(chromedriver_path)
    else:
        # Local (Windows/macOS) via webdriver-manager
        if ChromeDriverManager is None:
            raise RuntimeError(
                "Chromedriver não encontrado e webdriver-manager não está disponível. "
                "Instale webdriver-manager ou forneça CHROMEDRIVER_PATH."
            )
        service = Service(ChromeDriverManager().install())

    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.set_page_load_timeout(60)
    return driver


# =========================
# CORE LOOP
# =========================

def iniciar_robo():
    load_dotenv()

    blaze_url = os.getenv("BLAZE_URL", BLAZE_DOUBLE_URL_DEFAULT)

    # URLs (PROD via API_BASE_URL / DEV via fallback)
    horarios_url = os.getenv("HORARIOS_API_URL") or build_api_url("/horarios/permitidos")
    status_update_url = os.getenv("STATUS_UPDATE") or build_api_url("/update_status")

    # headless controlado por ENV
    headless = env_bool("HEADLESS", default=True)

    log("🤖 Robô Iniciado (Timezone Brasil fixado)")
    log(f"🌐 BLAZE_URL: {blaze_url}")
    log(f"🕒 HORARIOS_API_URL: {horarios_url}")
    log(f"📨 STATUS_UPDATE: {status_update_url}")
    log(f"🧠 HEADLESS: {headless}")

    horarios_client = HorariosClient(horarios_url)

    driver = make_driver(headless=headless)

    try:
        driver.get(blaze_url)
    except WebDriverException as e:
        log(f"Erro ao abrir URL do Blaze: {e}")
        raise

    last_sig = None
    _ = BetState()  # reservado para evolução

    while True:
        try:
            _ = horarios_client.get_state()  # você pode usar isso depois para travar sinais

            latest = get_latest_round(driver)
            if not latest:
                time.sleep(1)
                continue

            sig = build_round_signature(latest)
            if sig == last_sig:
                time.sleep(1)
                continue

            last_sig = sig

            numero = latest["numero"]
            cor = latest["cor"]
            hora = latest.get("hora") or now_br().strftime("%H:%M")

            log(f"📡 {numero} ({cor}) [{hora}]")

            payload = {
                "numero": numero,
                "cor": cor,
                "hora": hora,
                "mensagem": None
            }

            try:
                requests.post(status_update_url, json=payload, timeout=8).raise_for_status()
            except Exception as e:
                log(f"Erro POST update_status: {e}")

            time.sleep(1)

        except Exception as e:
            log(f"Erro loop: {e}")
            time.sleep(2)


def get_latest_round(driver):
    wait = WebDriverWait(driver, 15)
    wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, HISTORY_BUTTONS_SELECTOR)))

    elements = driver.find_elements(By.CSS_SELECTOR, HISTORY_BUTTONS_SELECTOR)

    for el in elements:
        rd = parse_pedra_from_element(el)
        if rd:
            return rd

    return None


if __name__ == "__main__":
    iniciar_robo()
