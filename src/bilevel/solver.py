import pyomo.environ as pe
import pyomo.opt as po
import os
import json
import time
import numpy as np

from ..data import ElectricityMarketCurvesDataframe, ElectricityMarketSolvedDataframe
from ..configuration import PathConfiguration, ExecutionConfiguration

class StrategicOfferingProblem():
    def __init__(self, path:str, ppa_price:float|int|None=None, battery:bool=False, solver_timeout:int=None, m_margin_multiplier:float=None):
        self.ppa_price = ppa_price
        self.ppa = ppa_price is not None
        self.battery = battery
        
        # Use provided values or fall back to ExecutionConfiguration defaults
        if solver_timeout is None:
            solver_timeout = ExecutionConfiguration.SOLVER_TIMEOUT_SECONDS
        if m_margin_multiplier is None:
            m_margin_multiplier = ExecutionConfiguration.M_MARGIN_MULTIPLIER
        
        self.solver_timeout = solver_timeout
        self.m_margin_multiplier = m_margin_multiplier

        self.df = ElectricityMarketCurvesDataframe(path)
        self.solved_df = None
        self.model = self.get_model()
        self.solver = po.SolverFactory('gurobi')
        self.solver.options['timelimit'] = self.solver_timeout
        self.results_info = {}

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
        # PPA_PRICE from constants

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

        if self.ppa:
            # PPA variable
            model.ppa_percentage = pe.Var(within=pe.NonNegativeReals)

        # --- Objective function (Strategic: maximize own generator revenue) ---
        def obj_rule(model):
            # No lineal version
            # obj = sum(sum((model.lambda_power_balance[t] - model.generator_marginal_cost[i, t]) * model.production[i, t] for i in model.own_generators) for t in model.hours)

            # Simplification given that the marginal cost is not a variable (keep in mind the generator_marginal_cost, as in the video the costs and the offer were different)
            # obj = sum(sum(model.generator_maximum_capacity[i, t] * model.omega_q_max[i, t] for i in model.own_generators) for t in model.hours)

            # Complete video linealization (keep in mind the generator_marginal_cost, as in the video the costs and the offer were different)
            obj = sum(- sum(model.generator_marginal_cost[j, t] * model.production[j, t] for j in model.generators) 
                    + sum(model.demand_marginal_utility[l, t] * model.consumption[l, t] for l in model.consumers) 
                    - sum(model.omega_d_max[l, t] * model.demand_maximum[l, t] for l in model.consumers) 
                    - sum(model.omega_q_max[j, t] * model.generator_maximum_capacity[j, t] for j in model.external_generators)
                    for t in model.hours)
            
            if self.ppa:
                obj += sum(sum((self.ppa_price - model.generator_marginal_cost[i, t])*model.ppa_percentage*model.generator_maximum_capacity[i, t]
                               for i in model.own_generators) 
                           for t in model.hours)
            
            return obj

        model.revenue = pe.Objective(rule = obj_rule, sense = pe.maximize)
        
        # --- Constraints ---
        def power_balance_rule(model, t):
            return sum(model.consumption[l, t] for l in model.consumers) - sum(model.production[j, t] for j in model.generators) == 0

        model.constraint_power_balance = pe.Constraint(model.hours, rule=power_balance_rule)

        def consumption_limit_rule(model, l, t):
            return model.demand_maximum[l, t] - model.consumption[l, t] >= 0

        model.constraint_consumption_limit = pe.Constraint(model.consumers, model.hours, rule=consumption_limit_rule)

        def production_limit_rule(model, j, t):
            if self.ppa and j in model.own_generators:
                return model.generator_maximum_capacity[j, t] * (1 - model.ppa_percentage) - model.production[j, t] >= 0
            else:
                return model.generator_maximum_capacity[j, t] - model.production[j, t] >= 0

        model.constraint_production_limit = pe.Constraint(model.generators, model.hours, rule=production_limit_rule)

        # *** Big-M linearized complementary slackness constraints ***
        # Get maximum possible market price from all offers (generators and consumers)
        max_market_price = self.df.df['offer'].max()
        # Generators: lower bound
        def bigm_q_min_dual_rule(model, j, t):
            m = max_market_price * self.m_margin_multiplier
            return model.omega_q_min[j, t] <= m * (1 - model.z_q_min[j, t])
        model.bigm_q_min_dual = pe.Constraint(model.generators, model.hours, rule=bigm_q_min_dual_rule)

        def bigm_q_min_primal_rule(model, j, t):
            m = model.generator_maximum_capacity[j, t] * self.m_margin_multiplier
            return model.production[j, t] <= m * model.z_q_min[j, t]
        model.bigm_q_min_primal = pe.Constraint(model.generators, model.hours, rule=bigm_q_min_primal_rule)

        # Generators: upper bound
        def bigm_q_max_dual_rule(model, j, t):
            m = max_market_price * self.m_margin_multiplier
            return model.omega_q_max[j, t] <= m * (1 - model.z_q_max[j, t])
        model.bigm_q_max_dual = pe.Constraint(model.generators, model.hours, rule=bigm_q_max_dual_rule)

        def bigm_q_max_primal_rule(model, j, t):
            m = model.generator_maximum_capacity[j, t] * self.m_margin_multiplier
            if self.ppa and j in model.own_generators:
                return model.generator_maximum_capacity[j, t] * (1 - model.ppa_percentage) - model.production[j, t] <= m * model.z_q_max[j, t]
            else:
                return model.generator_maximum_capacity[j, t] - model.production[j, t] <= m * model.z_q_max[j, t]
        model.bigm_q_max_primal = pe.Constraint(model.generators, model.hours, rule=bigm_q_max_primal_rule)

        # Demand: lower bound
        def bigm_d_min_dual_rule(model, l, t):
            m = max_market_price * self.m_margin_multiplier
            return model.omega_d_min[l, t] <= m * (1 - model.z_d_min[l, t])
        model.bigm_d_min_dual = pe.Constraint(model.consumers, model.hours, rule=bigm_d_min_dual_rule)

        def bigm_d_min_primal_rule(model, l, t):
            m = model.demand_maximum[l, t] * self.m_margin_multiplier
            return model.consumption[l, t] <= m * model.z_d_min[l, t]
        model.bigm_d_min_primal = pe.Constraint(model.consumers, model.hours, rule=bigm_d_min_primal_rule)

        # Demand: upper bound
        def bigm_d_max_dual_rule(model, l, t):
            m = max_market_price * self.m_margin_multiplier
            return model.omega_d_max[l, t] <= m * (1 - model.z_d_max[l, t])
        model.bigm_d_max_dual = pe.Constraint(model.consumers, model.hours, rule=bigm_d_max_dual_rule)

        def bigm_d_max_primal_rule(model, l, t):
            m = model.demand_maximum[l, t] * self.m_margin_multiplier
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

        if self.ppa:
            # PPA percentage upper bound
            def ppa_upper_bound_rule(model):
                return model.ppa_percentage <= 1
            model.ppa_upper_bound = pe.Constraint(rule=ppa_upper_bound_rule)

        num_constraints = len(list(model.component_data_objects(pe.Constraint, active=True)))
        num_variables = len(list(model.component_data_objects(pe.Var)))
        print(f"Number of constraints: {num_constraints}")
        print(f"Number of variables: {num_variables}")

        return model
    
    def _verify_solution(self, res):
        """
        Perform comprehensive numerical validation and verification of the solution.
        Returns a dictionary with verification results.
        """
        tolerance = 1e-6
        verification = {
            "complementarity_check": {},
            "kkt_conditions_check": {},
            "economic_reasonableness_check": {},
            "solver_optimality_check": {},
            "overall_valid": True
        }
        
        # ============ 1. COMPLEMENTARITY SATISFACTION CHECK ============
        z_q_min_violations = 0
        z_q_max_violations = 0
        z_d_min_violations = 0
        z_d_max_violations = 0
        
        for j in self.model.generators:
            for t in self.model.hours:
                # q_min complementarity: omega_q_min * production = 0
                omega_q_min_val = pe.value(self.model.omega_q_min[j, t])
                q_val = pe.value(self.model.production[j, t])
                # For lower bound: if production > 0, omega should be 0; if omega > 0, production should be 0
                if q_val > tolerance and omega_q_min_val > tolerance:
                    z_q_min_violations += 1
                
                # q_max complementarity: omega_q_max * (capacity - production) = 0
                omega_q_max_val = pe.value(self.model.omega_q_max[j, t])
                q_limit = pe.value(self.model.generator_maximum_capacity[j, t])
                # Apply PPA percentage adjustment for own generators if PPA is enabled
                if self.ppa and j in self.model.own_generators:
                    ppa_pct = pe.value(self.model.ppa_percentage)
                    q_limit = q_limit * (1 - ppa_pct)
                slack_val = q_limit - q_val  # slack = limit - production (without abs)
                # For upper bound: if slack > 0 (not at limit), omega should be 0; if omega > 0, slack should be 0
                if slack_val > tolerance and omega_q_max_val > tolerance:
                    z_q_max_violations += 1
        
        for l in self.model.consumers:
            for t in self.model.hours:
                # d_min complementarity: omega_d_min * consumption = 0
                omega_d_min_val = pe.value(self.model.omega_d_min[l, t])
                d_val = pe.value(self.model.consumption[l, t])
                # For lower bound: if consumption > 0, omega should be 0; if omega > 0, consumption should be 0
                if d_val > tolerance and omega_d_min_val > tolerance:
                    z_d_min_violations += 1
                
                # d_max complementarity: omega_d_max * (demand_max - consumption) = 0
                omega_d_max_val = pe.value(self.model.omega_d_max[l, t])
                d_limit = pe.value(self.model.demand_maximum[l, t])
                slack_val = d_limit - d_val  # slack = limit - consumption (without abs)
                # For upper bound: if slack > 0 (not at limit), omega should be 0; if omega > 0, slack should be 0
                if slack_val > tolerance and omega_d_max_val > tolerance:
                    z_d_max_violations += 1
        
        total_binary_vars = (len(self.model.generators) * len(self.model.hours) * 2 +
                            len(self.model.consumers) * len(self.model.hours) * 2)
        total_violations = z_q_min_violations + z_q_max_violations + z_d_min_violations + z_d_max_violations
        
        verification["complementarity_check"] = {
            "z_q_min_violations": int(z_q_min_violations),
            "z_q_max_violations": int(z_q_max_violations),
            "z_d_min_violations": int(z_d_min_violations),
            "z_d_max_violations": int(z_d_max_violations),
            "total_violations": int(total_violations),
            "total_binary_variables": int(total_binary_vars),
            "violation_percentage": float(100 * total_violations / total_binary_vars if total_binary_vars > 0 else 0),
            "passed": total_violations == 0
        }
        
        # ============ 2. KKT CONDITIONS CHECK ============
        # 2a. Primal Feasibility: Power Balance
        power_balance_violations = 0
        for t in self.model.hours:
            production_sum = sum(pe.value(self.model.production[j, t]) for j in self.model.generators)
            consumption_sum = sum(pe.value(self.model.consumption[l, t]) for l in self.model.consumers)
            if abs(production_sum - consumption_sum) > tolerance:
                power_balance_violations += 1
        
        # 2b. Dual Feasibility: All omega variables should be >= 0 (already enforced by constraints)
        dual_feasibility_passed = True
        for j in self.model.generators:
            for t in self.model.hours:
                if pe.value(self.model.omega_q_min[j, t]) < -tolerance or pe.value(self.model.omega_q_max[j, t]) < -tolerance:
                    dual_feasibility_passed = False
        
        for l in self.model.consumers:
            for t in self.model.hours:
                if pe.value(self.model.omega_d_min[l, t]) < -tolerance or pe.value(self.model.omega_d_max[l, t]) < -tolerance:
                    dual_feasibility_passed = False
        
        # 2c. Stationarity: Check stationarity constraints satisfaction
        stationarity_violations = 0
        for j in self.model.generators:
            for t in self.model.hours:
                stationary_val = (pe.value(self.model.generator_marginal_cost[j, t])
                                - pe.value(self.model.lambda_power_balance[t])
                                - pe.value(self.model.omega_q_min[j, t])
                                + pe.value(self.model.omega_q_max[j, t]))
                if abs(stationary_val) > tolerance:
                    stationarity_violations += 1
        
        for l in self.model.consumers:
            for t in self.model.hours:
                stationary_val = (-pe.value(self.model.demand_marginal_utility[l, t])
                                + pe.value(self.model.lambda_power_balance[t])
                                - pe.value(self.model.omega_d_min[l, t])
                                + pe.value(self.model.omega_d_max[l, t]))
                if abs(stationary_val) > tolerance:
                    stationarity_violations += 1
        
        verification["kkt_conditions_check"] = {
            "power_balance_violations": int(power_balance_violations),
            "power_balance_passed": power_balance_violations == 0,
            "dual_feasibility_passed": dual_feasibility_passed,
            "stationarity_violations": int(stationarity_violations),
            "stationarity_passed": stationarity_violations == 0,
            "overall_kkt_passed": (power_balance_violations == 0 and 
                                  dual_feasibility_passed and 
                                  stationarity_violations == 0)
        }
        
        # ============ 3. ECONOMIC REASONABLENESS CHECK ============
        # Get all prices
        prices = [pe.value(self.model.lambda_power_balance[t]) for t in self.model.hours]
        min_price = min(prices)
        max_price = max(prices)
        
        # Per-hour price bounds check
        # For each hour, check if the price is within the offer bounds of that specific hour
        price_bound_violations = 0
        hours_with_violations = []
        
        for t in self.model.hours:
            price_t = pe.value(self.model.lambda_power_balance[t])
            
            # Get offer bounds for this hour specifically
            # (considering all generators and consumers that have non-zero capacity in this hour)
            offers_this_hour = []
            
            # Collect all generator marginal costs for this hour
            for j in self.model.generators:
                cost_jt = pe.value(self.model.generator_marginal_cost[j, t])
                if cost_jt < 1_000_000:  # Exclude default high values
                    offers_this_hour.append(cost_jt)
            
            # Collect all consumer marginal utilities for this hour
            for l in self.model.consumers:
                util_lt = pe.value(self.model.demand_marginal_utility[l, t])
                offers_this_hour.append(util_lt)
            
            if offers_this_hour:
                min_offer_t = min(offers_this_hour)
                max_offer_t = max(offers_this_hour)
                
                # Check if price is within bounds for this hour (with tolerance)
                if price_t < min_offer_t - tolerance or price_t > max_offer_t + tolerance:
                    price_bound_violations += 1
                    hours_with_violations.append({
                        "hour": t,
                        "price": price_t,
                        "min_bound": min_offer_t,
                        "max_bound": max_offer_t
                    })
        
        # Check production monotonicity (production should generally increase with price within reasonable bounds)
        # For each generator, check if production correlates with prices
        monotonicity_checks = 0
        monotonicity_passed = 0
        
        for j in self.model.generators:
            generator_productions = [pe.value(self.model.production[j, t]) for t in self.model.hours]
            # Only check if there's variance in production
            if np.std(generator_productions) > tolerance:
                monotonicity_checks += 1
                # Simple check: correlation should be positive for generators
                if np.corrcoef(prices, generator_productions)[0, 1] > -0.1:
                    monotonicity_passed += 1
        
        verification["economic_reasonableness_check"] = {
            "min_price": float(min_price),
            "max_price": float(max_price),
            "price_range_span": float(max_price - min_price),
            "per_hour_bound_violations": int(price_bound_violations),
            "hours_with_violations": hours_with_violations,
            "prices_within_bounds": price_bound_violations == 0,
            "monotonicity_checks_performed": int(monotonicity_checks),
            "monotonicity_checks_passed": int(monotonicity_passed),
            "overall_economic_reasonableness": bool(price_bound_violations == 0)
        }
        
        # ============ 4. SOLVER OPTIMALITY CHECK ============
        # Extract optimality gap from solver results
        optimality_gap_percent = None
        optimality_gap_passed = False
        termination = res.solver.termination_condition
        
        # Check termination condition first (most reliable)
        if termination == po.TerminationCondition.optimal:
            # Optimal solution achieved - gap is 0%
            optimality_gap_percent = 0.0
            optimality_gap_passed = True
        elif termination == po.TerminationCondition.maxTimeLimit or termination == po.TerminationCondition.feasible:
            # Timed out or only feasible solution found - try to extract gap from solver
            try:
                # For Gurobi, try to get the gap from results if available
                if hasattr(res, 'solution') and len(res.solution) > 0:
                    solution = res.solution[0]
                    if hasattr(solution, 'gap') and solution.gap is not None:
                        optimality_gap_percent = float(solution.gap) * 100
                    elif hasattr(solution, 'MIPGap') and solution.MIPGap is not None:
                        optimality_gap_percent = float(solution.MIPGap) * 100
                
                # Try alternative Gurobi-specific attributes
                if optimality_gap_percent is None and hasattr(res.solver, 'results'):
                    results = res.solver.results
                    if hasattr(results, 'mip_gap') and results.mip_gap is not None:
                        optimality_gap_percent = float(results.mip_gap) * 100
                
                # If we found a gap, check if it's below 1%
                if isinstance(optimality_gap_percent, float):
                    optimality_gap_passed = optimality_gap_percent < 1.0
                else:
                    # Couldn't extract gap - mark as unknown but may still be acceptable
                    optimality_gap_percent = "unknown"
                    optimality_gap_passed = False
            except:
                optimality_gap_percent = "unknown"
                optimality_gap_passed = False
        else:
            # Other termination conditions (infeasible, unbounded, etc.)
            optimality_gap_percent = "N/A"
            optimality_gap_passed = False
        
        verification["solver_optimality_check"] = {
            "termination_condition": str(termination),
            "solver_status": str(res.solver.status),
            "optimality_gap_percent": optimality_gap_percent,
            "gap_below_1_percent": bool(optimality_gap_passed) if isinstance(optimality_gap_passed, bool) else None,
            "optimality_achieved": str(termination) == str(po.TerminationCondition.optimal)
        }
        
        # ============ OVERALL VERDICT ============
        verification["overall_valid"] = (
            verification["complementarity_check"]["passed"] and
            verification["kkt_conditions_check"]["overall_kkt_passed"] and
            verification["economic_reasonableness_check"]["overall_economic_reasonableness"] and
            (optimality_gap_passed if isinstance(optimality_gap_passed, bool) else True)
        )
        
        return verification
    
    def solve(self):
        start_time = time.time()
        res = self.solver.solve(self.model, tee=True)
        end_time = time.time()

        # Check if we have a valid solution (either optimal or feasible if timed out)
        feasible_conditions = [
            po.TerminationCondition.optimal,
            po.TerminationCondition.maxTimeLimit,
            po.TerminationCondition.feasible
        ]

        if res.solver.termination_condition not in feasible_conditions:
            print(f"Warning: Model not solved (Termination Condition: {res.solver.termination_condition}). Result dataframe not set.")
            return
        
        ppa_percentage = pe.value(self.model.ppa_percentage) if self.ppa else 0.0
        profit = pe.value(self.model.revenue)
        execution_time = end_time - start_time
        
        print(f"PPA percentage: {ppa_percentage}")
        print(f"Strategic Profit: {profit}")
        print(f"Execution Time: {execution_time:.2f} s")

        # Run numerical validation and verification
        print("\n=== Running Numerical Validation and Verification ===")
        verification_results = self._verify_solution(res)
        
        self.results_info = {
            "ppa_percentage": ppa_percentage,
            "strategic_profit": profit,
            "execution_time_seconds": execution_time,
            "solver_status": str(res.solver.status),
            "solver_termination_condition": str(res.solver.termination_condition),
            "numerical_validation": verification_results
        }
        
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
        solved_df = ElectricityMarketSolvedDataframe(self.df, taken=taken, prices=market_price, ppa_percentage=ppa_percentage)
        self.solved_df = solved_df
    
    def save_dataframe(self, *args):
        if self.solved_df is None:
            print("Unable to save dataframe: Dataframe not set.")
            return
        self.solved_df.save_dataframe(*args)

    def save_results_info(self, path: str):
        if not self.results_info:
            print("Unable to save results info: Info not set.")
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump(self.results_info, f, indent=4)

    def save_market_plots(self, **kwargs):
        if self.solved_df is None:
            print("Unable to save market plots: Dataframe not set.")
            return
        self.solved_df.save_market_plots(**kwargs)
    
    def save_monotone_price_curve(self, output_dir):
        if self.df is None:
            print("Unable to save monotone price curve: Dataframe not set.")
            return
        self.solved_df.save_monotone_price_curve(output_dir)

def _check_bilevel_files_exist(solved_path: str, info_path: str) -> bool:
    """Check if the bilevel output files already exist."""
    return os.path.exists(solved_path) and os.path.exists(info_path)

def main(estimation_name: str, solar_percent: float = 0.0, ppa_price:float|int|None=None, battery:bool=False, update: bool = True):
    # Handle list-type solar_percent parameter (iterate over solar percentages)
    if isinstance(solar_percent, (list, tuple)):
        for solar in solar_percent:
            main(estimation_name=estimation_name, solar_percent=solar, ppa_price=ppa_price, battery=battery, update=update)
        return
    
    # Handle list-type ppa_price parameter (iterate over prices)
    if isinstance(ppa_price, (list, tuple)):
        for price in ppa_price:
            main(estimation_name=estimation_name, solar_percent=solar_percent, ppa_price=price, battery=battery, update=update)
        return
    
    percent_name = f"solar_{int(solar_percent*100)}"
    path = os.path.join(PathConfiguration.ESTIMATIONS_DIR_PATH, estimation_name, f"{percent_name}.csv")
    
    problem_type = f"bilevel{'_ppa' if ppa_price is not None else ''}{'_battery' if battery else ''}"
    ppa_suffix = f"ppa_{ppa_price}" if ppa_price is not None else ""
    
    # Hierarchical solved and images directories
    solved_dir = os.path.join(PathConfiguration.SOLVED_ESTIMATIONS_DIR_PATH, estimation_name, percent_name, problem_type, ppa_suffix)
    solved_path = os.path.join(solved_dir, "results.csv")
    info_path = os.path.join(solved_dir, "info.json")
    
    # Check if files already exist and update flag is False
    if not update and _check_bilevel_files_exist(solved_path, info_path):
        print(f"Skipping (already exists): solar={int(solar_percent*100)}% ppa={ppa_price} battery={battery}")
        return
    
    p = StrategicOfferingProblem(path, ppa_price=ppa_price, battery=battery)
    p.solve()

    os.makedirs(solved_dir, exist_ok=True)
    p.save_dataframe(solved_path)
    
    p.save_results_info(info_path)

if __name__ == "__main__":
    main()