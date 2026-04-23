import os
import matplotlib.pyplot as plt
from matplotlib import colors

from ..data import ElectricityMarketSolvedDataframe
from ..configuration import PathConfiguration


class MarketVisualizer():
    """Auto-discovers market clearing results and provides plotting helpers
    for individual plots and comparisons across different PPA percentages.
    """
    def __init__(self, estimation_name: str, solar_percent: float = None, update: bool = True):
        if estimation_name is None:
            raise ValueError("estimation_name is required")
        self.estimation_name = estimation_name
        self.solar_percent = solar_percent
        self.update = update
        self.base_dir = os.path.join(PathConfiguration.SOLVED_ESTIMATIONS_DIR_PATH, self.estimation_name)
        self.results = self._load_all_results()

    def _load_all_results(self):
        """Walk `self.base_dir`, find all `solar_*` subfolders, then load
        every `market/ppa_*` `market.csv` found. Returns a list of
        dicts with `solar_percent`, `ppa_percent`, and monotone curve data.
        """
        results = []
        if not os.path.exists(self.base_dir):
            print(f"Directory not found: {self.base_dir}")
            return results

        for solar_folder in os.listdir(self.base_dir):
            solar_path = os.path.join(self.base_dir, solar_folder)
            if not os.path.isdir(solar_path) or not solar_folder.startswith("solar_"):
                continue

            # extract solar percent from folder name (solar_5 -> 0.05)
            try:
                raw = solar_folder.split('_', 1)[1]
                solar_percent_val = float(raw) / 100.0
            except Exception:
                # fallback default
                solar_percent_val = 0.0

            # If filtering by solar_percent, skip others
            if self.solar_percent is not None and solar_percent_val != self.solar_percent:
                continue

            market_base = os.path.join(solar_path, "market")
            if not os.path.exists(market_base):
                continue

            for ppa_folder in os.listdir(market_base):
                folder_path = os.path.join(market_base, ppa_folder)
                market_csv_path = os.path.join(folder_path, "market.csv")
                
                if not os.path.isdir(folder_path) or not os.path.exists(market_csv_path):
                    continue

                # extract ppa percent from folder name (ppa_50 -> 0.50)
                try:
                    ppa_raw = ppa_folder.split('_', 1)[1]
                    ppa_percent_val = float(ppa_raw) / 100.0
                except Exception:
                    # fallback
                    ppa_percent_val = 0.0

                # Load the solved dataframe
                try:
                    solved_df = ElectricityMarketSolvedDataframe(path=market_csv_path)
                    df_valid = solved_df.df[(solved_df.df["price"] > 0) & (solved_df.df["taken"] > 0)]
                    grouped = df_valid.groupby("hour").agg({"price": "first", "taken": "sum"}).reset_index()
                    sorted_grouped = grouped.sort_values(by="price", ascending=False)
                    sorted_grouped["cum_quantity"] = sorted_grouped["taken"].cumsum()
                    
                    results.append({
                        "solar_percent": solar_percent_val,
                        "solar_name": solar_folder,
                        "ppa_percent": ppa_percent_val,
                        "ppa_name": ppa_folder,
                        "market_csv_path": market_csv_path,
                        "images_dir": os.path.join(
                            PathConfiguration.IMAGES_DIR_PATH,
                            self.estimation_name,
                            solar_folder,
                            "market",
                            ppa_folder
                        ),
                        "solved_df": solved_df,
                        "cum_quantity": sorted_grouped["cum_quantity"].values,
                        "prices": sorted_grouped["price"].values
                    })
                except Exception as e:
                    print(f"Warning: Could not load {market_csv_path}: {e}")
                    continue

        # Sort by solar_percent then by ppa_percent
        return sorted(results, key=lambda x: (x["solar_percent"], x["ppa_percent"]))

    def plot_individual_results(self):
        """Generate and save individual plots (market_plots, monotone curve, and price history) for each result."""
        for result in self.results:
            images_dir = result["images_dir"]
            solved_df = result["solved_df"]
            ppa_name = result["ppa_name"]
            solar_name = result["solar_name"]
            
            print(f"Saving plots for {solar_name}/{ppa_name}")
            solved_df.save_all_plots(images_dir, update=self.update, show_dashed_lines=True)

    def plot_ppa_comparison_for_solar(self, solar_percent: float, output_dir: str = None):
        """Plot monotone price curves comparing different PPA percentages for a single solar percent."""
        entries = [r for r in self.results if r["solar_percent"] == solar_percent]
        if not entries:
            print(f"No results for solar_percent={solar_percent}")
            return

        plt.figure(figsize=(10, 6))
        cmap = plt.get_cmap('viridis')
        n = len(entries)
        
        for i, entry in enumerate(entries):
            if n > 1:
                color = cmap(i / (n - 1))
            else:
                color = cmap(0.5)
            
            ppa_label = f"PPA {int(entry['ppa_percent']*100)}%"
            plt.step(entry["cum_quantity"], entry["prices"], where='post', 
                    label=ppa_label, color=color, linewidth=2)
        
        plt.xlabel("Cumulative Quantity (MWh)")
        plt.ylabel("Market Price (€/MWh)")
        plt.title(f"Monotone Market Price Curve Comparison - {entries[0]['solar_name']}")
        plt.grid(True, alpha=0.3)
        plt.legend()
        
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            fname = os.path.join(output_dir, "monotone_price_curve_comparison.png")
            plt.savefig(fname, dpi=300, bbox_inches="tight")
            print(f"Plot saved to {fname}")
            plt.close()
        else:
            plt.show()

    def plot_ppa_comparison_all_solar(self, output_dir: str = None):
        """Plot monotone price curves for all solar percentages, with PPA percentages distinguished by color."""
        if not self.results:
            print("No results to plot.")
            return

        # Group by solar_percent
        groups = {}
        for r in self.results:
            sp = r["solar_percent"]
            groups.setdefault(sp, []).append(r)

        sorted_sps = sorted(groups.keys())
        n = len(sorted_sps)
        cmap = plt.cm.viridis
        norm = colors.Normalize(vmin=min(sorted_sps), vmax=max(sorted_sps)) if n > 0 else colors.Normalize(0, 1)

        plt.figure(figsize=(11, 7))
        for i, sp in enumerate(sorted_sps):
            entries = sorted(groups[sp], key=lambda x: x["ppa_percent"])
            # For each solar percent, take the first PPA percentage as a representative
            if entries:
                entry = entries[0]  # or could average them, or plot each separately
                frac = i / (n - 1) if n > 1 else 0
                color = cmap(frac)
                plt.step(entry["cum_quantity"], entry["prices"], where='post',
                        label=f"Solar {int(sp*100)}%", color=color, linewidth=2)

        plt.xlabel("Cumulative Quantity (MWh)")
        plt.ylabel("Market Price (€/MWh)")
        plt.title(f"Monotone Market Price Curves Across Solar Percentages ({self.estimation_name})")
        plt.grid(True, alpha=0.3)
        plt.legend()
        
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            fname = os.path.join(output_dir, "monotone_price_curve_comparison_all_solar.png")
            plt.savefig(fname, dpi=300, bbox_inches="tight")
            print(f"Plot saved to {fname}")
            plt.close()
        else:
            plt.show()


def main(estimation_name: str = None, update: bool = True):
    """Auto-discover and generate all plots: individual results and comparisons.
    
    If estimation_name is None, discovers all available estimations.
    If estimation_name is provided, processes only that estimation.
    """
    # If estimation_name is not provided, discover all estimations
    if estimation_name is None:
        solved_estimations_dir = PathConfiguration.SOLVED_ESTIMATIONS_DIR_PATH
        if not os.path.exists(solved_estimations_dir):
            print(f"Directory not found: {solved_estimations_dir}")
            return
        
        estimation_names = [d for d in os.listdir(solved_estimations_dir) 
                          if os.path.isdir(os.path.join(solved_estimations_dir, d))]
        
        for est_name in estimation_names:
            main(estimation_name=est_name, update=update)
        return
    
    # Process single estimation
    viz = MarketVisualizer(estimation_name=estimation_name, update=update)
    
    # Generate individual plots for all results
    print("\n" + "="*50)
    print(f"Generating individual market plots for: {estimation_name}")
    print("="*50)
    viz.plot_individual_results()
    
    # Get unique solar percentages for comparison plots
    solar_percents = sorted(set(r["solar_percent"] for r in viz.results))
    
    # Create per-solar comparisons
    print("\n" + "="*50)
    print("Generating per-solar PPA comparison plots")
    print("="*50)
    for solar_pct in solar_percents:
        images_dir = os.path.join(
            PathConfiguration.IMAGES_DIR_PATH,
            estimation_name,
            f"solar_{int(solar_pct*100)}",
            "market"
        )
        viz_for_solar = MarketVisualizer(estimation_name=estimation_name, solar_percent=solar_pct, update=update)
        viz_for_solar.plot_ppa_comparison_for_solar(solar_pct, output_dir=images_dir)
    
    # Create overall comparison across all solar percentages
    print("\n" + "="*50)
    print("Generating overall solar comparison plot")
    print("="*50)
    overall_images_dir = os.path.join(
        PathConfiguration.IMAGES_DIR_PATH,
        estimation_name,
        "comparisons"
    )
    viz.plot_ppa_comparison_all_solar(output_dir=overall_images_dir)


if __name__ == "__main__":
    main()
