import io
from typing import Any, Callable
from unicodedata import is_normalized
import numpy as np
from thesis_commons.functions import stack_data
from thesis_viability.helper.custom_edit_distance import DamerauLevenshstein
import thesis_viability.helper.base_distances as distances
from thesis_readers import MockReader as Reader
from thesis_generators.helper.wrapper import GenerativeDataset
from thesis_commons.modes import DatasetModes, GeneratorModes, FeatureModes
from thesis_commons.modes import TaskModes
from scipy.spatial import distance
import tensorflow as tf
import pickle

class SparcityMetric:
    def __init__(self, vocab_len, max_len) -> None:
        self.dist = DamerauLevenshstein(vocab_len, max_len, distances.EuclidianDistance())
        
    def compute_valuation(self, a_stacked, b_stacked):
        return self.dist(a_stacked, b_stacked)

if __name__ == "__main__":
    task_mode = TaskModes.NEXT_EVENT_EXTENSIVE
    epochs = 50
    reader = None
    reader = Reader(mode=task_mode).init_meta()

    (fa_events, fa_features), _, _ = reader._generate_dataset(data_mode=DatasetModes.TEST, ft_mode=FeatureModes.FULL_SEP)
    (cf_events, cf_features), _ = reader._generate_dataset(data_mode=DatasetModes.VAL, ft_mode=FeatureModes.FULL_SEP)

    fa_batch, fa_seq_len, fa_ft_size = fa_features.shape
    cf_batch, cf_seq_len, cf_ft_size = cf_features.shape

    a = np.repeat(fa_events, cf_batch, axis=0), np.repeat(fa_features, cf_batch, axis=0)
    b = np.repeat(cf_events[None], fa_batch, axis=0).reshape(-1, cf_seq_len), np.repeat(cf_features[None], fa_batch, axis=0).reshape(-1, cf_seq_len, cf_ft_size)


    sparcity_computer = SparcityMetric(reader.vocab_len, reader.max_len)


    bulk_distances = sparcity_computer.compute_valuation(a, b)

    print(f"All results\n{bulk_distances}")
    if bulk_distances.sum() == 0:
        print("Hmm...")


