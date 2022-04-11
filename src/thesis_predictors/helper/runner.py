import io
from typing import Type
from tensorflow.keras.models import Model
import tqdm
import json
from tensorflow.keras.optimizers import Adam
import pathlib

from thesis_commons.modes import TaskModeType
from ..models.model_commons import ModelInterface
from thesis_commons.modes import FeatureModes, DatasetModes
from thesis_readers import AbstractProcessLogReader
from ..helper.evaluation import FULL, Evaluator
from thesis_commons.metric import MSpCatCE,MSpCatAcc


# TODO: Put in runners module. This module is a key module not a helper.
DEBUG = True

class Runner(object):
    statistics = {}

    def __init__(
            self,
            Model: Type[ModelInterface],
            reader: AbstractProcessLogReader,
            epochs: int,
            batch_size: int,
            adam_init: float,
            num_train: int = None,
            num_val: int = None,
            num_test: int = None,
            ft_mode: FeatureModes = FeatureModes.EVENT_ONLY,
            **kwargs,
    ):
        self.reader = reader
        self.train_dataset = self.reader.get_dataset(batch_size, DatasetModes.TRAIN, ft_mode=ft_mode)
        self.val_dataset = self.reader.get_dataset(batch_size, DatasetModes.VAL, ft_mode=ft_mode)
        self.test_dataset = self.reader.get_dataset_with_indices(DatasetModes.TEST, ft_mode=ft_mode)
        self.model = Model(vocab_len=self.reader.vocab_len, max_len=self.reader.max_len, feature_len=self.reader.current_feature_len, **kwargs)

        if num_train:
            self.train_dataset = self.train_dataset.take(num_train)
        if num_val:
            self.val_dataset = self.val_dataset.take(num_val)
        if num_test:
            self.test_dataset = self.test_dataset.take(num_test) # TODO: IMPORTANT FIX - Was the wrong parameter!!!!
        

        self.epochs = epochs
        self.batch_size = batch_size
        self.adam_init = adam_init
        self.start_id = reader.start_id
        self.end_id = reader.end_id

        self.label = self.model.name

    def train_model(self, label=None, train_dataset=None, val_dataset=None):
        label = label or self.label
        train_dataset = train_dataset or self.train_dataset
        val_dataset = val_dataset or self.val_dataset
        # self.metrics = metrics
        # self.loss_fn = loss_fn

        print(f"{label}:")
        # TODO: Impl: check that checks whether ft_mode is compatible with model feature type
        self.model.compile(loss=self.model.loss_fn, optimizer=Adam(self.adam_init), metrics=self.model.metrics, run_eagerly=DEBUG)
        self.model.summary()

        # vd_1, vd_2 = [], []
        # for datapoint in val_dataset:
        #     vd_1.extend((datapoint[0], ))
        #     vd_2.extend((datapoint[1], ))
        # for epoch in tqdm.tqdm(range(self.epochs)):
        #     for X, y in train_dataset:
        #         train_results = self.model.fit(X, y[0], verbose=1)
        #         self.statistics[epoch] = {"history": train_results}
        #     val_loss, val_acc = self.model.evaluate(vd_1[0], vd_2[0])
        #     self.statistics[epoch].update({
        #         "train_loss" : train_results.history['loss'][-1],
        #         "train_acc" : train_results.history['accuracy'][-1],
        #         "val_loss" : val_loss,
        #         "val_acc" : val_acc,
        #     })

        # if self.model.task_mode_type == TaskModeType.FIX2ONE:
        #     class_weights = {idx: self.reader.cls_reweighting.get(idx, 0) for idx in range(self.reader.vocab_len)}
        #     self.history = self.model.fit(train_dataset, validation_data=val_dataset, epochs=self.epochs, class_weight=class_weights)
        # if self.model.task_mode_type == TaskModeType.FIX2FIX:
        #     self.history = self.model.fit(train_dataset, validation_data=val_dataset, epochs=self.epochs)

        self.history = self.model.fit(train_dataset, validation_data=val_dataset, epochs=self.epochs)

        # class_weights = {f"position_{idx}": class_weights for idx in range(self.reader.max_len)}

        return self

    def evaluate(self, evaluator: Evaluator, save_path="results", prefix="full", label=None, test_dataset=None, dont_save=False):
        test_dataset = test_dataset or self.test_dataset
        test_dataset = self.reader.gather_full_dataset(self.test_dataset)
        self.results = evaluator.set_model(self.model).evaluate(test_dataset)
        if not dont_save:
            label = label or self.label
            save_path = save_path or self.save_path
            self.results.to_csv(pathlib.Path(save_path) / (f"{prefix}_{label}.csv"))
        return self

    def save_model(self, save_path="build", prefix="full", label=None):
        label = label or self.label
        save_path = save_path or self.save_path
        target_folder = pathlib.Path(save_path) / (f"{prefix}_{label}")
        self.model.save(target_folder)
        self.model_path = target_folder
        json.dump(self._transform_model_history(), io.open(target_folder / 'history.json', 'w'), indent=4, sort_keys=True)
        return self

    def _transform_model_history(self):
        tmp_history = dict(self.history.history)
        tmp_history["epochs"] = self.history.epoch
        history = {
            "history": tmp_history,
            "params": self.history.params,
        }
        return history