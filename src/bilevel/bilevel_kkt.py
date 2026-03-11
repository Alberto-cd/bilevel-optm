import pyomo.environ as pe
import pyomo.opt as po

from ..data import ElectricityMarketCurvesDataframe, ElectricityMarketSolvedDataframe
from ..constants import MAIN_CSV, BILEVEL_SOLVED_CSV, BILEVEL_SOLVED_PLOTS, M_MARGIN_MULTIPLIER

class StrategicOfferingProblem():
    def __init__(self, path:str=MAIN_CSV, ppa:bool=False, battery:bool=False):
        self.df = ElectricityMarketCurvesDataframe(path)
        self.solved_df = None
        self.model = self.get_model()
        self.solver = po.SolverFactory('gurobi')

        self.ppa = ppa
        self.battery = battery

    def get_model(self):
        model = pe.ConcreteModel()
        
        # --- Sets ---
        model.generators = pe.Set(initialize=list(self.df.get_entities_name(True))) # j
        model.own_generators = pe.Set(initialize=list(self.df.get_entities_name(True, True))) # i - subset of generators
        model.external_generators = pe.Set(initialize=[j for j in model.generators if j not in model.own_generators])
        model.consumers = pe.Set(initialize=list(self.df.get_entities_name(False))) # l
        model.hours = pe.Set(initialize=list(self.df.get_hours())) # t
        
        # --- Parameters ---
        model.generator_marginal_cost = pe.Param(model.generators, 
                                                 model.hours, 
                                                 default=1_000_000, 
                                                 initialize=self.df.get_entities_column_dict("offer", True))
        model.generator_maximum_capacity = pe.Param(model.generators, model.hours, default=0, initialize=self.df.get_entities_column_dict("limit", True))
        model.demand_marginal_utility = pe.Param(model.consumers, model.hours, default=0, initialize=self.df.get_entities_column_dict("offer", False))
        model.demand_maximum = pe.Param(model.consumers, model.hours, default=0, initialize=self.df.get_entities_column_dict("limit", False))

        # --- Variables ---
        model.production = pe.Var(model.generators, model.hours, within = pe.NonNegativeReals)
        model.consumption = pe.Var(model.consumers, model.hours, within = pe.NonNegativeReals)

        # Duals for production bounds
        model.omega_q_min = pe.Var(model.generators, model.hours, within=pe.NonNegativeReals)  # for q_{j,t} >= 0
        model.omega_q_max = pe.Var(model.generators, model.hours, within=pe.NonNegativeReals)  # for q_{j,t} <= Q_{j,t}

        # Duals for consumption bounds
        model.omega_d_min = pe.Var(model.consumers, model.hours, within=pe.NonNegativeReals)   # for d_{l,t} >= 0
        model.omega_d_max = pe.Var(model.consumers, model.hours, within=pe.NonNegativeReals)   # for d_{l,t} <= D_{l,t}

        # Dual variable for power balance constraint (market price)
        model.lambda_power_balance = pe.Var(model.hours, within=pe.Reals)  # dual for power balance (equality)

        # Binary variables for big-M linearization
        model.z_q_min = pe.Var(model.generators, model.hours, within=pe.Binary)
        model.z_q_max = pe.Var(model.generators, model.hours, within=pe.Binary)
        model.z_d_min = pe.Var(model.consumers, model.hours, within=pe.Binary)
        model.z_d_max = pe.Var(model.consumers, model.hours, within=pe.Binary)

        # --- Objective function (Strategic: maximize own generator revenue) ---
        def obj_rule(model):
            # return sum(sum(model.lambda_power_balance[t] * model.production[i, t] for i in model.own_generators) for t in model.hours)
            return sum(sum(model.generator_maximum_capacity[i, t] * model.omega_q_max[i, t] for i in model.own_generators) for t in model.hours)
            # return sum( - sum(model.generator_marginal_cost[j, t] * model.production[j, t] for j in model.generators) 
            #             + sum(model.demand_marginal_utility[l, t] * model.consumption[l, t] for l in model.consumers) 
            #             - sum(model.z_d_max[l, t] * model.demand_maximum[l, t] for l in model.consumers) 
            #             - sum(model.z_q_max[j, t] * model.generator_maximum_capacity[j, t] for j in model.external_generators) 
            #            for t in model.hours)

        model.revenue = pe.Objective(rule = obj_rule, sense = pe.maximize)
        
        # --- Constraints ---
        def power_balance_rule(model, t):
            return sum(model.consumption[l, t] for l in model.consumers) - sum(model.production[j, t] for j in model.generators) == 0

        model.constraint_power_balance = pe.Constraint(model.hours, rule=power_balance_rule)

        def consumption_limit_rule(model, l, t):
            return model.demand_maximum[l, t] - model.consumption[l, t] >= 0

        model.constraint_consumption_limit = pe.Constraint(model.consumers, model.hours, rule=consumption_limit_rule)

        def production_limit_rule(model, j, t):
            return model.generator_maximum_capacity[j, t] - model.production[j, t] >= 0

        model.constraint_production_limit = pe.Constraint(model.generators, model.hours, rule=production_limit_rule)

        # *** Big-M linearized complementary slackness constraints ***
        # Get maximum possible market price from all offers (generators and consumers)
        max_market_price = self.df.df['offer'].max()
        # Generators: lower bound
        def bigm_q_min_dual_rule(model, j, t):
            m = max_market_price * M_MARGIN_MULTIPLIER
            return model.omega_q_min[j, t] <= m * (1 - model.z_q_min[j, t])
        model.bigm_q_min_dual = pe.Constraint(model.generators, model.hours, rule=bigm_q_min_dual_rule)

        def bigm_q_min_primal_rule(model, j, t):
            m = model.generator_maximum_capacity[j, t] * M_MARGIN_MULTIPLIER
            return model.production[j, t] <= m * model.z_q_min[j, t]
        model.bigm_q_min_primal = pe.Constraint(model.generators, model.hours, rule=bigm_q_min_primal_rule)

        # Generators: upper bound
        def bigm_q_max_dual_rule(model, j, t):
            m = max_market_price * M_MARGIN_MULTIPLIER
            return model.omega_q_max[j, t] <= m * (1 - model.z_q_max[j, t])
        model.bigm_q_max_dual = pe.Constraint(model.generators, model.hours, rule=bigm_q_max_dual_rule)

        def bigm_q_max_primal_rule(model, j, t):
            m = model.generator_maximum_capacity[j, t] * M_MARGIN_MULTIPLIER
            return model.generator_maximum_capacity[j, t] - model.production[j, t] <= m * model.z_q_max[j, t]
        model.bigm_q_max_primal = pe.Constraint(model.generators, model.hours, rule=bigm_q_max_primal_rule)

        # Demand: lower bound
        def bigm_d_min_dual_rule(model, l, t):
            m = max_market_price * M_MARGIN_MULTIPLIER
            return model.omega_d_min[l, t] <= m * (1 - model.z_d_min[l, t])
        model.bigm_d_min_dual = pe.Constraint(model.consumers, model.hours, rule=bigm_d_min_dual_rule)

        def bigm_d_min_primal_rule(model, l, t):
            m = model.demand_maximum[l, t] * M_MARGIN_MULTIPLIER
            return model.consumption[l, t] <= m * model.z_d_min[l, t]
        model.bigm_d_min_primal = pe.Constraint(model.consumers, model.hours, rule=bigm_d_min_primal_rule)

        # Demand: upper bound
        def bigm_d_max_dual_rule(model, l, t):
            m = max_market_price * M_MARGIN_MULTIPLIER
            return model.omega_d_max[l, t] <= m * (1 - model.z_d_max[l, t])
        model.bigm_d_max_dual = pe.Constraint(model.consumers, model.hours, rule=bigm_d_max_dual_rule)

        def bigm_d_max_primal_rule(model, l, t):
            m = model.demand_maximum[l, t] * M_MARGIN_MULTIPLIER
            return model.demand_maximum[l, t] - model.consumption[l, t] <= m * model.z_d_max[l, t]
        model.bigm_d_max_primal = pe.Constraint(model.consumers, model.hours, rule=bigm_d_max_primal_rule)

        # *** Stationarity constraints ***
        # For all generators and hours
        def stationarity_production_rule(model, j, t):
            return (model.generator_marginal_cost[j, t]
                - model.lambda_power_balance[t]
                - model.omega_q_min[j, t]
                + model.omega_q_max[j, t]
                == 0)
        model.stationarity_production = pe.Constraint(model.generators, model.hours, rule=stationarity_production_rule)

        # For all consumers and hours
        def stationarity_consumption_rule(model, l, t):
            return (-model.demand_marginal_utility[l, t]
                + model.lambda_power_balance[t]
                - model.omega_d_min[l, t]
                + model.omega_d_max[l, t]
                == 0)
        model.stationarity_consumption = pe.Constraint(model.consumers, model.hours, rule=stationarity_consumption_rule)

        num_constraints = len(list(model.component_data_objects(pe.Constraint, active=True)))
        num_variables = len(list(model.component_data_objects(pe.Var)))
        print(f"Number of constraints: {num_constraints}")
        print(f"Number of variables: {num_variables}")

        return model
    
    def solve(self):
        res = self.solver.solve(self.model, tee=True)

        if res.solver.status != 'ok':
            print("As the model was not solved, the result dataframe was not set.")
            return

        # Get market prices from lambda_power_balance variable
        market_price = {t: pe.value(self.model.lambda_power_balance[t]) for t in self.model.hours}

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
    
    def save_dataframe(self, *args):
        if self.solved_df is None:
            print("Unable to save dataframe: Dataframe not set.")
            return
        self.solved_df.save_dataframe(*args)

    def save_market_plots(self, **kwargs):
        if self.solved_df is None:
            print("Unable to save market plots: Dataframe not set.")
            return
        self.solved_df.save_market_plots(**kwargs)

def main():
    p = StrategicOfferingProblem()
    p.solve()
    p.save_dataframe(BILEVEL_SOLVED_CSV)
    p.save_market_plots(output_dir=BILEVEL_SOLVED_PLOTS, show_dashed_lines=True)

if __name__ == "__main__":
    main()