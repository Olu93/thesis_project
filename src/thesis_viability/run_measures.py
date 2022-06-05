import os

import numpy as np
import pandas as pd
import tensorflow as tf
from thesis_commons.config import DEBUG_USE_MOCK

import thesis_commons.metric as metric
from thesis_commons.constants import PATH_MODELS_PREDICTORS
from thesis_commons.functions import get_all_data, stack_data
from thesis_commons.libcuts import K, layers, losses
from thesis_commons.modes import (DatasetModes, FeatureModes, GeneratorModes,
                                  TaskModes)
from thesis_commons.representations import Cases
from thesis_generators.helper.wrapper import GenerativeDataset
from thesis_viability.datallh.datallh_measure import DatalikelihoodMeasure
from thesis_viability.outcomellh.outcomllh_measure import \
    OutcomeImprovementMeasureDiffs as OutcomelikelihoodMeasure
from thesis_viability.similarity.similarity_measure import SimilarityMeasure
from thesis_viability.sparcity.sparcity_measure import SparcityMeasure
from thesis_predictors.models.lstms.lstm import OutcomeLSTM


if DEBUG_USE_MOCK:
    from thesis_readers import OutcomeMockReader as Reader
else:
    from thesis_readers import OutcomeBPIC12Reader as Reader

DEBUG_SPARCITY = True
DEBUG_SIMILARITY = True
DEBUG_DLLH = True
DEBUG_OLLH = True

if __name__ == "__main__":
    task_mode = TaskModes.OUTCOME_PREDEFINED
    ft_mode = FeatureModes.FULL

    epochs = 50
    reader = Reader(mode=task_mode).init_meta()
    vocab_len = reader.vocab_len
    max_len = reader.max_len
    # TODO: Implement cleaner version. Could use from_config instead of init_metrics as both are static methods
    custom_objects_predictor = {obj.name: obj for obj in OutcomeLSTM.init_metrics()}

    # generative_reader = GenerativeDataset(reader)
    tr_cases, cf_cases, fa_cases = get_all_data(reader, ft_mode=ft_mode, fa_num=5, fa_filter_lbl=1)

    
    if DEBUG_SPARCITY:
        print("Run Sparcity")
        sparcity_computer = SparcityMeasure(vocab_len, max_len)
        sparcity_values = sparcity_computer.compute_valuation(fa_cases, cf_cases).normalize()
        print(sparcity_values)
    
    if DEBUG_SIMILARITY:
        print("Run Similarity")
        similarity_computer = SimilarityMeasure(vocab_len, max_len)
        similarity_values = similarity_computer.compute_valuation(fa_cases, cf_cases).normalize()
        print(similarity_values)
    
    if DEBUG_DLLH:
        print("Run Data Likelihood")
        feasibility_computer = DatalikelihoodMeasure(vocab_len, max_len, training_data=tr_cases)
        feasibility_values = feasibility_computer.compute_valuation(fa_cases, cf_cases).normalize()
        print(feasibility_values)
    
    if DEBUG_OLLH:
        print("Run Outcome Likelihood")
        all_models = os.listdir(PATH_MODELS_PREDICTORS)
        prediction_model = tf.keras.models.load_model(PATH_MODELS_PREDICTORS / all_models[-1], custom_objects=custom_objects_predictor)
        improvement_computer = OutcomelikelihoodMeasure(vocab_len, max_len, prediction_model=prediction_model)
        improvement_values = improvement_computer.compute_valuation(fa_cases, cf_cases).normalize()
        print(improvement_values)
    print("DONE")