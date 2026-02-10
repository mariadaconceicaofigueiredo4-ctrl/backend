import os
import re
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any, List

import requests
import pytz
from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import (
    TimeoutException,
    WebDriverException,
    NoSuchWindowException,
    InvalidSessionIdException,
)
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime
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

def hora_esta_permitida(hora: str, horarios_permitidos: List[str]) -> bool:
    return hora in set([x.strip() for x in horarios_permitidos if str(x).strip()])


def cor_do_numero(n: int) -> str:
    if n == 0:
        return "white"
    if 1 <= n <= 7:
        return "red"
    return "black"


def log(msg: str) -> None:
    print(msg, flush=True)


def safe_get_text(el) -> str:
    try:
        return (el.text or "").strip()
    except Exception:
        return ""


# =========================
# EXTRAÇÃO DE HORÁRIO
# =========================

def find_time_near_element(el) -> Optional[str]:
    try:
        # procura qualquer elemento dentro do botão que tenha padrão de hora
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

    hora_source = "dom"


    return {
        "numero": n,
        "cor": cor_do_numero(n),
        "hora": hora,
        "hora_source": hora_source,
        "raw": text,
    }


def build_round_signature(round_data: Dict[str, Any]) -> str:
    n = round_data.get("numero")
    h = round_data.get("hora")
    src = round_data.get("hora_source")

    if h and src == "dom":
        return f"{n}@{h}"
    return f"{n}"


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
            r = requests.get(self.url, timeout=5)
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


def horarios_liberados(state: HorariosState) -> bool:
    return bool(state.ativo and state.horarios)


# =========================
# DRIVER
# =========================

def make_driver() -> webdriver.Chrome:
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.binary_location = "/usr/bin/chromium"

    service = Service("/usr/bin/chromedriver")
    driver = webdriver.Chrome(service=service, options=chrome_options)

    driver.set_page_load_timeout(60)
    return driver


# =========================
# CORE LOOP
# =========================

def iniciar_robo():
    load_dotenv()

    blaze_url = os.getenv("BLAZE_URL", BLAZE_DOUBLE_URL_DEFAULT)
    status_update_url = os.getenv("STATUS_UPDATE", "http://127.0.0.1:8000/update_status")
    horarios_url = os.getenv("HORARIOS_API_URL", "http://127.0.0.1:8000/horarios/permitidos")

    log("🤖 Robô Iniciado (Timezone Brasil fixado)")

    horarios_client = HorariosClient(horarios_url)
    driver = make_driver()
    driver.get(blaze_url)

    last_sig = None
    bet_state = BetState()

    while True:
        try:
            st = horarios_client.get_state()

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
            hora = latest.get("hora", now_br().strftime("%H:%M"))

            log(f"📡 {numero} ({cor}) [{hora}]")

            payload = {
                "numero": numero,
                "cor": cor,
                "hora": hora,
                "mensagem": None
            }

            requests.post(status_update_url, json=payload, timeout=5)

            time.sleep(1)

        except Exception as e:
            log(f"Erro: {e}")
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
