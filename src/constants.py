import os

DATA_DIR_PATH = "data"
BASE_ESTIMATIONS_DIR_PATH = os.path.join(DATA_DIR_PATH, "base_estimations")
os.makedirs(BASE_ESTIMATIONS_DIR_PATH, exist_ok=True)
PROFILES_DIR_PATH = os.path.join(DATA_DIR_PATH, "profiles")
os.makedirs(PROFILES_DIR_PATH, exist_ok=True)

ESTIMATIONS_DIR_PATH = os.path.join(DATA_DIR_PATH, "estimations")
os.makedirs(ESTIMATIONS_DIR_PATH, exist_ok=True)
SOLVED_ESTIMATIONS_DIR_PATH = os.path.join(DATA_DIR_PATH, "solved_estimations")
os.makedirs(SOLVED_ESTIMATIONS_DIR_PATH, exist_ok=True)

IMAGES_DIR_PATH = "images"
os.makedirs(IMAGES_DIR_PATH, exist_ok=True)

# For data.py when executed as __main__
ESTIMATIONS_TO_CREATE = {
    "base_estimations": "market_data.json",
    "profile": "esios_profiles_processed2023.csv",
    "final_path": os.path.join(ESTIMATIONS_DIR_PATH, "estimations_2030.csv"),
    "percent": 0.2
}

ESTIMATIONS_TO_SOLVE = {
    "name": "test",
    "solvers": [
        {"module": "market.market", "args": {}},
        {"module": "bilevel.bilevel_kkt", "args": {"ppa": False}},
        {"module": "bilevel.bilevel_kkt", "args": {"ppa": True}}
    ]
}

M_MARGIN_MULTIPLIER = 1.2
PPA_PRICE = 0
