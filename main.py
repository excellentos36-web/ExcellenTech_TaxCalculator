from fastapi import FastAPI
from pydantic import BaseModel
import json, os, threading, requests
from fastapi.middleware.cors import CORSMiddleware

BASE_DIR = os.path.dirname(__file__)
LOCAL_SLABS_PATH = os.path.join(BASE_DIR, '..', 'tax_slabs.json')
REMOTE_SLABS_URL = "https://raw.githubusercontent.com/example/tax-slabs/main/tax_slabs.json"  # replace with your hosted URL

app = FastAPI(title='ExcellenTech Tax Backend')
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:3000'], allow_methods=['*'], allow_headers=['*'])

SLABS = {}
SLABS_VERSION = None

def load_local_slabs():
    global SLABS, SLABS_VERSION
    try:
        with open(LOCAL_SLABS_PATH, 'r', encoding='utf-8') as f:
            SLABS = json.load(f)
            SLABS_VERSION = SLABS.get('version')
            print('Loaded local slabs, version:', SLABS_VERSION)
    except Exception as e:
        print('Failed to load local slabs:', e)
        SLABS = {}

def fetch_remote_slabs_once(timeout=5):
    global SLABS, SLABS_VERSION
    try:
        resp = requests.get(REMOTE_SLABS_URL, timeout=timeout)
        if resp.status_code == 200:
            remote = resp.json()
            remote_version = remote.get('version')
            if remote_version and remote_version != SLABS_VERSION:
                SLABS = remote
                SLABS_VERSION = remote_version
                try:
                    with open(LOCAL_SLABS_PATH, 'w', encoding='utf-8') as f:
                        json.dump(remote, f, indent=2, ensure_ascii=False)
                except Exception as e:
                    print('Warning: could not persist remote slabs:', e)
                print('Updated slabs from remote, version', remote_version)
            else:
                print('Remote slabs present but same version or missing version.')
        else:
            print('Remote slabs fetch returned status', resp.status_code)
    except Exception as e:
        print('Could not fetch remote slabs (network?):', e)

load_local_slabs()
threading.Thread(target=fetch_remote_slabs_once, daemon=True).start()

with open(LOCAL_SLABS_PATH, 'r', encoding='utf-8') as f:
    SLABS = json.load(f)

class CalcReq(BaseModel):
    vtype: str
    amount: float
    age: int
    fuel: str
    other_state: bool
    model: str = ''

def find_rate(list_slabs, amount):
    for s in list_slabs:
        lo = s.get('min') if 'min' in s else s[0]
        hi = s.get('max') if 'max' in s else s[1]
        rate = s.get('rate') if 'rate' in s else s[2]
        if lo <= amount <= hi:
            return rate
    return list_slabs[-1].get('rate') if isinstance(list_slabs[-1], dict) else list_slabs[-1][2]

@app.post('/api/calc')
def calc(req: CalcReq):
    amount = req.amount
    age = req.age
    vtype = req.vtype
    fuel = req.fuel
    other = req.other_state

    if vtype == 'Car':
        rate = find_rate(SLABS.get('car_slabs') or SLABS.get('car_slabs'), amount)
    elif vtype == 'Two Wheeler':
        rate = find_rate(SLABS.get('two_wheeler_slabs') or SLABS.get('two_wheeler_slabs'), amount)
    else:
        rate = find_rate(SLABS.get('commercial_slabs') or SLABS.get('commercial_slabs'), amount)

    base_tax = amount * rate

    age_disc = 0.0
    for ad in SLABS.get('age_depreciation', []):
        min_age = ad.get('min_age', ad[0])
        max_age = ad.get('max_age', ad[1])
        if min_age <= age <= max_age:
            age_disc = ad.get('discount', ad[2])
            break

    tax_payable = base_tax * (1 - age_disc) if other else base_tax

    ev_conf = SLABS.get('ev_special', {})
    ev_discount = ev_conf.get('ev_discount_example', 0.0) if fuel == 'Electric' else 0.0
    tax_payable = tax_payable * (1 - ev_discount)

    fixed = SLABS.get('fixed_charges', {})
    fixed_sum = sum(fixed.values())

    total = tax_payable + fixed_sum

    return {
        'base_tax': round(base_tax,2),
        'age_discount_percent': round(age_disc*100,2),
        'ev_discount_percent': round(ev_discount*100,2),
        'tax_payable': round(tax_payable,2),
        'fixed_charges': fixed,
        'fixed_sum': round(fixed_sum,2),
        'total_estimated': round(total,2)
    }
