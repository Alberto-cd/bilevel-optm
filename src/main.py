import importlib
import itertools
import os
from .configuration import PathConfiguration, ExecutionConfiguration

def main():
    # 2. Execute solvers
    print("\n" + "="*50)
    print("STEP: Executing Solvers")
    print("="*50)
    
    solvers = ExecutionConfiguration.SOLVERS
    
    for solver_opt in solvers:
        module_path = solver_opt["module"]
        base_args = solver_opt.get("args", {})
        
        # Extract non-list parameters like 'update' that should be passed to all iterations
        non_list_params = {}
        list_args = {}
        for k, v in base_args.items():
            if isinstance(v, (list, range)):
                list_args[k] = v
            else:
                non_list_params[k] = v
        
        # If there are multiple list-valued parameters, treat the first list-valued
        # parameter as the outer sweep and pass other list-valued parameters through
        # intact (so modules can receive lists for comparison plots).
        list_keys = [k for k in list_args.keys()]
        if len(list_keys) > 1:
            outer_key = list_keys[0]
            outer_values = list(list_args[outer_key])
            for outer_val in outer_values:
                args = {**non_list_params}
                for k, v in list_args.items():
                    if k == outer_key:
                        args[k] = outer_val
                    else:
                        args[k] = list(v)

                print(f"\n{'='*50}")
                print(f"Executing: {module_path}")
                print(f"Args: {args}")
                print(f"{'='*50}\n")

                full_module_path = f"src.{module_path}"
                try:
                    module = importlib.import_module(full_module_path)
                    if hasattr(module, 'main'):
                        module.main(**args)
                    else:
                        print(f"Error: Module {full_module_path} does not have a 'main' function.")
                except ImportError as e:
                    print(f"Error importing {full_module_path}: {e}")
                except KeyboardInterrupt:
                    print("\nExecution cancelled by user. Exiting...")
                    return
                except Exception as e:
                    print(f"An error occurred during execution of {module_path}: {e}")
            continue

        # Collect all parameter keys and their values (normalizing to lists)
        param_names = []
        param_values = []
        for key, value in list_args.items():
            param_names.append(key)
            if isinstance(value, (list, range)):
                param_values.append(list(value))
            else:
                param_values.append([value])

        # Create Cartesian product of all parameters for multidimensional sweep
        # e.g. every solar_percent with every ppa_price
        for combination in itertools.product(*param_values):
            args = dict(zip(param_names, combination))
            # Add non-list parameters to the args
            args.update(non_list_params)

            print(f"\n{'='*50}")
            print(f"Executing: {module_path}")
            print(f"Args: {args}")
            print(f"{'='*50}\n")

            full_module_path = f"src.{module_path}"

            try:
                module = importlib.import_module(full_module_path)
                if hasattr(module, 'main'):
                    module.main(**args)
                else:
                    print(f"Error: Module {full_module_path} does not have a 'main' function.")
            except ImportError as e:
                print(f"Error importing {full_module_path}: {e}")
            except KeyboardInterrupt:
                print("\nExecution cancelled by user. Exiting...")
                return
            except Exception as e:
                print(f"An error occurred during execution of {module_path}: {e}")

if __name__ == "__main__":
    main()
