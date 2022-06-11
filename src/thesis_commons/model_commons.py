import abc
from typing import Any, Sequence, Tuple
import pandas as pd
import numpy as np
import tensorflow as tf
from tqdm import tqdm
from thesis_commons.constants import PATH_RESULTS_MODELS_SPECIFIC

# from tensorflow.keras import Model, layers, optimizers
# from tensorflow.keras.losses import Loss, SparseCategoricalCrossentropy
# from tensorflow.keras.metrics import Metric, SparseCategoricalAccuracy
from thesis_commons.libcuts import K, layers, losses, metrics
from thesis_commons.modes import FeatureModes, TaskModeType
from thesis_commons.representations import Cases, EvaluatedCases, SortedCases
from thesis_commons.statististics import InstanceData, RunData
from thesis_viability.viability.viability_function import (MeasureMask,
                                                           ViabilityMeasure)


class Sampler(layers.Layer):
    """Uses (z_mean, z_log_var) to sample z, the vector encoding a digit."""
    def call(self, inputs):
        # Why log(x) - https://stats.stackexchange.com/a/486161
        z_mean, z_log_var = inputs
        # Why log(variance) - https://stats.stackexchange.com/a/486205

        epsilon = K.random_normal(shape=tf.shape(z_mean))
        return z_mean + tf.exp(0.5 * z_log_var) * epsilon


# class RandomPicker(layers.Layer):
#     def call(self, inputs):
#         z_mean, z_log_var = inputs

#         epsilon = K.random_normal(shape=tf.shape(z_mean))
#         return z_mean + tf.exp(0.5 * z_log_var) * epsilon


class ReverseEmbedding(layers.Layer):
    def __init__(self, embedding_layer: layers.Embedding, trainable=True, name=None, dtype=None, dynamic=False, **kwargs):
        super().__init__(trainable, name, dtype, dynamic)
        self.embedding_layer = embedding_layer

    def call(self, inputs, **kwargs):
        B = self.embedding_layer.get_weights()[0]
        A = K.reshape(inputs, (-1, B.shape[1]))
        similarities = self.cosine_similarity_faf(A, B)
        indices = K.argmax(similarities)
        indices_reshaped = tf.reshape(indices, inputs.shape[:2])
        indices_onehot = tf.keras.utils.to_categorical(indices_reshaped, A.shape[1])

        return indices_onehot

    def cosine_similarity_faf(self, A, B):
        nominator = A @ B
        norm_A = tf.norm(A, axis=1)
        norm_B = tf.norm(B, axis=1)
        denominator = tf.reshape(norm_A, [-1, 1]) * tf.reshape(norm_B, [1, -1])
        return tf.divide(nominator, denominator)


class BaseModelMixin:
    # def __init__(self) -> None:
    task_mode_type: TaskModeType = None
    loss_fn: losses.Loss = None
    metric_fn: metrics.Metric = None

    def __init__(self, ft_mode: FeatureModes, vocab_len: int, max_len: int, feature_len: int, **kwargs):
        print(__class__)
        super().__init__(**kwargs)
        self.vocab_len = vocab_len
        self.max_len = max_len
        self.feature_len = feature_len
        self.ft_mode = ft_mode
        self.kwargs = kwargs


class DistanceOptimizerModelMixin(BaseModelMixin):
    def __init__(self, name: str, distance: ViabilityMeasure, *args, **kwargs) -> None:
        print(__class__)
        super(DistanceOptimizerModelMixin, self).__init__(*args, **kwargs)
        self.picks = None
        self.name = name
        self.distance = distance

    def __call__(self, ):
        raise NotImplementedError('Class method needs to be subclassed and overwritten.')

    def predict(self, inputs):
        return self.__call__(inputs)

    def compute_topk_picks(self):
        raise NotImplementedError('Class method needs to be subclassed and overwritten.')

    def compute_viabilities(self, fa_cases:Cases, cf_cases:Cases):
        viability_values = self.distance.compute(fa_cases, cf_cases)
        partial_values = self.distance.partial_values
        return viability_values, partial_values

    def compute_shapes(self, topk, batch_size, seq_len):
        shape_ft = (batch_size, topk, seq_len, -1)
        shape_ev = (batch_size, topk, seq_len)
        shape_viab = (batch_size, topk)
        shape_parts = (-1, batch_size, topk)
        return shape_ev, shape_ft, shape_viab, shape_parts

    def pick_chosen_indices(self, viability_values: np.ndarray, topk: int = 5):
        num_fs, num_cfs = viability_values.shape
        ranking = np.argsort(viability_values, axis=1)
        best_indices = ranking[:, :-topk + 1]
        base_indices = np.repeat(np.arange(num_fs)[..., None], topk, axis=1)

        chosen_indices = np.stack((base_indices.flatten(), best_indices.flatten()), axis=0)
        return chosen_indices, None, ranking

    def pick_topk(self, cf_ev, cf_ft, viabilities, partials, chosen, mask, ranking):
        new_viabilities = viabilities[chosen[0], chosen[1]]
        new_partials = partials[:, chosen[0], chosen[1]]
        chosen_ev, chosen_ft = cf_ev[chosen[1]], cf_ft[chosen[1]]
        return chosen_ev, chosen_ft, new_viabilities, new_partials

    def compute_topk_picks(self, topk, fa_ev, fa_ft, cf_ev, cf_ft):
        batch_size, sequence_length, feature_len = fa_ft.shape
        viab_values, parts_values = self.compute_viabilities(fa_ev, fa_ft, cf_ev, cf_ft)
        chosen, mask, ranking = self.pick_chosen_indices(viab_values, topk)
        shape_ev, shape_ft, shape_viab, shape_parts = self.compute_shapes(topk, batch_size, sequence_length)
        all_shapes = [shape_ev, shape_ft, shape_viab, shape_parts]
        chosen_ev, chosen_ft, new_viabilities, new_partials = self.pick_topk(cf_ev, cf_ft, viab_values, parts_values, chosen, mask, ranking)
        all_picked = [chosen_ev, chosen_ft, new_viabilities, new_partials]
        chosen_ev, chosen_ft, new_viabilities, new_partials = self.compute_reshaping(all_picked, all_shapes)
        picks = {'events': chosen_ev, 'features': chosen_ft, 'viabilities': new_viabilities, 'partials': new_partials}
        return picks, new_partials

    def compute_reshaping(self, all_picked, all_shapes):
        reshaped_picks = tuple([pick.reshape(shape) for pick, shape in zip(all_picked, all_shapes)])
        return reshaped_picks


class ProcessInputLayer(tf.keras.layers.Layer):
    def __init__(self, max_len, feature_len, trainable=True, name=None, dtype=None, dynamic=False, **kwargs):
        super().__init__(trainable, name, dtype, dynamic, **kwargs)
        self.max_len = max_len
        self.feature_len = feature_len
        # self.events = tf.keras.layers.Input(shape=(self.max_len, ), name="events")
        # self.features = tf.keras.layers.Input(shape=(self.max_len, self.feature_len), name="event_features")
        # self.events = tf.keras.layers.InputLayer(input_shape=(self.max_len, ), name="events")
        # self.features = tf.keras.layers.InputLayer(input_shape=(self.max_len, self.feature_len), name="event_features")
        # self.input_layer = tf.keras.layers.InputLayer(shape=[(self.max_len, ),(self.max_len, self.feature_len)], name="event_attributes")

    def build(self, input_shape=None):
        events_shape, features_shape = input_shape
        self.events = tf.keras.layers.InputLayer(input_shape=events_shape[1:], name="events")
        self.features = tf.keras.layers.InputLayer(input_shape=features_shape[1:], name="event_features")

    def call(self, inputs, *args, **kwargs):
        events, features = inputs
        result = self.events(events), self.features(features)
        return result

    # def call(self, inputs, *args, **kwargs):
    #     events, features = inputs
    #     result = [self.events(events), self.features(features)]
    #     # result = self.input_layer(inputs)
    #     # result = events, features
    #     return result

    def get_config(self):
        config = {
            "max_len": self.max_len,
            "feature_len": self.feature_len,
        }
        # config.update(self.kwargs)
        return config


class TensorflowModelMixin(BaseModelMixin, tf.keras.Model):
    def __init__(self, *args, **kwargs) -> None:
        print(__class__)
        super(TensorflowModelMixin, self).__init__(*args, **kwargs)
        # TODO: Turn to layer
        # self.input_layer = tf.keras.layers.InputLayer(input_shape=((self.max_len, ),(self.max_len, self.feature_len)), name="event_attributes")
        self.input_layer = ProcessInputLayer(self.max_len, self.feature_len)

    def build(self, input_shape):
        events_shape, features_shape = input_shape
        # self.events = tf.keras.layers.InputLayer(input_shape=events_shape.shape[1:], name="events")
        # self.features = tf.keras.layers.InputLayer(input_shape=features_shape.shape[1:], name="event_features")
        # self.events = tf.keras.layers.Input(shape=events_shape.shape[1:], name="events")
        # self.features = tf.keras.layers.Input(shape=features_shape.shape[1:], name="event_features")
        # self.input_layer = ProcessInputLayer(self.max_len, self.feature_len)
        self.input_layer.build((events_shape, features_shape))
        self.built = True
        # return super().build(input_shape)

    def compile(self, optimizer=None, loss=None, metrics=None, loss_weights=None, weighted_metrics=None, run_eagerly=None, steps_per_execution=None, **kwargs):
        optimizer = optimizer or tf.keras.optimizers.Adam()
        events_shape, features_shape = (None, self.max_len), (None, self.max_len, self.feature_len)
        self.build((events_shape, features_shape))
        return super().compile(optimizer, loss, metrics, loss_weights, weighted_metrics, run_eagerly, steps_per_execution, **kwargs)

    def get_config(self):
        config = {
            "vocab_len": self.vocab_len,
            "max_len": self.max_len,
            "feature_len": self.feature_len,
        }
        config.update(self.kwargs)
        return config

    @classmethod
    def from_config(cls, config):
        return cls(**config)

    def build_graph(self) -> tf.keras.Model:
        events = tf.keras.layers.Input(shape=(self.max_len, ), name="events")
        features = tf.keras.layers.Input(shape=(self.max_len, self.feature_len), name="event_features")
        results = [events, features]
        summarizer = tf.keras.models.Model(inputs=[results], outputs=self.call(results))
        return summarizer

    def summary(self, line_length=None, positions=None, print_fn=None, expand_nested=False, show_trainable=False):
        summarizer = self.build_graph()
        summary = summarizer.summary(line_length, positions, print_fn, expand_nested, show_trainable)
        # self.build(summarizer.input_shape[0])
        return summary

    # def call(self, inputs, training=None, mask=None):
    #     result = self.input_layer.call(inputs, training, mask)
    #     return result
    # def call(self, inputs, training=None, mask=None):
    #     return super().call(inputs, training, mask)


class GeneratorMixin(abc.ABC):
    def __init__(self, predictor: TensorflowModelMixin, generator: BaseModelMixin, evaluator: ViabilityMeasure, top_k: int = None, measure_mask:MeasureMask = None, **kwargs) -> None:
        super(GeneratorMixin, self).__init__()
        # self.name = 
        self.measure_mask = measure_mask or MeasureMask()
        self.evaluator = evaluator
        self.predictor = predictor
        self.generator = generator
        self.run_stats = RunData()
        self.top_k = top_k
        
    def set_measure_mask(self, measure_mask: MeasureMask = None):
        self.measure_mask = measure_mask or MeasureMask()
        return self

    def generate(self, fa_seeds: Cases, **kwargs) -> Sequence[EvaluatedCases]:
        results: Sequence[EvaluatedCases] = []
        pbar = tqdm(enumerate(fa_seeds), total=len(fa_seeds), desc=f"{self.generator.name}")
        self.evaluator = self.evaluator.apply_measure_mask(self.measure_mask)
        for instance_num, fa_case in pbar:
            generation_results, stats = self.execute_generation(fa_case, **kwargs)
            # result = self.construct_result(generation_results, **kwargs)
            reduced_results = self.get_topk(generation_results, top_k=self.top_k).set_instance_num(instance_num).set_creator(self.name).set_fa_case(fa_case)
            self.run_stats.update(stats)
            tmp = self.run_stats.data # DELETE
            results.append(reduced_results)

        return results

    @abc.abstractmethod
    def execute_generation(self, fc_case, **kwargs) -> Tuple[EvaluatedCases, Sequence[InstanceData]]:
        pass

    @abc.abstractmethod
    def construct_result(self, generation_results, **kwargs) -> EvaluatedCases:
        pass

    def get_topk(self, result: EvaluatedCases, top_k: int = None) -> SortedCases:
        if top_k is not None:
            return result.get_topk(top_k)
        return result.sort()

    def save_statistics(self) -> bool:
        data:pd.DataFrame = self._instance_statistics.data
        target = PATH_RESULTS_MODELS_SPECIFIC/(self.name + ".csv")
        data.to_csv(target.open("w"))


    @property
    def name(self):
        return f"{type(self).__name__}_top{self.top_k}"