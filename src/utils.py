import matplotlib.pyplot as plt

# def combine_dicts(keys, *dicts):
#     return {k: [d.get(k, None) for d in dicts if d.get(k, None) is not None] for k in keys}

def create_data_list(color, keys, *dicts):
    return [[color, *[d[k] for d in dicts]] for k in keys]

def draw_clearing_market(demands, own_generators, external_generators, consumption_limit: dict[str, int|float], own_production_limit: dict[str, int|float], external_production_limit: dict[str, int|float], demands_bid: dict[str, int|float], own_generators_offer: dict[str, int|float], external_generators_offer: dict[str, int|float], market_price: float, suplied_demand: float):
    demands_info = create_data_list("blue", demands, consumption_limit, demands_bid)
    own_generators_info = create_data_list("green", own_generators, own_production_limit, own_generators_offer)
    external_generators_info = create_data_list("red", external_generators, external_production_limit, external_generators_offer)

    demands_info.sort(key=lambda x: x[-1], reverse=True)
    generators_info = own_generators_info + external_generators_info
    generators_info.sort(key=lambda x: x[-1])
    
    plt.clf()

    x1 = 0
    last_bid = None
    for color, limit, bid in demands_info:
        if last_bid is not None:
            plt.plot([x1, x1], [last_bid, bid], color=color)
        plt.plot([x1, x1+limit], [bid, bid], color=color)
        x1 += limit
        last_bid = bid
    
    x2 = 0
    last_offer = None
    for color, limit, offer in generators_info:
        if last_offer is not None:
            plt.plot([x2, x2], [last_offer, offer], color=color)
        plt.plot([x2, x2+limit], [offer, offer], color=color)
        x2 += limit
        last_offer = offer
    
    plt.plot([0, suplied_demand], [market_price, market_price], color="orange", linestyle="dashed")
    plt.plot([suplied_demand, suplied_demand], [market_price, 0], color="orange", linestyle="dashed")
    plt.axis((0, max(x1, x2), 0, 1.1*max(demands_info[0][2], generators_info[-1][2])))
    plt.savefig("market.png")

def test_drawing():
    demands = ['d1', 'd2']
    own_generators = ['og1', 'og2']
    external_generators = ['eg1', 'eg2']

    consumption_limit = {
        'd1': 100,
        'd2': 50
    }
    own_production_limit = {
        'og1': 100,
        'og2': 50
    }
    external_production_limit = {
        'eg1': 100,
        'eg2': 50
    }
    demands_bid = {
        'd1': 40,
        'd2': 42
    }
    own_generators_offer = {
        'og1': 3.0,
        'og2': 5.0
    }
    external_generators_offer = {
        'eg1': 11,
        'eg2': 13
    }
    draw_clearing_market(demands, own_generators, external_generators, consumption_limit, own_production_limit, external_production_limit, demands_bid, own_generators_offer, external_generators_offer, 10, 150)

if __name__ == "__main__":
    test_drawing()