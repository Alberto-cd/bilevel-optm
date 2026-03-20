import importlib
from .constants import ESTIMATIONS_TO_SOLVE

def main():
    solvers = ESTIMATIONS_TO_SOLVE.get("solvers", [])

    if not solvers:
        print("No solvers specified in ESTIMATIONS_TO_SOLVE['solvers'].")
        return

    for solver_opt in solvers:
        module_path = solver_opt["module"]
        args = solver_opt.get("args", {})
        
        print(f"\n{'='*50}")
        print(f"Executing: {module_path} with args: {args}")
        print(f"{'='*50}\n")

        # Full module path for importlib
        full_module_path = f"src.{module_path}"
        
        try:
            # Dynamically import the module
            module = importlib.import_module(full_module_path)
            
            # Call the main function with unpacked arguments
            if hasattr(module, 'main'):
                module.main(**args)
            else:
                print(f"Error: Module {full_module_path} does not have a 'main' function.")
                
        except ImportError as e:
            print(f"Error importing {full_module_path}: {e}")
        except Exception as e:
            print(f"An error occurred during execution of {module_path}: {e}")

if __name__ == "__main__":
    main()
