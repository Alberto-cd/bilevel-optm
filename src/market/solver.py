import pyomo.environ as pe
import pyomo.opt as po
import os

from ..data import ElectricityMarketCurvesDataframe, ElectricityMarketSolvedDataframe
from ..configuration import PathConfiguration

class MarketClearingProblem():
    def __init__(self, path: str, ppa_percentage: float = 0.0):
        # Load base dataframe
        self.df = ElectricityMarketCurvesDataframe(path)
        # If a PPA percentage is provided, reduce own generators' limits before building the model
        if ppa_percentage and ppa_percentage > 0.0:
            self.df.df = self.df.df.copy()
            self.df.df["limit"] = self.df.df["limit"].astype(float)
            own_mask = (self.df.df["is_generator"]) & (self.df.df["own"])
            self.df.df.loc[own_mask, "limit"] = self.df.df.loc[own_mask, "limit"] * (1 - float(ppa_percentage))

        self.solved_df = None
        self.model = self.get_model()
        self.solver = po.SolverFactory('gurobi')

    def get_model(self):
        model = pe.ConcreteModel()
        
        # Set dual
        model.dual = pe.Suffix(direction=pe.Suffix.IMPORT)
        
        # Sets
        model.generators = pe.Set(initialize=list(self.df.get_entities_name(True))) # j
        model.consumers = pe.Set(initialize=list(self.df.get_entities_name(False))) # l
        model.years = pe.Set(initialize=list(self.df.get_years())) # y
        model.hours = pe.Set(initialize=list(self.df.get_hours())) # t
        
        # Parameters
        model.generator_marginal_cost = pe.Param(model.generators, 
                                                 model.hours, 
                                                 default=1_000_000, 
                                                 initialize=self.df.get_entities_column_dict("offer", True))
        model.generator_maximum_capacity = pe.Param(model.generators, model.hours, default=0, initialize=self.df.get_entities_column_dict("limit", True))
        model.demand_marginal_utility = pe.Param(model.consumers, model.hours, default=0, initialize=self.df.get_entities_column_dict("offer", False))
        model.demand_maximum = pe.Param(model.consumers, model.hours, default=0, initialize=self.df.get_entities_column_dict("limit", False))

        # Variables
        model.production = pe.Var(model.generators, model.hours, within = pe.NonNegativeReals)
        model.consumption = pe.Var(model.consumers, model.hours, within = pe.NonNegativeReals)

        # Objective function
        def obj_rule(model):
            return sum(sum(model.demand_marginal_utility[l, t] * model.consumption[l, t] for l in model.consumers) - sum(model.generator_marginal_cost[j, t] * model.production[j, t] for j in model.generators) for t in model.hours)

        model.cost = pe.Objective(rule = obj_rule, sense = pe.maximize)
        
        # Constraints
        def power_balance_rule(model, t):
            return sum(model.consumption[l, t] for l in model.consumers) - sum(model.production[j, t] for j in model.generators) == 0

        model.constraint_power_balance = pe.Constraint(model.hours, rule=power_balance_rule)

        def consumption_limit_rule(model, l, t):
            return model.consumption[l, t] <= model.demand_maximum[l, t]

        model.constraint_consumption_limit = pe.Constraint(model.consumers, model.hours, rule=consumption_limit_rule)

        def production_limit_rule(model, j, t):
            return model.production[j, t] <= model.generator_maximum_capacity[j, t]

        model.constraint_production_limit = pe.Constraint(model.generators, model.hours, rule=production_limit_rule)

        num_constraints = len(list(model.component_data_objects(pe.Constraint, active=True)))
        num_variables = len(list(model.component_data_objects(pe.Var)))
        print(f"Number of constraints: {num_constraints}")
        print(f"Number of variables: {num_variables}")

        return model
    
    def solve(self):
        self.solver.solve(self.model, tee=False)

        # Get market prices (dual of power balance constraint)
        market_price = {t: self.model.dual[self.model.constraint_power_balance[t]] for t in self.model.hours}

        # Get taken for all entities (generators: production, consumers: consumption)
        taken = {}
        # Generators
        for j in self.model.generators:
            for t in self.model.hours:
                taken[(j, t)] = pe.value(self.model.production[j, t])
        # Consumers
        for l in self.model.consumers:
            for t in self.model.hours:
                taken[(l, t)] = pe.value(self.model.consumption[l, t])

        # Store raw results so caller can re-create solved dataframe with different ppa percentages
        self.taken = taken
        self.market_price = market_price

        # Default solved dataframe without PPA reduction applied
        solved_df = ElectricityMarketSolvedDataframe(self.df, taken=taken, prices=market_price)
        self.solved_df = solved_df

def _check_market_files_exist(solved_path: str) -> bool:
    """Check if the market output files already exist."""
    return os.path.exists(solved_path)

def main(estimation_name: str, solar_percent: float = 0.0, ppa_percent=0.0, update: bool = True):
    # Handle list-type solar_percent parameter (iterate over solar percentages)
    if isinstance(solar_percent, (list, tuple)):
        for solar in solar_percent:
            main(estimation_name=estimation_name, solar_percent=solar, ppa_percent=ppa_percent, update=update)
        return
    
    # Handle list-type ppa_percent parameter (iterate over ppa percentages)
    if isinstance(ppa_percent, (list, tuple)):
        for ppa in ppa_percent:
            main(estimation_name=estimation_name, solar_percent=solar_percent, ppa_percent=ppa, update=update)
        return
    
    # Single scalar values - do the actual computation
    percent_name = f"solar_{int(solar_percent*100)}"
    path = os.path.join(PathConfiguration.ESTIMATIONS_DIR_PATH, estimation_name, f"{percent_name}.csv")

    scalar_ppa = float(ppa_percent) if ppa_percent else 0.0
    ppa_name = f"ppa_{int(scalar_ppa*100)}"
    
    # Hierarchical solved and images directories
    solved_dir = os.path.join(PathConfiguration.SOLVED_ESTIMATIONS_DIR_PATH, estimation_name, percent_name, "market", ppa_name)
    solved_path = os.path.join(solved_dir, "market.csv")
    
    # Check if files already exist and update flag is False
    if not update and _check_market_files_exist(solved_path):
        print(f"Skipping (already exists): solar={int(solar_percent*100)}% ppa={int(scalar_ppa*100)}%")
        return
    
    print(f"Computing: solar={int(solar_percent*100)}% ppa={int(scalar_ppa*100)}%")
    
    # Build and solve the market with own-generator limits reduced by the PPA percentage
    p = MarketClearingProblem(path, ppa_percentage=scalar_ppa)
    p.solve()

    # Solved dataframe already reflects the reduced limits (constructed from p.df)
    solved_df = ElectricityMarketSolvedDataframe(p.df, taken=p.taken, prices=p.market_price)

    # Save solved dataframe
    os.makedirs(solved_dir, exist_ok=True)
    solved_df.save_dataframe(solved_path)

if __name__ == "__main__":
    main()