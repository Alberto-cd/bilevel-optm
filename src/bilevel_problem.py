import pyomo.environ as pe
import pyomo.opt as po

from scipy.optimize import minimize

from object_utils import ElectricityMarketDataframe


class BilivelProblem():
    def __init__(self, df: ElectricityMarketDataframe, years: int = 10):
        self.df: ElectricityMarketDataframe = df
        self.years = years
        self.model = None
        self.solver = po.SolverFactory('gurobi')
        self.reset_lower_level()

    def reset_lower_level(self):
        model = pe.ConcreteModel()
        
        # Sets
        model.generators = pe.Set(initialize=[self.df.get]) # j
        model.consumers = pe.Set(initialize=list(self.consumers_data)) # l
        model.years = pe.Set(initialize=list(range(self.years))) # y
        model.hours = pe.Set(initialize=list(range(24*365*self.years))) # t
        
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

        # Set dual
        model.dual = pe.Suffix(direction=pe.Suffix.IMPORT)

        self.model = model
    
    def get_dict_index(self, dictionary, key):
        return {k: v[key] for k, v in dictionary.items()}
    
    def solve_lower_level(self):
        result = self.solver.solve(self.model, tee=False)
        market_price = self.model.dual[self.model.constraint_power_balance]
        return result, market_price
    
    def upper_objective(self):

    
    def solve(self):

        return minimize(self.upper_objective,
                        self.get_dict_index(self.own_generators_data, "cost"),
                        method='Nelder-Mead',
                        options={'maxiter': 15, 'disp':True})


def main():
    path = "../data/curva_pbc_20251126.csv"
    df = ElectricityMarketDataframe(path)
    df.get_var_vector()
    df.get_var_dict()

    problem = BilivelProblem()


if __name__ == "__main__":
    main()