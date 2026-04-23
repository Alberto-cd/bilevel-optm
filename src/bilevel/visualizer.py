import os
import json
import matplotlib.pyplot as plt
from matplotlib import colors
from ..data import ElectricityMarketSolvedDataframe
from ..configuration import PathConfiguration


class PPAVisualizer():
    """Auto-discovers bilevel PPA results and provides plotting helpers
    for individual plots and comparisons.
    """
    def __init__(self, estimation_name: str, update: bool = True):
        if estimation_name is None:
            raise ValueError("estimation_name is required")
        self.estimation_name = estimation_name
        self.update = update
        self.base_dir = os.path.join(PathConfiguration.SOLVED_ESTIMATIONS_DIR_PATH, self.estimation_name)
        self.results = self._load_all_results()

    def _load_all_results(self):
        """Walk `self.base_dir`, find all `solar_*` subfolders, then load
        every `bilevel_ppa/ppa_*` result. Returns a list of dicts with
        metadata and solved dataframe for individual plots.
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
                solar_percent = float(raw) / 100.0
            except Exception:
                # fallback default
                solar_percent = 0.0

            ppa_base = os.path.join(solar_path, "bilevel_ppa")
            if not os.path.exists(ppa_base):
                continue

            for ppa_folder in os.listdir(ppa_base):
                folder_path = os.path.join(ppa_base, ppa_folder)
                info_path = os.path.join(folder_path, "info.json")
                results_csv_path = os.path.join(folder_path, "results.csv")
                
                if not os.path.isdir(folder_path) or not os.path.exists(info_path):
                    continue

                with open(info_path, 'r') as f:
                    data = json.load(f)

                # Try to extract price from folder name `ppa_50` -> 50
                try:
                    price = float(ppa_folder.split('_', 1)[1])
                except Exception:
                    # If not available, try info.json keys or leave None
                    price = data.get("ppa_price") or data.get("price") or None

                # Load solved dataframe if available
                solved_df = None
                if os.path.exists(results_csv_path):
                    try:
                        solved_df = ElectricityMarketSolvedDataframe(path=results_csv_path)
                    except Exception as e:
                        print(f"Warning: Could not load {results_csv_path}: {e}")

                images_dir = os.path.join(
                    PathConfiguration.IMAGES_DIR_PATH,
                    self.estimation_name,
                    solar_folder,
                    "bilevel_ppa",
                    ppa_folder
                )

                results.append({
                    "solar_percent": solar_percent,
                    "solar_name": solar_folder,
                    "ppa_folder": ppa_folder,
                    "price": price,
                    "ppa_percentage": data.get("ppa_percentage", 0),
                    "profit": data.get("strategic_profit", 0),
                    "time": data.get("execution_time_seconds", 0),
                    "solved_df": solved_df,
                    "images_dir": images_dir
                })

        # Sort first by solar_percent then by price (None prices go last)
        return sorted(results, key=lambda x: (x["solar_percent"], x["price"] is None, x["price"]))

    def _check_individual_plots_exist(self, images_dir: str) -> bool:
        """Check if individual plots already exist in the images directory.
        Checks for both the monotone price curve and at least one market hour plot."""
        monotone_exists = os.path.exists(os.path.join(images_dir, "monotone_price_curve.png"))
        # Check if at least one market_hour plot exists
        market_plots_exist = False
        if os.path.exists(images_dir):
            market_plots_exist = any(f.startswith("market_hour_") and f.endswith(".png") 
                                     for f in os.listdir(images_dir))
        return monotone_exists and market_plots_exist

    def plot_individual_results(self):
        """Generate and save individual plots for each result (if solved_df is available)."""
        for result in self.results:
            if result["solved_df"] is None:
                print(f"Skipping plots for {result['solar_name']}/{result['ppa_folder']} (no solved dataframe)")
                continue
            
            images_dir = result["images_dir"]
            solved_df = result["solved_df"]
            ppa_folder = result["ppa_folder"]
            solar_name = result["solar_name"]
            
            # Check if plots already exist and update flag is False
            if not self.update and self._check_individual_plots_exist(images_dir):
                print(f"Skipping (already exists): {solar_name}/{ppa_folder}")
                continue
            
            print(f"Saving plots for {solar_name}/{ppa_folder}")
            os.makedirs(images_dir, exist_ok=True)
            
            # Save market plots and monotone curve
            solved_df.save_market_plots(images_dir, show_dashed_lines=True)
            solved_df.save_monotone_price_curve(output_dir=images_dir)

    def plot_price_vs_percentage_for(self, solar_percent: float, output_dir: str = None):
        """Plot PPA price vs PPA percentage for a single solar percent."""
        entries = [r for r in self.results if r["solar_percent"] == solar_percent]
        if not entries:
            print(f"No results for solar_percent={solar_percent}")
            return

        prices = [r["price"] for r in entries]
        percentages = [r["ppa_percentage"] * 100 for r in entries]

        plt.figure(figsize=(10, 6))
        plt.plot(prices, percentages, marker='o', linestyle='-', color='b', linewidth=2)
        plt.xlabel("PPA Price (€/MWh)")
        plt.ylabel("PPA Percentage (%)")
        plt.title(f"PPA Price vs Percentage Sensitivity (solar_{int(solar_percent*100)})")
        plt.grid(True, alpha=0.3)
        plt.ylim(-5, 105)

        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            fname = os.path.join(output_dir, f"ppa_price_vs_percentage_solar_{int(solar_percent*100)}.png")
            plt.savefig(fname, dpi=300, bbox_inches="tight")
            print(f"Plot saved to {fname}")
            plt.close()

    def plot_price_vs_percentage_all(self, output_dir: str = None):
        """Plot PPA price vs percentage for all discovered solar percentages
        in the same axis, using a color gradient to indicate solar percent.
        """
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
            entries = sorted(groups[sp], key=lambda x: (x["price"] is None, x["price"]))
            prices = [e["price"] for e in entries]
            percentages = [e["ppa_percentage"] * 100 for e in entries]
            if not prices:
                continue
            # fraction for color mapping
            frac = i / (n - 1) if n > 1 else 0
            color = cmap(frac)
            plt.plot(prices, percentages, marker='o', linestyle='-', color=color, linewidth=2, label=f"{int(sp*100)}%")

        plt.xlabel("PPA Price (€/MWh)")
        plt.ylabel("PPA Percentage (%)")
        plt.title(f"PPA Price vs Percentage Across Solar Percents ({self.estimation_name})")
        plt.grid(True, alpha=0.3)
        plt.ylim(-5, 105)
        plt.legend(title='Solar %', bbox_to_anchor=(1.02, 1), loc='upper left')

        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            fname = os.path.join(output_dir, "ppa_price_vs_percentage_all_solar.png")
            plt.savefig(fname, dpi=300, bbox_inches="tight")
            print(f"Plot saved to {fname}")
            plt.close()


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
    viz = PPAVisualizer(estimation_name=estimation_name, update=update)
    
    # Generate individual plots for all results
    print("\n" + "="*50)
    print(f"Generating individual bilevel PPA plots for: {estimation_name}")
    print("="*50)
    viz.plot_individual_results()
    
    # Get unique solar percentages for comparison plots
    solar_percents = sorted(set(r["solar_percent"] for r in viz.results))
    
    # Create per-solar comparisons
    print("\n" + "="*50)
    print("Generating per-solar PPA price vs percentage plots")
    print("="*50)
    for solar_pct in solar_percents:
        images_dir = os.path.join(
            PathConfiguration.IMAGES_DIR_PATH,
            estimation_name,
            f"solar_{int(solar_pct*100)}",
            "bilevel_ppa"
        )
        viz.plot_price_vs_percentage_for(solar_pct, output_dir=images_dir)
    
    # Create overall comparison across all solar percentages
    print("\n" + "="*50)
    print("Generating overall comparison plot")
    print("="*50)
    images_dir = os.path.join(
        PathConfiguration.IMAGES_DIR_PATH,
        estimation_name,
        "comparisons"
    )
    viz.plot_price_vs_percentage_all(output_dir=images_dir)


if __name__ == "__main__":
    main()