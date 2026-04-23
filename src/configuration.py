import os

# Configuration for running the optimization solvers
# 
# The 'update' flag controls whether to recompute results:
#   - update=True (default): Always recompute and overwrite results
#   - update=False: Skip computation if results already exist (faster for re-runs)
# 
# Add "update": False to any solver's args to skip recomputation of existing results

class PathConfiguration():
    DATA_DIR_PATH = "data"
    BASE_ESTIMATIONS_DIR_PATH = os.path.join(DATA_DIR_PATH, "base_estimations")
    PROFILES_DIR_PATH = os.path.join(DATA_DIR_PATH, "profiles")
    ESTIMATIONS_DIR_PATH = os.path.join(DATA_DIR_PATH, "estimations")
    SOLVED_ESTIMATIONS_DIR_PATH = os.path.join(DATA_DIR_PATH, "solved_estimations")
    IMAGES_DIR_PATH = "images"

    @classmethod
    def create_directories(cls):
        for attr in cls.__dict__:
            if attr.endswith("_DIR_PATH"):
                os.makedirs(getattr(cls, attr), exist_ok=True)

PathConfiguration.create_directories()

class ExecutionConfiguration():
    # Variables that you may edit
    # BASE_ESTIMATIONS = "market_data.json"
    # PROFILE = "esios_profiles_processed2023.csv"
    # Use 0.0 for tests placed in a folder (e.g. estimations/test_2/solar_0.csv)
    # SOLAR_PERCENTS = [0.0]
    PPA_PERCENTS = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    # PPA_PRICES = list(range(-30, 16))

    # ESTIMATIONS_NAME = "test"
    SOLVERS = [
        {"module": "market.market", "args": {"estimation_name": "test", "solar_percent": 0.0, "ppa_percent": PPA_PERCENTS, "update": False}},
        {"module": "market.visualizer", "args":{"estimation_name": "test", "update": False}},
        {"module": "bilevel.bilevel_kkt", "args": {"estimation_name": "test", "solar_percent": 0.0, "ppa_price": list(range(-30, 16)), "update": False}},
        {"module": "bilevel.visualizer", "args":{"estimation_name": "test", "update": False}},
        
        {"module": "market.market", "args": {"estimation_name": "test_2", "solar_percent": 0.0, "ppa_percent": PPA_PERCENTS, "update": False}},
        {"module": "market.visualizer", "args":{"estimation_name": "test_2", "update": False}},
        {"module": "bilevel.bilevel_kkt", "args": {"estimation_name": "test_2", "solar_percent": 0.0, "ppa_price": list(range(-15, 16)), "update": False}},
        {"module": "bilevel.visualizer", "args":{"estimation_name": "test_2", "update": False}},
        
        {"module": "data", "args": {"base_estimations": "market_data.json", "profile": "esios_profiles_processed2023.csv", "estimation_name": "estimations_2030", "update": False}},
        {"module": "market.market", "args": {"estimation_name": "estimations_2030", "solar_percent": [0.0, 0.01, 0.05, 0.1, 0.2, 0.5, 1], "ppa_percent": PPA_PERCENTS, "update": False}},
        {"module": "market.visualizer", "args":{"estimation_name": "estimations_2030", "update": False}},
        {"module": "bilevel.bilevel_kkt", "args": {"estimation_name": "estimations_2030", "solar_percent": 0.05, "ppa_price": [x/2 for x in range(9*2, 16*2)], "update": False}},
        {"module": "bilevel.bilevel_kkt", "args": {"estimation_name": "estimations_2030", "solar_percent": 0.1, "ppa_price": [x/2 for x in range(5*2, 20*2)], "update": False}},
        {"module": "bilevel.bilevel_kkt", "args": {"estimation_name": "estimations_2030", "solar_percent": 0.2, "ppa_price": list(range(0, 31)), "update": False}},
        {"module": "bilevel.visualizer", "args":{"estimation_name": "estimations_2030", "update": False}}
    ]
    M_MARGIN_MULTIPLIER = 1.2
    SOLVER_TIMEOUT_SECONDS = 6000  # 100 minutes

    # Automatic variables
    # PARTICULAR_SOLVED_ESTIMATIONS_DIR_PATH = os.path.join(PathConfiguration.SOLVED_ESTIMATIONS_DIR_PATH, ESTIMATIONS_NAME)

#     @classmethod
#     def create_directories(cls):
#         for attr in cls.__dict__:
#             if attr.endswith("_DIR_PATH"):
#                 os.makedirs(getattr(cls, attr), exist_ok=True)

# ExecutionConfiguration.create_directories()