import pandas as pd
import numpy as np


def hour_to_year(hour: int) -> int:
    return hour//(24*365)

class EntityDataframe():
    def __init__(self, path):
        self.columns: list[str] = ["offer", "limit"]
        self.df: pd.DataFrame = self._read_csv(path)
    
    def _read_csv(self, path):
        df = pd.read_csv(path)

        assert len(df.columns) == len(self.columns)
        assert set(df.columns) == set(self.columns)

        # TODO: Add checks of gaps

        return df

class ElectricityMarketDataframe():
    def __init__(self, path: str):
        self.columns: list[str] = ["is_generator", "own", "entity", "years", "hours", "offer", "limit"]
        self.df: pd.DataFrame = self._read_csv(path)

    def get_entities_name(self, is_generator:bool|None = None, own: bool|None = None) -> np.ndarray:
        
        if own is None:
            if is_generator is None:
                return self.df["entity"].unique()
            else:
                return self.df[self.df["is_generator"] == is_generator]["entity"].unique()
        elif is_generator is None:
            return self.df[self.df["own"] == own]["entity"].unique()


        return self.df[(self.df["is_generator"] == is_generator) & (self.df["own"] == own)]["entity"].unique()
    
    def get_hours(self) -> np.ndarray:
        return self.df["hours"].unique()
    
    def get_years(self) -> np.ndarray:
        return self.df["years"].unique()
    
    def get_entities_column_dict(self, column: str, is_generator: bool, own: bool|None = None) -> dict:
        assert column in self.columns

        if own is None:
            df = self.df[(self.df["is_generator"] == is_generator)]
        else:
            df = self.df[(self.df["is_generator"] == is_generator) & (self.df["own"] == own)]

        return df.set_index(["entity", "hours"])[column].to_dict()
    
    def get_own_generators_offers(self):
        self.get_entities_column_dict("offer", True)
    
    def get_own_generators_limit(self):
        self.get_entities_column_dict("limit", True)
    
    def get_var_vector(self) -> list[float]:
        generators = self.get_entities_name(True, True)
        hours = self.get_hours()
        offers = self.get_entities_column_dict("offer", True, True)

        vector = []
        for g in generators:
            for t in hours:
                # Offer
                vector.append(offers[(g, t)])
                # PPA percentage
                vector.append(0.0)

        return vector
    
    def get_var_dict(self, vector):
        generators = self.get_entities_name(True, True)
        hours = self.get_hours()

        assert 2*len(generators)*len(hours) == len(vector)

        offers = dict()
        ppa_percentage = dict()

        i = 0
        for g in generators:
            for t in hours:
                # Offer
                offers[(g, t)] = vector[i]
                i += 1
                # PPA percentage
                ppa_percentage[(g, t)] = vector[i]
                i += 1

        return offers, ppa_percentage

    def _read_csv(self, path):
        # df = pd.read_csv(path, sep=";", decimal=",")
        df = pd.read_csv(path)

        # assert len(df.columns) == len(self.columns)
        # assert set(df.columns) == set(self.columns)

        # TODO: Add checks of gaps

        # TODO: Set order for vector

        return df

