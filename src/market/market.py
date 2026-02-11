import pyomo.environ as pe
import pyomo.opt as po

from ..data import ElectricityMarketCurvesDataframe, ElectricityMarketSolvedDataframe
from ..constants import MAIN_CSV, SOLVED_CSV, SOLVED_PLOTS

class MarketClearingProblem():
    def __init__(self, path:str=MAIN_CSV):
        self.df = ElectricityMarketCurvesDataframe(path)
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

        # Build solved dataframe
        solved_df = ElectricityMarketSolvedDataframe(self.df, taken=taken, prices=market_price)
        self.solved_df = solved_df

def main():
    p = MarketClearingProblem()
    p.solve()
    p.solved_df.save_dataframe(SOLVED_CSV)
    p.solved_df.save_market_plots(SOLVED_PLOTS)

if __name__ == "__main__":
    main()