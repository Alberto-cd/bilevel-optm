# module for building the pyomo model
import pyomo.environ as pe
# module for solving the pyomo model
import pyomo.opt as po

from scipy.optimize import minimize
from utils import draw_clearing_market

def get_lower_level_model(offer, production_limit):
    '''
    Gets the market clearing model.
    '''
    if list(offer) != list(production_limit):
        raise ValueError
    
    model = pe.ConcreteModel()

    # Sets
    model.demands = pe.Set(initialize=['d1', 'd2']) # k
    model.own_generators = pe.Set(initialize=list(offer)) # i
    model.external_generators = pe.Set(initialize=['eg1', 'eg2']) # j

    # Parameters
    model.consumption_limit = pe.Param(model.demands, default=0, initialize = {
        'd1': 100,
        'd2': 50
    })
    model.own_production_limit = pe.Param(model.own_generators, default=0, initialize=production_limit)
    model.external_production_limit = pe.Param(model.external_generators, default=0, initialize = {
        'eg1': 100,
        'eg2': 50
    })
    model.demand_bid = pe.Param(model.demands, default=0, initialize = {
        'd1': 40,
        'd2': 42
    })
    model.own_generators_offer = pe.Param(model.own_generators, default=0, initialize=offer, mutable=True)
    model.external_generators_offer = pe.Param(model.external_generators, default=0, initialize = {
        'eg1': 11,
        'eg2': 13
    })

    # Variables
    model.consumption = pe.Var(model.demands, within = pe.NonNegativeReals)
    model.own_production = pe.Var(model.own_generators, within = pe.NonNegativeReals)
    model.external_production = pe.Var(model.external_generators, within = pe.NonNegativeReals)

    # Objective function
    def obj_rule(model):
        return sum(model.demand_bid[k] * model.consumption[k] for k in model.demands) - sum(model.own_generators_offer[i] * model.own_production[i] for i in model.own_generators) - sum(model.external_generators_offer[j] * model.external_production[j] for j in model.external_generators)

    model.cost = pe.Objective(rule = obj_rule, sense = pe.maximize)

    # Constraint
    def power_balance_rule(model):
        return sum(model.consumption[k] for k in model.demands) - sum(model.own_production[i] for i in model.own_generators) - sum(model.external_production[j] for j in model.external_generators) == 0

    model.constraint_power_balance = pe.Constraint(rule=power_balance_rule)

    def consumption_limit_rule(model, k):
        return model.consumption[k] <= model.consumption_limit[k]

    model.constraint_consumption_limit = pe.Constraint(model.demands, rule=consumption_limit_rule)

    def own_production_limit_rule(model, i):
        return model.own_production[i] <= model.own_production_limit[i]

    model.constraint_own_production_limit = pe.Constraint(model.own_generators, rule=own_production_limit_rule)
    
    def external_production_limit_rule(model, j):
        return model.external_production[j] <= model.external_production_limit[j]

    model.constraint_external_production_limit = pe.Constraint(model.external_generators, rule=external_production_limit_rule)

    # Set dual
    model.dual = pe.Suffix(direction=pe.Suffix.IMPORT)

    return model

def make_upper_objective(costs, production_limit, initial_offer_list):
    """
    Returns a function f(alpha_vector) -> -profit
    alpha_vector is in the same order as costs.keys()
    """
    own_generators_list = list(costs)
    
    initial_offer = {g: initial_offer_list[i] for i,g in enumerate(own_generators_list)}
    model = get_lower_level_model(initial_offer, production_limit)

    def obj(alpha_vec):
        offers = {g: alpha_vec[i] for i,g in enumerate(own_generators_list)}

        # model = get_lower_level_model(offers, costs)
        # model.own_generators_offer = pe.Param(model.own_generators, default=0, initialize=offers)
        for g in own_generators_list:
            model.own_generators_offer[g] = offers[g]

        solver = po.SolverFactory('gurobi')
        res = solver.solve(model, tee=False)

        market_price = model.dual[model.constraint_power_balance]
        
        draw_clearing_market(
            list(model.demands), 
            list(model.own_generators), 
            list(model.external_generators),
            {k: pe.value(model.consumption_limit[k]) for k in model.demands},
            {k: pe.value(model.own_production_limit[k]) for k in model.own_generators},
            {k: pe.value(model.external_production_limit[k]) for k in model.external_generators},
            {k: pe.value(model.demand_bid[k]) for k in model.demands},
            {k: pe.value(model.own_generators_offer[k]) for k in model.own_generators},
            {k: pe.value(model.external_generators_offer[k]) for k in model.external_generators},
            market_price, 
            sum([pe.value(model.consumption[k]) for k in model.demands])
        )
        print(f"{market_price = }")
        print(f"{offers = }")
        print("-"*50)
        profit = sum(pe.value(model.own_production[g]) * (market_price - costs[g]) for g in own_generators_list)

        return -profit

    return obj

def main():
    # your generators marginal costs C_i
    costs = {
        'og1': 1,
        'og2': 2
    }
    production_limit = {
        'og1': 100,
        'og2': 50
    }
    # initial guess for their offer prices αᵢ^offer
    # x0 = [3.0, 5.0]
    x0 = [1.35, 10.75]

    upper_obj = make_upper_objective(costs, production_limit, x0)
    result = minimize(upper_obj,
                      x0,
                      method='Nelder-Mead',
                      options={'maxiter': 15, 'disp':True})

    print("Optimal offers:", result.x)
    print("Max profit    :", -result.fun)

if __name__ == "__main__":
    main()
