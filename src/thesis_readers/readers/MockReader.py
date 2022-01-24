from typing import Counter
import tensorflow as tf

from ..helper.modes import DatasetModes, FeatureModes
from .AbstractProcessLogReader import AbstractProcessLogReader
import numpy as np
import pandas as pd


class MockReader(AbstractProcessLogReader):
    def __init__(self, random_feature_len = 42) -> None:
        feature_len = random_feature_len
        self.y_true = np.array([
            [1, 2, 3, 6, 0, 0],
            [1, 2, 1, 2, 3, 4],
            [1, 2, 1, 1, 2, 3],
            [1, 2, 1, 2, 3, 4],
            [1, 1, 2, 5, 0, 0],
            [1, 1, 2, 5, 0, 0],
            [1, 2, 3, 6, 0, 0],
            [1, 1, 1, 2, 3, 4],
            [1, 1, 1, 2, 3, 4],
            [1, 2, 3, 6, 0, 0],
            [1, 2, 3, 6, 0, 0],
            [1, 2, 3, 6, 0, 0],
            [1, 2, 3, 6, 0, 0],
            [1, 2, 1, 1, 2, 3],
        ], dtype=np.int32)
        nonzeros = np.nonzero(self.y_true)
        log_len, num_max_events = self.y_true.shape[0], self.y_true.shape[1]
        case_ids = np.arange(1, log_len+1)[:,None] * np.ones_like(self.y_true)
        times = np.arange(1, num_max_events+1)[None,:] * np.ones_like(self.y_true)
        features = np.random.uniform(-5, 5, size=(log_len, num_max_events, feature_len))

        ys = self.y_true[nonzeros][None].T
        ids = case_ids[nonzeros][None].T
        tm = times[nonzeros][None].T
        fts = features[nonzeros]
        self.data = pd.DataFrame(np.concatenate([ids, tm, fts, ys], axis=1))

        self.col_timestamp = "tm"
        self.col_case_id = "case_id"
        self.col_activity_id = "event_id"
        self.col_timestamp_all = [self.col_timestamp]
        new_columns = [f"ft_{idx}" for idx in self.data.columns]
        new_columns[0] = self.col_case_id
        new_columns[1] = self.col_timestamp
        new_columns[len(self.data.columns)-1] = self.col_activity_id
        self.data.columns = new_columns
        print("USING MOCK DATASET!")

    def init_log(self, save=False):
        self.log = None
        self._original_data = None
        return self

    def init_data(self):
        self.register_vocabulary()
        self.group_rows_into_traces()
        self.gather_information_about_traces()
        self.instantiate_dataset()
        return self


    def get_dataset(self, batch_size=None, data_mode: DatasetModes = DatasetModes.TRAIN, ft_mode: FeatureModes = FeatureModes.EVENT_ONLY):
        results = self._prepare_input_data(self.traces, self.targets, ft_mode)
        bs = self.log_len if batch_size is None else min([batch_size, self.log_len]) 
        return tf.data.Dataset.from_tensor_slices(results).batch(bs)