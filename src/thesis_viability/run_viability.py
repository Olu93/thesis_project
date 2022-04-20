import io
import os
from typing import Any, Callable
import numpy as np
from thesis_commons.functions import stack_data
from thesis_viability.similarity.similarity_metric import SimilarityMeasure
from thesis_viability.sparcity.sparcity_metric import SparcityMeasure
from thesis_viability.feasibility.feasibility_metric import FeasibilityMeasure
from thesis_viability.likelihood.likelihood_improvement import ImprovmentMeasureOdds as ImprovementMeasure
from thesis_viability.helper.base_distances import odds_ratio as dist
from thesis_commons.constants import PATH_MODELS_PREDICTORS, PATH_MODELS_GENERATORS
from thesis_commons.libcuts import layers, K, losses
import thesis_commons.metric as metric
from thesis_readers import MockReader as Reader
from thesis_generators.helper.wrapper import GenerativeDataset
from thesis_commons.modes import DatasetModes, GeneratorModes, FeatureModes
from thesis_commons.modes import TaskModes
from thesis_generators.models.encdec_vae.joint_trainer import MultiTrainer as Generator
import tensorflow as tf
import pandas as pd
import glob

DEBUG = True


class ViabilityMeasure:
    
    def __init__(self, vocab_len, max_len, base_data, prediction_model) -> None:
        tr_events, tr_features = base_data
        self.sparcity_computer = SparcityMeasure(vocab_len, max_len)
        self.similarity_computer = SimilarityMeasure(vocab_len, max_len)
        self.feasibility_computer = FeasibilityMeasure(tr_events, tr_features)
        self.improvement_computer = ImprovementMeasure(prediction_model)

    def compute_valuation(self, fa_events, fa_features, cf_events, cf_features, is_multiplied=False):
        sparcity_values = self.sparcity_computer.compute_valuation(fa_events, fa_features, cf_events, cf_features)
        similarity_values = self.similarity_computer.compute_valuation(fa_events, fa_features, cf_events, cf_features)
        feasibility_values = self.feasibility_computer.compute_valuation(cf_events, cf_features)
        improvement_values = self.improvement_computer.compute_valuation(fa_events, fa_features, cf_events, cf_features)
        if not is_multiplied:
            result = sparcity_values + similarity_values + feasibility_values + improvement_values 
        else:
            result = sparcity_values * similarity_values * feasibility_values * improvement_values 
            
        return result
        

if __name__ == "__main__":
    task_mode = TaskModes.NEXT_EVENT_EXTENSIVE
    epochs = 50
    reader = Reader(mode=task_mode).init_meta()
    custom_objects_predictor = {obj.name: obj for obj in [metric.MSpCatCE(), metric.MSpCatAcc(), metric.MEditSimilarity()]}
    custom_objects_generator = {obj.name: obj for obj in Generator.get_loss_and_metrics()}
    
    # generative_reader = GenerativeDataset(reader)
    (tr_events, tr_features), _, _ = reader._generate_dataset(data_mode=DatasetModes.TRAIN, ft_mode=FeatureModes.FULL_SEP)
    (fa_events, fa_features), _, _ = reader._generate_dataset(data_mode=DatasetModes.TEST, ft_mode=FeatureModes.FULL_SEP)
    

    all_models_predictors = os.listdir(PATH_MODELS_PREDICTORS)
    predictor = tf.keras.models.load_model(PATH_MODELS_PREDICTORS / all_models_predictors[-1], custom_objects=custom_objects_predictor)
    all_models_generators = os.listdir(PATH_MODELS_GENERATORS)
    generator = tf.keras.models.load_model(PATH_MODELS_GENERATORS / all_models_generators[-1], custom_objects=custom_objects_generator)
    
    cf_events, cf_features, z_sample, z_mean, z_logvar = generator.generator([fa_events, fa_features])    
    
    viability = ViabilityMeasure(reader.vocab_len, reader.max_len, (tr_events, tr_features), predictor)
    
    viability_values = viability.compute_valuation(fa_events, fa_features, cf_events, cf_features)
    print(viability_values)
    print("DONE")