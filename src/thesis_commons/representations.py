from __future__ import annotations
from typing import Dict, Tuple
from numpy.typing import NDArray
import numpy as np

# TODO: Rename data property to cases
# TODO: Use all property to get all of the important parts
# TODO: Change outcomes setter to set_outcome which returns itself
# TODO: Rename outcomes to likelihoods
# TODO: Introduce static CaseBuilder class which builds all case types
# TODO: Move ResultStatistics from model_commons to this representations
# TODO: Reduce prominence of Population subclass
# TODO: Merge GeneratedResult with EvaluatedCases


class Cases():
    def __init__(self, events: NDArray, features: NDArray, outcomes: NDArray = None):
        self._events = events
        self._features = features
        self._outcomes = outcomes
        self._len = len(self._events)
        self.num_cases, self.max_len, self.num_features = features.shape
        self._viabilities = None

    def tie_all_together(self) -> Cases:
        return self

    def sort(self) -> Cases:
        ev, ft = self.data
        viability = self.viabilities
        ranking = np.argsort(viability)
        sorted_ev, sorted_ft = ev[ranking], ft[ranking]
        sorted_viability = viability[ranking]
        return Cases(sorted_ev, sorted_ft).set_viability(sorted_viability)

    def sample(self, sample_size: int) -> Cases:
        chosen = self._get_random_selection(sample_size)
        ev, ft = self.data
        outcomes = self.outcomes
        return Cases(ev[chosen], ft[chosen], outcomes[chosen])

    def set_viability(self, viabilities: NDArray) -> Cases:
        if not (len(self.events) == len(viabilities)):
            ValueError(f"Number of fitness_vals needs to be the same as number of population: {len(self)} != {len(viabilities)}")
        self._viabilities = viabilities
        return self

    def get_topk(self, k: int):
        return

    def __iter__(self) -> Cases:
        events, features, outcomes = self.events, self.features, self.outcomes
        for i in range(len(self)):
            yield Cases(events[i:i + 1], features[i:i + 1], outcomes[i:i + 1])
        # raise StopIteration

    def __len__(self):
        return self._len

    def _get_random_selection(self, sample_size: int):
        num_cases = len(self)
        chosen = np.random.choice(np.arange(num_cases), size=sample_size, replace=False)
        return chosen

    def assert_viability_is_set(self, raise_error=False):

        if raise_error and (self._viabilities is None):
            raise ValueError(f"Viability values where never set: {self._viabilities}")

        return self._viabilities is not None

    @property
    def avg_viability(self) -> NDArray:
        self.assert_viability_is_set(raise_error=True)
        return self._viabilities.mean()

    @property
    def max_viability(self) -> NDArray:
        self.assert_viability_is_set(raise_error=True)
        return self._viabilities.max()

    @property
    def median_viability(self) -> NDArray:
        self.assert_viability_is_set(raise_error=True)
        return np.median(self._viabilities)



    @property
    def data(self) -> Tuple[NDArray, NDArray]:
        return self._events.copy(), self._features.copy()

    @property
    def all(self) -> Tuple[NDArray, NDArray, NDArray, NDArray]:
        result = (
            self.events,
            self.features,
            self.outcomes,
            self.viabilities,
        )
        return result

    @property
    def events(self):
        return self._events.copy() if self._events is not None else None

    @property
    def features(self):
        return self._features.copy() if self._features is not None else None

    @property
    def outcomes(self):
        return self._outcomes.copy() if self._outcomes is not None else None

    @property
    def viabilities(self) -> NDArray:
        return self._viabilities.copy() if self._viabilities is not None else None

    @outcomes.setter
    def outcomes(self, outcomes):
        self._outcomes = outcomes

    @property
    def size(self):
        return self._len


class EvaluatedCases(Cases):
    def __init__(self, events: NDArray, features: NDArray, outcomes: NDArray = None, viabilities: NDArray = None):
        super().__init__(events, features, outcomes)
        self._viabilities = viabilities

    def sample(self, sample_size: int) -> EvaluatedCases:
        chosen = super()._get_random_selection(sample_size)
        ev, ft = self.data
        viabilities = self.viabilities
        outcomes = self.outcomes
        return EvaluatedCases(ev[chosen], ft[chosen], outcomes[chosen], viabilities[chosen])


class Population(EvaluatedCases):
    def __init__(self, events: NDArray, features: NDArray, outcomes: NDArray = None, viabilities: NDArray = None):
        super(Population, self).__init__(events, features, outcomes, viabilities)
        self._survivor = None
        self._mutation = None

    def tie_all_together(self):
        return self

    def set_mutations(self, mutations: NDArray):
        if len(self.events) != len(mutations): f"Number of mutations needs to be the same as number of population: {len(self)} != {len(mutations)}"
        self._mutation = mutations
        return self

    def set_fitness_values(self, fitness_values: NDArray):
        self.set_viability(fitness_values)
        return self

    @staticmethod
    def from_cases(obj: Cases):
        return Population(obj.events, obj.features, obj.outcomes)

    @property
    def avg_fitness(self) -> NDArray:
        return self.avg_viability

    @property
    def max_fitness(self) -> NDArray:
        return self.max_viability

    @property
    def median_fitness(self) -> NDArray:
        return self.median_viability

    @property
    def fitness_values(self) -> NDArray:
        return self.viabilities.T[0]

    @property
    def mutations(self):
        if self._mutation is None: raise ValueError(f"Mutation values where never set: {self._mutation}")
        return self._mutation.copy()


class GeneratorResult(Cases):
    def __init__(self, events: NDArray, features: NDArray, outcomes: NDArray, viabilities: NDArray):
        super().__init__(events, features, outcomes)
        self.set_viability(viabilities)
        self.instance_num: int = None

    @classmethod
    def from_cases(cls, population: Cases):
        events, features = population.data
        result = cls(events.astype(float), features, population.outcomes, population.viabilities)
        return result

    def get_topk(self, top_k: int = 5):
        ev, ft = self.data
        viab = self.viabilities
        outc = self.outcomes

        ranking = np.argsort(viab, axis=0)
        topk_indices = ranking[-top_k:].flatten()

        ev_chosen, ft_chosen, outc_chosen, viab_chosen = ev[topk_indices], ft[topk_indices], outc[topk_indices], viab[topk_indices]
        return GeneratorResult(ev_chosen, ft_chosen, outc_chosen, viab_chosen)

    def set_instance_num(self, num: int) -> GeneratorResult:
        self.instance_num = num
        return self

    def set_creator(self, creator: str) -> GeneratorResult:
        self.creator = creator
        return self

    def to_dict_stream(self):
        for i in range(len(self)):
            yield {
                "creator": self.creator,
                "instance_num": self.instance_num,
                "events": self._events[i],
                "features": self._features[i],
                "likelihood": self._outcomes[i][0],
                "outcome": ((self._outcomes[i] > 0.5) * 1)[0],
                "viability": self._viabilities[i][0]
            }
