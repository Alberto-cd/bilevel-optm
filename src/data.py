import json
import pandas as pd
import numpy as np
import os
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from .constants import BASE_MARKET_ESTIMATIONS_PATH, MARKET_PROFILE_PATH, MAIN_CSV

class DataProcessor():
    def __init__(self, json_path: str = BASE_MARKET_ESTIMATIONS_PATH, csv_path: str = MARKET_PROFILE_PATH, percent:float=0.2):
        self.percent = percent
        gen_est, gen_prices, dem_est, dem_prices = self._get_market_curves_estimations(json_path, csv_path)
        self.dataframe: pd.DataFrame = self._combine_dataframes(gen_est, gen_prices, dem_est, dem_prices)
        
        self.columns: list[str] = ["is_generator", "own", "entity", "years", "hour", "offer", "limit"]
        
    @staticmethod
    def normalize_profile(market_estimations, past_market_profiles, key):
        profile_keys = [gen["profile_key"] for gen in market_estimations[key]]
        columns_to_drop = [col for col in past_market_profiles.columns if col not in profile_keys]
        filtered_profiles = past_market_profiles.drop(columns=columns_to_drop)

        estimations = pd.DataFrame(index=filtered_profiles.index)
        for gen in market_estimations[key]:
            profile_key = gen["profile_key"]
            annual_gwh = gen["annual_gwh"]
            if profile_key in filtered_profiles.columns:
                # Profile-based
                profile_col = filtered_profiles[profile_key]
                scaling = annual_gwh / profile_col.sum()
                profile_curve = profile_col * scaling
                estimations[gen["name"]] = profile_curve
            else:
                flat_curve = pd.Series([annual_gwh / 8760] * len(filtered_profiles), index=filtered_profiles.index)
                estimations[gen["name"]] = flat_curve

        prices = pd.DataFrame([
            {"name": gen["name"], "min_price": gen["min_price"], "max_price": gen["max_price"]}
            for gen in market_estimations[key]
        ])

        return estimations, prices

    def _get_market_curves_estimations(self, json_path: str = BASE_MARKET_ESTIMATIONS_PATH, csv_path: str = MARKET_PROFILE_PATH):
        # Read data files
        with open(json_path, 'r') as file:
            market_estimations = json.load(file)

        past_market_profiles = pd.read_csv(csv_path)

        # Normalize data
        gen_est, gen_prices = self.normalize_profile(market_estimations, past_market_profiles, "generators")
        dem_est, dem_prices = self.normalize_profile(market_estimations, past_market_profiles, "demands")
        
        return gen_est, gen_prices, dem_est, dem_prices

    def _combine_dataframes(self, gen_est, gen_prices, dem_est, dem_prices):
        # Combine generators
        gen_df = gen_est.melt(var_name='name', value_name='limit', ignore_index=False).reset_index().rename(columns={'index': 'hour'})
        gen_df['is_generator'] = True
        gen_prices['offer'] = (gen_prices['min_price'] + gen_prices['max_price']) / 2
        gen_df = pd.merge(gen_df, gen_prices[['name', 'offer']], on='name')

        # Split Solar PV into owned and non-owned portions
        solar_pv_mask = gen_df['name'] == 'Solar PV'
        solar_pv_data = gen_df[solar_pv_mask].copy()
        non_solar_data = gen_df[~solar_pv_mask].copy()
        
        if not solar_pv_data.empty:
            # Create owned solar portion
            solar_owned = solar_pv_data.copy()
            solar_owned['limit'] = solar_owned['limit'] * self.percent
            solar_owned['name'] = 'Solar PV (Own)'
            
            # Update non-owned solar portion
            solar_pv_data['limit'] = solar_pv_data['limit'] * (1 - self.percent)
            
            # Combine all generator data
            gen_df = pd.concat([non_solar_data, solar_pv_data, solar_owned], ignore_index=True)

        # Combine demands
        dem_df = dem_est.melt(var_name='name', value_name='limit', ignore_index=False).reset_index().rename(columns={'index': 'hour'})
        dem_df['is_generator'] = False
        dem_prices['offer'] = (dem_prices['min_price'] + dem_prices['max_price']) / 2
        dem_df = pd.merge(dem_df, dem_prices[['name', 'offer']], on='name')

        # Concatenate and set ownership
        combined_df = pd.concat([gen_df, dem_df], ignore_index=True)
        combined_df['own'] = combined_df['name'] == 'Solar PV (Own)'
        combined_df['years'] = 1  # Placeholder
        combined_df = combined_df.rename(columns={"name": "entity"})
        
        # Reorder and assign
        return combined_df[['is_generator', 'own', 'entity', 'years', 'hour', 'offer', 'limit']]

    def save_dataframe(self, path:str=MAIN_CSV, decimals:None|int=None):
        df = self.dataframe.copy()
        if decimals is not None:
            df = df.round(decimals)
        df.to_csv(path, index=False)


class ElectricityMarketCurvesDataframe():
    def __init__(self, path: str):
        self.columns: list[str] = ["is_generator", "own", "entity", "years", "hour", "offer", "limit"]
        self.path: str = path
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
        return self.df["hour"].unique()
    
    def get_years(self) -> np.ndarray:
        return self.df["years"].unique()
    
    def get_entities_column_dict(self, column: str, is_generator: bool, own: bool|None = None) -> dict:
        assert column in self.columns

        if own is None:
            df = self.df[(self.df["is_generator"] == is_generator)]
        else:
            df = self.df[(self.df["is_generator"] == is_generator) & (self.df["own"] == own)]

        return df.set_index(["entity", "hour"])[column].to_dict()
    
    def get_own_generators_offers(self):
        self.get_entities_column_dict("offer", True)
    
    def get_own_generators_limit(self):
        self.get_entities_column_dict("limit", True)

    def _read_csv(self, path):
        # df = pd.read_csv(path, sep=";", decimal=",")
        df = pd.read_csv(path)

        assert len(df.columns) == len(self.columns)
        assert set(df.columns) == set(self.columns)

        return df

class ElectricityMarketSolvedDataframe(ElectricityMarketCurvesDataframe):
    def __init__(self, base_df: ElectricityMarketCurvesDataframe, taken: dict = None, prices: dict = None):
        # Copy base columns and add solved columns
        self.columns = base_df.columns + ["taken", "price"]
        # Copy base dataframe
        self.df = base_df.df.copy()
        # Add taken and price columns if provided
        if taken is not None:
            # taken: dict[(entity, hour)] = value
            self.df["taken"] = self.df.apply(lambda row: taken.get((row["entity"], row["hour"]), 0.0), axis=1)
        else:
            self.df["taken"] = 0.0
        if prices is not None:
            # prices: dict[hour] = value
            self.df["price"] = self.df["hour"].map(lambda h: prices.get(h, 0.0))
        else:
            self.df["price"] = 0.0

    def save_dataframe(self, path: str, decimals: None | int = None):
        df = self.df.copy()
        if decimals is not None:
            df = df.round(decimals)
        df.to_csv(path, index=False)
    
    def save_market_plots(self, output_dir: str = "market_plots", limit=24):
        os.makedirs(output_dir, exist_ok=True)

        hours = list(self.df["hour"].unique())[:limit] if limit is not None else list(self.df["hour"].unique())
        for hour in hours:
            df_hour = self.df[self.df["hour"] == hour]

            # Separate data by type
            demand_data = df_hour[~df_hour["is_generator"]]
            own_gen_data = df_hour[df_hour["is_generator"] & df_hour["own"]]
            ext_gen_data = df_hour[df_hour["is_generator"] & ~df_hour["own"]]

            # Create bid/offer curves data
            demands_info = [[row["limit"], row["offer"]] for _, row in demand_data.iterrows()]
            own_gen_info = [[row["limit"], row["offer"]] for _, row in own_gen_data.iterrows()]
            ext_gen_info = [[row["limit"], row["offer"]] for _, row in ext_gen_data.iterrows()]

            # Sort data for plotting
            demands_info.sort(key=lambda x: x[1], reverse=True)  # Sort by bid (descending)
            generators_info = own_gen_info + ext_gen_info
            generators_info.sort(key=lambda x: x[1])  # Sort by offer (ascending)

            # Plot market curves
            plt.figure(figsize=(10, 6))

            # Plot demand curve (blue)
            x_demand = 0
            last_bid = None
            for limit, bid in demands_info:
                if last_bid is not None:
                    plt.plot([x_demand, x_demand], [last_bid, bid], color="blue")
                plt.plot([x_demand, x_demand + limit], [bid, bid], color="blue", linewidth=2)
                x_demand += limit
                last_bid = bid

            # Plot supply curves
            x_supply = 0
            last_offer = None
            for i, (limit, offer) in enumerate(generators_info):
                # Use green for own generators, red for external
                color = "green" if i < len(own_gen_info) else "red"
                if last_offer is not None:
                    plt.plot([x_supply, x_supply], [last_offer, offer], color=color)
                plt.plot([x_supply, x_supply + limit], [offer, offer], color=color, linewidth=2)
                x_supply += limit
                last_offer = offer
            
            # Add market clearing lines
            max_quantity = max(x_demand, x_supply) if max(x_demand, x_supply) > 0 else 100
            max_price = max((demands_info[0][1] if demands_info else 100),
                           (generators_info[-1][1] if generators_info else 100)) * 1.1
            
            market_price = df_hour["price"].iloc[0]
            supplied_demand = demand_data["taken"].sum()
            
            plt.axhline(y=market_price, xmax=supplied_demand/max_quantity, 
                       color="orange", linestyle="--", linewidth=2, label=f"Market Price: {market_price:.2f}")
            plt.axvline(x=supplied_demand, ymax=market_price/max_price, 
                       color="magenta", linestyle="--", linewidth=2)

            # Set plot limits and labels
            min_price = min((demands_info[-1][1] if demands_info else 0),
                           (generators_info[0][1] if generators_info else 0),
                           0) * 1.1
            plt.xlim(0, max_quantity)
            plt.ylim(min_price, max_price)
            plt.xlabel("Quantity (MWh)")
            plt.ylabel("Price (€/MWh)")
            plt.title(f"Market Clearing - Hour {hour}")

            # Custom legend with correct colors and only present categories
            legend_elements = [Line2D([0], [0], color='blue', lw=2, label='Demand')]
            if len(own_gen_info) > 0:
                legend_elements.append(Line2D([0], [0], color='green', lw=2, label='Own Generators'))
            if len(ext_gen_info) > 0:
                legend_elements.append(Line2D([0], [0], color='red', lw=2, label='External Generators'))
            legend_elements.append(Line2D([0], [0], color='orange', lw=2, linestyle='--', label=f'Market Price: {market_price:.2f}'))
            legend_elements.append(Line2D([0], [0], color='magenta', lw=2, linestyle='--', label=f'Supplied Quantity: {supplied_demand:.2f}'))
            plt.legend(handles=legend_elements)
            plt.grid(True, alpha=0.3)

            # Save plot
            plot_path = os.path.join(output_dir, f"market_hour_{hour}.png")
            plt.savefig(plot_path, dpi=300, bbox_inches="tight")
            plt.close()


def main():
    DataProcessor().save_dataframe(MAIN_CSV)
    ElectricityMarketCurvesDataframe(MAIN_CSV)

if __name__ == "__main__":
    main()
