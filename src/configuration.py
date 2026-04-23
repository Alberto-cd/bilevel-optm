import os

# Configuration for running the optimization solvers

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
    M_MARGIN_MULTIPLIER = 1.2
    SOLVER_TIMEOUT_SECONDS = 6000  # 100 minutes
