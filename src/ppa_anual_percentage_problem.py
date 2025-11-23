# module for building the pyomo model
import pyomo.environ as pe
# module for solving the pyomo model
import pyomo.opt as po

from scipy.optimize import minimize
from utils import draw_continous_market_price_vs_ppa_percentage
from object_utils import ElectricityMarketDataframe
import os

hours_base = []
market_prices_history = []
ppa_percentage_history = dict()
offers_history = dict()

def get_lower_level_model(df: ElectricityMarketDataframe):
    '''
    Gets the market clearing model.
    '''
    
    model = pe.ConcreteModel()

    # Sets
    model.generators = pe.Set(initialize=df.get_entities_name(True)) # j
    model.consumers = pe.Set(initialize=df.get_entities_name(False)) # l
    model.years = pe.Set(initialize=df.get_years())
    model.hours = pe.Set(initialize=df.get_hours()) # t

    # Parameters
    model.generator_marginal_cost = pe.Param(model.generators, model.hours, default=1_000_000, initialize = df.get_entities_column_dict("offer", True), mutable=True)
    model.demand_marginal_utility = pe.Param(model.consumers, model.hours, default=0, initialize = df.get_entities_column_dict("offer", False))
    model.generator_maximum_capacity = pe.Param(model.generators, model.hours, default=0, initialize = df.get_entities_column_dict("limit", True), mutable=True)
    model.demand_maximum = pe.Param(model.consumers, model.hours, default=0, initialize = df.get_entities_column_dict("limit", False))

    # model.production_percentage = pe.Param(model.generators, model.years, default=0, initialize = {})
    # model.ppa_price = pe.Param(10)

    # Variables
    model.production = pe.Var(model.generators, model.hours, within = pe.NonNegativeReals)
    model.consumption = pe.Var(model.consumers, model.hours, within = pe.NonNegativeReals)

    # Objective function
    def obj_rule(model):
        return sum(model.demand_marginal_utility[l, t] * model.consumption[l, t] for l in model.consumers for t in model.hours) - sum(model.generator_marginal_cost[j, t] * model.production[j, t] for j in model.generators for t in model.hours)

    model.cost = pe.Objective(rule = obj_rule, sense = pe.maximize)

    # Constraint
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

    return model

def make_upper_objective(df: ElectricityMarketDataframe):
    """
    Returns a function f(alpha_vector) -> -profit
    alpha_vector is in the same order as costs.keys()
    """
    model = get_lower_level_model(df)
    production_limit = df.get_entities_column_dict("limit", True, True)
    own_generators = df.get_entities_name(True, True)
    hours = df.get_hours()
    global hours_base 
    hours_base = list(range(len(hours)))
    global ppa_percentage_history 
    ppa_percentage_history = {g: [] for g in own_generators}
    global offers_history 
    offers_history = {g: [] for g in own_generators}
    PPA_PRICE = 10

    def obj(vec):
        own_generators_offer, own_generators_ppa_percentage = df.get_var_dict(vec)

        # model = get_lower_level_model(offers, costs)
        # model.own_generators_offer = pe.Param(model.own_generators, default=0, initialize=offers)
        for g in own_generators:
            for t in hours:
                model.generator_marginal_cost[g, t] = own_generators_offer[(g, t)]
            
                model.generator_maximum_capacity[g, t] = production_limit[(g, t)]*(1 - min(max(own_generators_ppa_percentage[(g, t)], 0), 1))

        solver = po.SolverFactory('gurobi')
        res = solver.solve(model, tee=False)
 
        market_prices = {t: model.dual[model.constraint_power_balance[t]] for t in hours}
        market_prices_history.append([model.dual[model.constraint_power_balance[t]] for t in hours])
        for g in own_generators:
            ppa_percentage_history[g].append([min(max(own_generators_ppa_percentage[(g, t)], 0), 1) for t in hours])
            offers_history[g].append([own_generators_offer[(g, t)] for t in hours])

        profit = sum(
            pe.value(model.production[g, t]) * (market_prices[t]) +
            PPA_PRICE*own_generators_ppa_percentage[(g, t)]*production_limit[(g, t)] -
            pe.value(model.generator_marginal_cost[g, t])*(pe.value(model.production[g, t]) + own_generators_ppa_percentage[(g, t)]*production_limit[(g, t)])
            for t in hours for g in own_generators
        )

        return -profit

    return obj

def main():
    os.makedirs("../data", exist_ok=True)
    os.makedirs("../images", exist_ok=True)
    path = "../data/example_complete.csv"
    df = ElectricityMarketDataframe(path)
    x0 = df.get_var_vector()

    upper_obj = make_upper_objective(df)
    result = minimize(upper_obj,
                      x0,
                      method='Nelder-Mead',
                      options={'maxiter': 50, 'disp':True})

    print("Optimal offers:", result.x)
    print("Max profit    :", -result.fun)

    own_generators = df.get_entities_name(True, True)
    for g in own_generators:
        draw_continous_market_price_vs_ppa_percentage(
            hours_base,
            market_prices_history,
            ppa_percentage_history[g],
            offers_history[g],
            f"../images/{g}_mp_vs_ppa.png"
        )

if __name__ == "__main__":
    main()
