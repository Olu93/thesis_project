
from enum import Enum
import pathlib
import importlib_resources
from thesis_commons.config import DEBUG_DATASET, READER

from thesis_commons.functions import create_path
import tensorflow as tf

keras = tf.keras
from keras import backend as K
from keras.utils.losses_utils import ReductionV2  


PATH_ROOT: pathlib.Path = importlib_resources.files(__package__).parent.parent
PATH_MODELS = PATH_ROOT / "models"
PATH_MODELS_PREDICTORS = PATH_MODELS / "predictors"
PATH_MODELS_GENERATORS = PATH_MODELS / "generators"
PATH_MODELS_OTHERS = PATH_MODELS / "others"
PATH_RESULTS = PATH_ROOT / "results"
PATH_RESULTS_MODELS_OVERALL = PATH_RESULTS / "models_overall"
PATH_RESULTS_MODELS_SPECIFIC = PATH_RESULTS / "models_specific"
PATH_READERS = PATH_ROOT / "readers"

print("================= Folders =====================")
create_path("PATH_ROOT", PATH_ROOT)
create_path("PATH_MODELS", PATH_MODELS)
create_path("PATH_MODELS_PREDICTORS", PATH_MODELS_PREDICTORS)
create_path("PATH_MODELS_GENERATORS", PATH_MODELS_GENERATORS)
print("==============================================")


class StringEnum(str, Enum):
    def __repr__(self):
        return self.name


class CMeta(StringEnum):
    IMPRT = 'important'
    FEATS = 'features'
    NON = 'other'


class CDType(StringEnum):
    BIN = 'binaricals'
    CAT = 'categoricals'
    NUM = 'numericals'
    TMP = 'temporals'
    NON = 'other'


class CDomainMappings():
    ALL_DISCRETE = [CDType.BIN, CDType.CAT]
    ALL_CONTINUOUS = [CDType.NUM, CDType.TMP]
    ALL_IMPORTANT = ['inportant', 'timestamp']
    ALL = [CDType.BIN, CDType.CAT, CDType.NUM, CDType.TMP]


class CDomain(StringEnum):
    DISCRETE = 'discrete'
    CONTINUOUS = 'continuous'
    NON = 'none'

    @classmethod
    def map_dtype(cls, dtype):
        if dtype in CDomainMappings.ALL_DISCRETE:
            return cls.DISCRETE
        if dtype in CDomainMappings.ALL_CONTINUOUS:
            return cls.CONTINUOUS

        return cls.NON

DS_BPIC_S = 'OutcomeBPIC12ReaderShort'
DS_BPIC_M = 'OutcomeBPIC12ReaderMedium'
DS_BPIC_F = 'OutcomeBPIC12ReaderFull'
DS_LITERATURE = 'OutcomeDice4ELReader'
DS_SEPSIS = 'OutcomeSepsis1Reader'
DS_TRAFFIC = 'OutcomeTrafficFineReader'
MAIN_READER = READER
ALL_DATASETS = [DS_BPIC_S, DS_BPIC_M, DS_BPIC_F, DS_LITERATURE, DS_SEPSIS, DS_TRAFFIC] if not DEBUG_DATASET else [MAIN_READER]

REDUCTION = ReductionV2 