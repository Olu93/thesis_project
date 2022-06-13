from __future__ import annotations
from abc import ABC, abstractmethod
import io
from tokenize import Number
from typing import Any, Counter, Dict, List, Sequence, Tuple, Union

import numpy as np
import pandas as pd
from tqdm import tqdm
from thesis_commons.constants import PATH_RESULTS_MODELS_SPECIFIC

from thesis_commons.model_commons import BaseModelMixin
from thesis_commons.modes import MutationMode
from thesis_commons.representations import Cases, MutatedCases, MutationRate
from thesis_commons.statististics import InstanceData, IterationData, RowData
from thesis_viability.viability.viability_function import ViabilityMeasure

DEBUG_STOP = 1000




# class IterationStatistics():
#     def __init__(self) -> None:
#         self.base_store = {}
#         self.complex_store = {}
#         self._digested_data = None
#         self._combined_data = None

#     # num_generation, num_population, num_survivors, fitness_values
#     def update_base(self, stat_name: str, val: Number):
#         self.base_store[stat_name] = val

#     def update_mutations(self, stat_name: str, mutations: Union[List[MutationMode], List[Sequence[MutationMode]]]):
#         cnt = Counter((tuple(row) for row in mutations))
#         self.complex_store[stat_name] = cnt

#     def __repr__(self):
#         dict_copy = dict(self.base_store)
#         return f"@IterationStats[{repr(dict_copy)}]"
    
#     def _digest(self) -> IterationStatistics:
#         self._combined_data = [{**self.base_store, **{stat_name : self.complex_store[stat_name] for stat_name in self.complex_store}}]
#         return self
        
#     @property
#     def data(self) -> pd.DataFrame:
#         self._digest()
#         return self._combined_data










# TODO: Rename num_population to sample size
# TODO: Actually remove num_population and put it to predict
class EvolutionaryStrategy(BaseModelMixin, ABC):
    def __init__(self,
                 evaluator: ViabilityMeasure,
                 max_iter: int = 1000,
                 survival_thresh: int = 25,
                 num_population: int = 100,
                 edit_rate: float = 0.1,
                 recombination_rate: float = 0.5,
                 mutation_rate: MutationRate = MutationRate(),
                 **kwargs) -> None:
        super(EvolutionaryStrategy, self).__init__(**kwargs)
        self.fitness_function = evaluator
        self.mutation_rate = mutation_rate
        self.edit_rate = edit_rate
        self.recombination_rate = recombination_rate
        self.max_iter: int = max_iter
        self.name: str = self.__class__.__name__
        self.num_survivors: int = survival_thresh
        self.num_population: int = num_population
        self.num_cycle: int = 0
        self._iteration_statistics: IterationData = None
        self._curr_stats: RowData = None
        self.cycle_pbar: tqdm = None
        self.is_saved : bool = False
        # self._stats: Sequence[IterationStatistics] = []

    def predict(self, fa_case: Cases, **kwargs) -> Tuple[MutatedCases, IterationData]:
        fa_seed = Cases(*fa_case.all)
        self._iteration_statistics = IterationData()
        cf_parents: MutatedCases = self.init_population(fa_seed)
        self.num_cycle = 0
        self.cycle_pbar = tqdm(total=self.max_iter, desc="Evo Cycle")
        
        self._curr_stats = RowData()
        cf_survivors = self.run_iteration(self.num_cycle, fa_seed, cf_parents)
        self.wrapup_cycle()

        while not self.is_cycle_end(cf_survivors, self.num_cycle, fa_seed):
            self._curr_stats = RowData()
            cf_survivors = self.run_iteration(self.num_cycle, fa_seed, cf_parents)
            self.wrapup_cycle(**kwargs)
            cf_parents = cf_survivors

        # self.statistics
        final_population = cf_parents
        final_fitness = self.set_population_fitness(final_population, fa_seed)
        # for
        # self.is_saved:bool = self.save_statistics()
        # if self.is_saved:
        #     print("Successfully saved stats!")
        return final_fitness, self._iteration_statistics

    def run_iteration(self, cycle_num: int, fa_seed: Cases, cf_population: MutatedCases):
        self._curr_stats.attach("num_cycle", cycle_num)

        cf_selection = self.selection(cf_population, fa_seed)
        cf_offspring = self.crossover(cf_selection, fa_seed) 
        cf_mutated = self.mutation(cf_offspring, fa_seed)
        cf_candidates = cf_mutated + cf_population
        cf_survivors = self.recombination(cf_candidates, fa_seed)
        
        self._curr_stats.attach("n_selection", cf_selection.size)
        self._curr_stats.attach("n_offspring", cf_offspring.size)
        self._curr_stats.attach("n_mutated", cf_mutated.size)
        self._curr_stats.attach("n_candidates", cf_candidates.size)
        self._curr_stats.attach("n_survivors", cf_survivors.size)

        self._curr_stats.attach('mutsum', cf_mutated, EvolutionaryStrategy.count_mutations)
        self._curr_stats.attach("avg_zeros", (cf_survivors.events == 0).mean(-1).mean(-1))
        self._curr_stats.attach("avg_survivors_fitness", cf_survivors.avg_viability[0])
        self._curr_stats.attach("median_survivors_fitness", cf_survivors.median_viability[0])
        self._curr_stats.attach("max_survivors_fitness", cf_survivors.max_viability[0])
        # self._iteration_statistics.update_mutations('mut_num_s', cf_survivors.mutations)

        return cf_survivors

    @abstractmethod
    def selection(self, cf_population:MutatedCases, fa_seed: MutatedCases, **kwargs) -> MutatedCases:
        pass

    @abstractmethod
    def crossover(self, cf_parents: MutatedCases, fa_seed: MutatedCases, **kwargs) -> MutatedCases:
        pass

    @abstractmethod
    def mutation(self, cf_offspring: MutatedCases, fa_seed: MutatedCases, *args, **kwargs) -> MutatedCases:
        pass
        
    def recombination(self, cf_offspring: MutatedCases, fa_seed:MutatedCases, **kwargs) -> MutatedCases:
        cf_ev, cf_ft, _, fitness = cf_offspring.all
        # mutations = cf_offspring.mutations
        ranking = np.argsort(fitness.viabs, axis=0)
        selector = ranking[-self.num_survivors:].flatten()
        selected_fitness = fitness[selector]
        selected_events = cf_ev[selector]
        selected_features = cf_ft[selector]
        # selected_mutations = mutations[selector]
        selected = MutatedCases(selected_events, selected_features, selected_fitness) #.set_mutations(selected_mutations)
        return selected

    # def _crossover(self, cf_parents: MutatedCases, fc_seed: MutatedCases, **kwargs):
    #     if cf_parents is None:
    #         offspring = self._init_population(fc_seed)
    #         mutated = self.mutation(offspring, fc_seed)
    #         return mutated

    #     return mutated

    @abstractmethod
    def init_population(self, fc_seed: MutatedCases, **kwargs) -> MutatedCases:
        pass

    def set_population_fitness(self, cf_offspring: MutatedCases, fc_seed: MutatedCases, **kwargs) -> MutatedCases:
        fitness = self.fitness_function(fc_seed, cf_offspring)
        return cf_offspring.set_viability(fitness)



    def wrapup_cycle(self, *args, **kwargs):
        self.num_cycle += 1
        self.cycle_pbar.update(1)
        self._iteration_statistics.append(self._curr_stats)

    def is_cycle_end(self, *args, **kwargs) -> bool:
        return self.num_cycle >= self.max_iter

    @property
    def stats(self):
        return self._iteration_statistics.data

    @staticmethod
    def count_mutations(cases:MutatedCases):
        x = cases.mutations.flatten()
        cnt = Counter(x)
        result = {mtype._name_: cnt.get(mtype, 0) for mtype in MutationMode}
        return result

    # @abstractmethod
    # def __call__(self, *args, **kwargs):
    #     pass