from dataclasses import dataclass, field


class InfeasibleRouteError(ValueError):
    pass


@dataclass(frozen=True)
class Stop:
    mile: float
    price: float
    ref: object = None


@dataclass
class Purchase:
    stop: Stop
    gallons: float
    cost: float


@dataclass
class FuelPlan:
    purchases: list[Purchase] = field(default_factory=list)

    @property
    def total_gallons(self):
        return sum(p.gallons for p in self.purchases)

    @property
    def total_cost(self):
        return sum(p.cost for p in self.purchases)


def plan_fuel_stops(stops, total_miles, max_range_miles, mpg) -> FuelPlan:
    eps = 1e-9
    capacity = max_range_miles / mpg

    stops = sorted((s for s in stops if 0 <= s.mile < total_miles), key=lambda s: s.mile)
    stops.append(Stop(total_miles, 0.0))

    if stops[0].mile > eps:
        raise InfeasibleRouteError("No station at the origin and the tank starts empty.")

    plan = FuelPlan()
    fuel = 0.0
    i = 0

    while i < len(stops) - 1:
        current = stops[i]

        reachable = [j for j in range(i + 1, len(stops)) if stops[j].mile - current.mile <= max_range_miles + eps]

        if not reachable:
            gap = stops[i + 1].mile - current.mile

            raise InfeasibleRouteError(f"Gap of {gap:.0f} miles after mile {current.mile:.0f}.")

        cheaper = next((j for j in reachable if stops[j].price < current.price), None)

        if cheaper is not None:
            target = cheaper
            buy = max(0.0, (stops[target].mile - current.mile) / mpg - fuel)
        else:
            target = min(reachable, key=lambda j: (stops[j].price, stops[j].mile))
            buy = capacity - fuel

        if buy > eps:
            plan.purchases.append(Purchase(current, buy, buy * current.price))
            fuel += buy

        fuel -= (stops[target].mile - current.mile) / mpg
        i = target

    return plan