import pathlib
from typing import List
import tensorflow as tf
import tensorflow.python.keras as keras
import tensorflow.python.keras.backend as K
from tensorflow.python.keras import layers
import numpy as np
from tensorflow.python.keras import losses
from tensorflow.python.keras import callbacks
from thesis_commons.functions import create_path

from thesis_commons.constants import PATH_ROOT


class CallbackCollection:

    def __init__(
        self,
        model_name: str,
        models_dir: pathlib.Path,
        is_prod: bool = False,
    ) -> None:
        self.model_name = model_name
        self.models_dir = models_dir
        tmp_chkpt_path = create_path("chkpt_path", self.models_dir / self.model_name)
        self.chkpt_path = tmp_chkpt_path 
        self.tboard_path = create_path("tboard_path", PATH_ROOT / 'logs' / self.model_name)
        self.csv_logger_path = tmp_chkpt_path / "history.csv"
        self.cb_list = []
        self.is_prod = is_prod

    def add(self, cb: callbacks.Callback):
        self.cb_list.append(cb)
        return self

    def build(self):
        self.cb_list.append(callbacks.ModelCheckpoint(filepath=self.chkpt_path, verbose=0 if self.is_prod else 1, save_best_only=self.is_prod))
        self.cb_list.append(callbacks.TensorBoard(log_dir=self.tboard_path))
        self.cb_list.append(callbacks.CSVLogger(filename=self.csv_logger_path))
        return self.cb_list
