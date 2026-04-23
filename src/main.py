from .data import main as data_main
from .market.solver import main as market_solver_main
from .market.visualizer import main as market_visualizer_main
from .bilevel.solver import main as bilevel_solver_main
from .bilevel.visualizer import main as bilevel_visualizer_main


# Execution configuration constants
PPA_PERCENTS = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]


def _print_title(title: str):
    """Print a formatted title."""
    print(f"\n{'='*50}")
    print(title)
    print(f"{'='*50}")

def _print_subtitle(subtitle: str):
    """Print a formatted subtitle."""
    print(f"\n{'-'*50}")
    print(subtitle)
    print(f"{'-'*50}")

def _execute_test_estimations():
    """Execute solvers for test estimation set."""
    _print_title("Test Estimations")
    
    _print_subtitle("Executing: market.solver (test)")
    market_solver_main(estimation_name="test", solar_percent=0.0, ppa_percent=PPA_PERCENTS, update=False)
    
    _print_subtitle("Executing: market.visualizer (test)")
    market_visualizer_main(estimation_name="test", update=False)
    
    _print_subtitle("Executing: bilevel.solver (test)")
    bilevel_solver_main(estimation_name="test", solar_percent=0.0, ppa_price=list(range(-30, 16)), update=False)
    
    _print_subtitle("Executing: bilevel.visualizer (test)")
    bilevel_visualizer_main(estimation_name="test", update=False)


def _execute_test_2_estimations():
    """Execute solvers for test_2 estimation set."""
    _print_title("Test 2 Estimations")
    
    _print_subtitle("Executing: market.solver (test_2)")
    market_solver_main(estimation_name="test_2", solar_percent=0.0, ppa_percent=PPA_PERCENTS, update=False)
    
    _print_subtitle("Executing: market.visualizer (test_2)")
    market_visualizer_main(estimation_name="test_2", update=False)
    
    _print_subtitle("Executing: bilevel.solver (test_2)")
    bilevel_solver_main(estimation_name="test_2", solar_percent=0.0, ppa_price=list(range(-15, 16)), update=False)
    
    _print_subtitle("Executing: bilevel.visualizer (test_2)")
    bilevel_visualizer_main(estimation_name="test_2", update=False)


def _execute_estimations_2030():
    """Execute solvers for estimations_2030 dataset."""
    _print_title("Estimations 2030")
    
    _print_subtitle("Executing: data (estimations_2030)")
    data_main(
        base_estimations="market_data.json",
        profile="esios_profiles_processed2023.csv",
        estimation_name="estimations_2030",
        solar_percent=[0.0, 0.01, 0.05, 0.1, 0.2, 0.5, 1.0],
        update=False
    )
    
    _print_subtitle("Executing: market.solver (estimations_2030)")
    market_solver_main(
        estimation_name="estimations_2030",
        solar_percent=[0.0, 0.01, 0.05, 0.1, 0.2, 0.5, 1],
        ppa_percent=PPA_PERCENTS,
        update=False
    )
    
    _print_subtitle("Executing: market.visualizer (estimations_2030)")
    market_visualizer_main(estimation_name="estimations_2030", update=False)
    
    _print_subtitle("Executing: bilevel.solver (estimations_2030 - solar_percent=0.01)")
    bilevel_solver_main(
        estimation_name="estimations_2030",
        solar_percent=0.01,
        ppa_price=[x/10 for x in range(12*10, 13*10 + 1)],
        update=False
    )
    
    _print_subtitle("Executing: bilevel.solver (estimations_2030 - solar_percent=0.05)")
    bilevel_solver_main(
        estimation_name="estimations_2030",
        solar_percent=0.05,
        ppa_price=[x/2 for x in range(9*2, 16*2 + 1)],
        update=False
    )
    
    _print_subtitle("Executing: bilevel.solver (estimations_2030 - solar_percent=0.1)")
    bilevel_solver_main(
        estimation_name="estimations_2030",
        solar_percent=0.1,
        ppa_price=[x/2 for x in range(5*2, 20*2 + 1)],
        update=False
    )
    
    _print_subtitle("Executing: bilevel.solver (estimations_2030 - solar_percent=0.2)")
    bilevel_solver_main(
        estimation_name="estimations_2030",
        solar_percent=0.2,
        ppa_price=list(range(0, 31)),
        update=False
    )
    
    _print_subtitle("Executing: bilevel.visualizer (estimations_2030)")
    bilevel_visualizer_main(estimation_name="estimations_2030", update=False)


def main():
    """Execute all solvers with explicit function calls."""
    
    try:
        _execute_test_estimations()
        _execute_test_2_estimations()
        _execute_estimations_2030()
        
        print("\n" + "="*50)
        print("EXECUTION COMPLETED SUCCESSFULLY")
        print("="*50)
        
    except KeyboardInterrupt:
        print("\nExecution cancelled by user. Exiting...")
        return
    except Exception as e:
        print(f"An error occurred during execution: {e}")
        raise

if __name__ == "__main__":
    main()
