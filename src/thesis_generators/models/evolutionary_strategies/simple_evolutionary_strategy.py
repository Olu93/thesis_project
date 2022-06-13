import os

import numpy as np
import tensorflow as tf

from thesis_commons import random
from thesis_commons.constants import PATH_MODELS_PREDICTORS
from thesis_commons.functions import extract_padding_mask
from thesis_commons.modes import (DatasetModes, FeatureModes, MutationMode, TaskModes)
from thesis_commons.representations import Cases, MutatedCases
from thesis_generators.models.encdec_vae.vae_seq2seq import \
    SimpleGeneratorModel as Generator
from thesis_generators.models.evolutionary_strategies.base_evolutionary_strategy import \
    EvolutionaryStrategy
from thesis_predictors.models.lstms.lstm import OutcomeLSTM
from thesis_readers import OutcomeMockReader as Reader
from thesis_viability.viability.viability_function import ViabilityMeasure

DEBUG = True

# Tricks
# https://cs.stackexchange.com/a/54835


# TODO: Test if cf change is meaningful by test if likelihood flipped decision
class SimpleEvolutionStrategy(EvolutionaryStrategy):
    def __init__(self, max_iter, evaluator: ViabilityMeasure, **kwargs) -> None:
        super().__init__(max_iter=max_iter, evaluator=evaluator, **kwargs)

    def selection(self, cf_population: MutatedCases, fa_seed: MutatedCases, **kwargs) -> MutatedCases:
        evs, fts, llhs, fitness = cf_population.all
        viabs = fitness.viabs.flatten()
        normalized_viabs = viabs / viabs.sum()
        selection = random.choice(np.arange(len(cf_population)), size=100, p=normalized_viabs)
        cf_selection = cf_population[selection]
        return cf_selection

    def crossover(self, cf_parents: MutatedCases, fa_seed: MutatedCases, **kwargs) -> MutatedCases:
        cf_ev, cf_ft = cf_parents.cases
        total = self.num_population
        # Parent can mate with itself, as that would preserve some parents
        # TODO: Check this out http://www.scholarpedia.org/article/Evolution_strategies
        mother_ids, father_ids = random.integers(0, len(cf_ev), (2, total))
        mother_events, father_events = cf_ev[mother_ids], cf_ev[father_ids]
        mother_features, father_features = cf_ft[mother_ids], cf_ft[father_ids]
        mask = extract_padding_mask(mother_events)
        gene_flips = random.random((total, mother_events.shape[1])) > self.recombination_rate
        gene_flips = gene_flips & mask
        child_events = mother_events.copy()
        child_events[gene_flips] = father_events[gene_flips]
        child_features = mother_features.copy()
        child_features[gene_flips] = father_features[gene_flips]

        return MutatedCases(child_events, child_features)

    def init_population(self, fa_seed: MutatedCases, **kwargs):
        fc_ev, fc_ft = fa_seed.cases
        random_events = random.integers(0, self.vocab_len, (self.num_population, ) + fc_ev.shape[1:]).astype(float)
        random_features = random.standard_normal((self.num_population, ) + fc_ft.shape[1:])
        return MutatedCases(random_events, random_features).evaluate_fitness(self.fitness_function, fa_seed)

    def mutation(self, cf_offspring: MutatedCases, fa_seed: MutatedCases, *args, **kwargs):
        events, features = cf_offspring.cases
        # This corresponds to one Mutation per Case
        m_type = random.choice(MutationMode, size=(events.shape[0], 1), p=self.mutation_rate.probs)
        positions = np.argsort(random.random(events.shape), axis=1)
        m_position = positions <= int(events.shape[1] * self.edit_rate)

        delete_mask = (m_type == MutationMode.DELETE) & (events != 0) & (positions < 1)
        change_mask = (m_type == MutationMode.CHANGE) & (events != 0) & (m_position)
        insert_mask = (m_type == MutationMode.INSERT) & (events == 0) & (m_position)
        swap_mask = (m_type == MutationMode.SWAP) & (m_position)
        # This is a version for multiple swaps
        # swap_mask = (m_type == MUTATION.SWAP) & (rand.random([events.shape[0]]) > 0.1)

        orig_ev = events.copy()
        orig_ft = features.copy()

        # DELETE
        # delete_position = rand.randint(0, self.max_len, len(events[delete_mask]))
        events[delete_mask] = 0
        features[delete_mask] = 0
        # CHANGE
        events[change_mask] = random.integers(1, self.vocab_len, events.shape)[change_mask]
        features[change_mask] = random.standard_normal(features.shape)[change_mask]
        # INSERT
        events[insert_mask] = random.integers(1, self.vocab_len, events.shape)[insert_mask]
        features[insert_mask] = random.standard_normal(features.shape)[insert_mask]
        # SWAP

        source_container = np.roll(events, -1, axis=1)
        tmp_container = np.ones_like(events) * np.nan
        tmp_container[swap_mask] = events[swap_mask]
        tmp_container = np.roll(tmp_container, 1, axis=1)
        backswap_mask = ~np.isnan(tmp_container)

        events[swap_mask] = source_container[swap_mask]
        events[backswap_mask] = tmp_container[backswap_mask]

        source_container = np.roll(features, -1, axis=1)
        tmp_container = np.ones_like(features) * np.nan
        tmp_container[swap_mask] = features[swap_mask]
        tmp_container = np.roll(tmp_container, 1, axis=1)

        features[swap_mask] = source_container[swap_mask]
        features[backswap_mask] = tmp_container[backswap_mask]

        mutations = m_type
        return MutatedCases(events, features).set_mutations(mutations).evaluate_fitness(self.fitness_function, fa_seed)


    # def generate(self, fa_cases: Cases) -> GeneratorResult:
    #     fa_events, fa_features = fa_cases.items()
    #     return self([fa_events, fa_features], fa_labels)


DEBUG = True
if __name__ == "__main__":
    task_mode = TaskModes.OUTCOME_PREDEFINED
    epochs = 1000
    reader = Reader(mode=task_mode).init_meta(skip_dynamics=True)
    custom_objects_predictor = {obj.name: obj for obj in OutcomeLSTM.init_metrics()}
    custom_objects_generator = {obj.name: obj for obj in Generator.init_metrics()}

    # generative_reader = GenerativeDataset(reader)
    (tr_events, tr_features), _ = reader._generate_dataset(data_mode=DatasetModes.TRAIN, ft_mode=FeatureModes.FULL)
    (fa_events, fa_features), fa_labels = reader._generate_dataset(data_mode=DatasetModes.TEST, ft_mode=FeatureModes.FULL)
    take = 2
    factual_cases = Cases(fa_events[:take], fa_features[:take], fa_labels[:take, 0])

    all_models_predictors = os.listdir(PATH_MODELS_PREDICTORS)
    predictor = tf.keras.models.load_model(PATH_MODELS_PREDICTORS / all_models_predictors[-1], custom_objects=custom_objects_predictor)
    print("PREDICTOR")
    predictor.summary()

    viability = ViabilityMeasure(reader.vocab_len, reader.max_len, (tr_events, tr_features), predictor)

    generator = SimpleEvolutionStrategy(
        evaluator=viability,
        vocab_len=reader.vocab_len,
        max_len=reader.max_len,
        feature_len=reader.num_event_attributes,
        max_iter=epochs,
    )

    results = generator(factual_cases, 5)
    print("DONE")
    print(generator.stats)
    generator.stats.to_csv('tmp.csv', index=False, line_terminator='\n')
