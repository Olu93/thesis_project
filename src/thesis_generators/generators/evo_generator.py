from typing import Sequence, Tuple
from thesis_generators.models.evolutionary_strategies.base_evolutionary_strategy import IterationStatistics
from thesis_commons.representations import Population
from thesis_commons.model_commons import BaseModelMixin
from thesis_generators.models.evolutionary_strategies.simple_evolutionary_strategy import SimpleEvolutionStrategy
from thesis_commons.representations import GeneratorResult
from thesis_commons.representations import Cases
from thesis_viability.viability.viability_function import ViabilityMeasure
from thesis_commons.model_commons import GeneratorMixin
import numpy as np


class SimpleEvoGenerator(GeneratorMixin):
    def __init__(self, generator: BaseModelMixin, evaluator: ViabilityMeasure, **kwargs) -> None:
        super().__init__(evaluator)
        self.generator: SimpleEvolutionStrategy = generator

    def execute_generation(self, fa_case: Cases) -> GeneratorResult:
        cf_population, stats = self.generator.predict(fa_case)
        return cf_population, stats

    def construct_result(self, generation_results: Tuple[Population, Sequence[IterationStatistics]], **kwargs) -> GeneratorResult:
        cf_population, stats = generation_results
        g_result = GeneratorResult.from_cases(cf_population)
        g_result.outcomes = self.predictor.predict(*cf_population.items())
        return g_result
