from enum import Enum, auto
from typing import Any, Generic, Type, TypeVar
import tensorflow as tf
from thesis_commons import modes
from thesis_viability.viability.viability_function import ViabilityMeasure
from thesis_commons.libcuts import K, optimizers, layers, models, losses, metrics, utils
# from tensorflow.keras import Model, layers, optimizers
# from tensorflow.keras.losses import Loss, SparseCategoricalCrossentropy
# from tensorflow.keras.metrics import Metric, SparseCategoricalAccuracy
from thesis_commons import metric
from thesis_commons.modes import TaskModeType, InputModeType
import inspect
import abc
import numpy as np


# TODO: Fix imports by collecting all commons
# TODO: Rename to 'SamplingLayer'
class Sampler(layers.Layer):
    """Uses (z_mean, z_log_var) to sample z, the vector encoding a digit."""
    def call(self, inputs):
        # Why log(x) - https://stats.stackexchange.com/a/486161
        z_mean, z_log_var = inputs
        # Why log(variance) - https://stats.stackexchange.com/a/486205

        epsilon = K.random_normal(shape=tf.shape(z_mean))
        return z_mean + tf.exp(0.5 * z_log_var) * epsilon


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


class GeneratorType(Enum):
    TRADITIONAL = auto()  # Masked sparse categorical loss and metric version


class BaseModelMixin:
    # def __init__(self) -> None:
    task_mode_type: TaskModeType = None
    loss_fn: losses.Loss = None
    metric_fn: metrics.Metric = None

    def __init__(self, vocab_len, max_len, feature_len, *args, **kwargs):
        print(__class__)
        super(BaseModelMixin, self).__init__()
        self.vocab_len = vocab_len
        self.max_len = max_len
        self.feature_len = feature_len
        self.kwargs = kwargs


class JointTrainMixin:
    def __init__(self, *args, **kwargs) -> None:
        print(__class__)
        super(JointTrainMixin, self).__init__(*args, **kwargs)
        self.optimizer = optimizers.Adam()

    def construct_loss(self, loss, default_losses):
        loss = (metric.JoinedLoss(loss) if type(loss) is list else loss) if loss else (metric.JoinedLoss(default_losses) if type(default_losses) is list else default_losses)
        return loss

    def construct_metrics(self, loss, metrics, default_metrics):
        metrics = [loss] + metrics if metrics else [loss] + default_metrics
        if type(loss) is metric.JoinedLoss:
            metrics = loss.composites + metrics
        return metrics


class HybridGraph():
    def __init__(self, *args, **kwargs) -> None:
        super(HybridGraph, self).__init__(*args, **kwargs)
        self.in_events = tf.keras.layers.Input(shape=(self.max_len, ))  # TODO: Fix import
        self.in_features = tf.keras.layers.Input(shape=(self.max_len, self.feature_len))
        self.in_layer_shape = [self.in_events, self.in_features]

    def build_graph(self):
        events = layers.Input(shape=(self.max_len, ))
        features = layers.Input(shape=(self.max_len, self.feature_len))
        inputs = [events, features]
        summarizer = models.Model(inputs=[inputs], outputs=self.call(inputs))
        return summarizer


class DistanceOptimizerModelMixin(BaseModelMixin):
    def __init__(self, *args, **kwargs) -> None:
        print(__class__)
        super(DistanceOptimizerModelMixin, self).__init__(*args, **kwargs)
        self.picks = None

    def fit(self, inputs, predictive_model: models.Model):
        self.distance = ViabilityMeasure(self.vocab_len, self.max_len, inputs, predictive_model)

    def __call__(self, ):
        raise NotImplementedError('Class method needs to be subclassed and overwritten.')

    def predict(self, inputs):
        return self.__call__(inputs)

    def compute_topk_picks(self):
        raise NotImplementedError('Class method needs to be subclassed and overwritten.')

    def compute_viabilities(self, events_input, features_input, cf_ev, cf_ft):
        viability_values = self.distance.compute_valuation(events_input, features_input, cf_ev, cf_ft)
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

        # mask_topk = (ranking >= (num_cfs - topk))
        # top_ranking = ranking[mask_topk].reshape((num_fs, topk))

        # order_1 = top_ranking + np.arange(0, num_fs)[..., None]*topk
        # order_2 = np.argsort(order_1).flatten()
        # indices = np.arange(0, order_2.shape[0])

        # chosen_indices = np.where(mask_topk)
        # best_values = viability_values[mask_topk].reshape((num_fs, topk))
        # # sorted_indices =
        # chosen_indices = np.stack(chosen_indices , axis=-1).reshape((num_fs, topk, -1))
        # chosen_indices = np.sort(chosen_indices, axis=1).reshape((-1, 2)).T
        # ranking = ranking[mask_topk].reshape((num_fs, topk)).argsort(axis=1)

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
        return picks

    def compute_reshaping(self, all_picked, all_shapes):
        reshaped_picks = tuple([pick.reshape(shape) for pick, shape in zip(all_picked, all_shapes)])
        return reshaped_picks


class TensorflowModelMixin(BaseModelMixin, JointTrainMixin, models.Model):
    def __init__(self, *args, **kwargs) -> None:
        print(__class__)
        super(TensorflowModelMixin, self).__init__(*args, **kwargs)

    def compile(self, optimizer=None, loss=None, metrics=None, loss_weights=None, weighted_metrics=None, run_eagerly=None, steps_per_execution=None, **kwargs):
        optimizer = optimizer or self.optimizer
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

    def build_graph(self):
        events = tf.keras.layers.Input(shape=(self.max_len, ), name="events")
        features = tf.keras.layers.Input(shape=(self.max_len, self.feature_len), name="event_attributes")
        inputs = [events, features]
        summarizer = models.Model(inputs=[inputs], outputs=self.call(inputs))
        return summarizer


class InterpretorPartMixin(BaseModelMixin, JointTrainMixin, models.Model):
    def __init__(self, *args, **kwargs) -> None:
        print(__class__)
        super(InterpretorPartMixin, self).__init__(*args, **kwargs)

    def compile(self, optimizer=None, loss=None, metrics=None, loss_weights=None, weighted_metrics=None, run_eagerly=None, steps_per_execution=None, **kwargs):
        optimizer = optimizer or self.optimizer
        return super().compile(optimizer, loss, metrics, loss_weights, weighted_metrics, run_eagerly, steps_per_execution, **kwargs)


class MetricTypeMixin:
    def __init__(self, *args, **kwargs) -> None:
        print(__class__)
        super(MetricTypeMixin, self).__init__(*args, **kwargs)


class MetricVAEMixin(MetricTypeMixin):
    def __init__(self, *args, **kwargs) -> None:
        print(__class__)
        super(MetricVAEMixin, self).__init__(*args, **kwargs)
        self.rec_loss = metric.GaussianReconstructionLoss()
        self.kl_loss = metric.SimpleKLDivergence()
        self.loss = None
        self.metric = None

    def compute_loss(self, y_true: tf.Tensor, y_pred: tf.Tensor, z_mean: tf.Tensor, z_log_var: tf.Tensor):
        rec_loss = self.rec_loss(y_true, y_pred) * y_true.shape[1]
        kl_loss = self.kl_loss(z_mean, z_log_var) * y_true.shape[1]
        return {
            "rec_loss": rec_loss,
            "kl_loss": kl_loss,
        }


class InputModeTypeDetector:
    pass  # Maybe override build


class CustomInputLayer(layers.Layer):
    in_layer_shape = None

    def __init__(self, trainable=True, name=None, dtype=None, dynamic=False, **kwargs):
        super().__init__(trainable, name, dtype, dynamic, **kwargs)

    def call(self, inputs, **kwargs):
        return super().call(inputs, **kwargs)


class TokenInputLayer(CustomInputLayer):
    def __init__(self, max_len, feature_len, *args, **kwargs) -> None:
        print(__class__)
        super(TokenInputLayer, self).__init__(*args, **kwargs)
        self.in_layer_shape = tf.keras.layers.Input(shape=(max_len, ))

    def call(self, inputs, **kwargs):
        return self.in_layer_shape.call(inputs, **kwargs)


class HybridInputLayer(CustomInputLayer):
    def __init__(self, max_len, feature_len, *args, **kwargs) -> None:
        super(HybridInputLayer, self).__init__(*args, **kwargs)
        self.in_events = tf.keras.layers.Input(shape=(max_len, ))  # TODO: Fix import
        self.in_features = tf.keras.layers.Input(shape=(max_len, feature_len))
        self.in_layer_shape = [self.in_events, self.in_features]

    def call(self, inputs, **kwargs):
        x = [self.in_layer_shape[idx].call(inputs[idx], **kwargs) for idx in enumerate(inputs)]
        return x


class VectorInputLayer(CustomInputLayer):
    def __init__(self, max_len, feature_len, *args, **kwargs) -> None:
        super(VectorInputLayer, self).__init__(*args, **kwargs)
        self.in_layer_shape = tf.keras.layers.Input(shape=(max_len, feature_len))

    def call(self, inputs, **kwargs):
        return self.in_layer_shape.call(inputs, **kwargs)


class EmbedderLayer(models.Model):
    def __init__(self, feature_len=None, max_len=None, ff_dim=None, vocab_len=None, embed_dim=None, mask_zero=0, *args, **kwargs) -> None:
        print(__class__)
        super(EmbedderLayer, self).__init__(*args, **kwargs)
        self.embedder = layers.Embedding(vocab_len, embed_dim, mask_zero=mask_zero, *args, **kwargs)
        self.feature_len: int = feature_len
        self.vocab_len: int = vocab_len

    def call(self, inputs, **kwargs):
        indices, other_features = inputs
        features = self.embedder(indices)
        self.feature_len = features.shape[-1]
        return features

    def get_config(self):
        return {"feature_len": self.feature_len, "vocab_len": self.vocab_len}

    @classmethod
    def from_config(cls, config):
        return cls(**config)


class OnehotEmbedderLayer(EmbedderLayer):
    def __init__(self, vocab_len, embed_dim, mask_zero=0, *args, **kwargs) -> None:
        print(__class__)
        super(OnehotEmbedderLayer, self).__init__(vocab_len=vocab_len, embed_dim=embed_dim, mask_zero=mask_zero, *args, **kwargs)
        # self.embedder = layers.CategoryEncoding(vocab_len, output_mode="one_hot")
        # self.test = layers.Lambda(lambda ev_sequence: self.embedder(ev_sequence))
        self.embedder = layers.Lambda(OnehotEmbedderLayer._one_hot, arguments={'num_classes': vocab_len})

    @classmethod
    def _one_hot(x, num_classes):
        return K.one_hot(K.cast(x, tf.uint8), num_classes=num_classes)

    def call(self, inputs, **kwargs):
        indices = inputs
        # features = self.test(indices)
        features = self.embedder(indices)
        self.feature_len = features.shape[-1]
        return features


# class OneHotEncodingLayer():
#     # https://fdalvi.github.io/blog/2018-04-07-keras-sequential-onehot/
#     def __init__(self, input_dim=None, input_length=None) -> None:
#         # Check if inputs were supplied correctly
#         if input_dim is None or input_length is None:
#             raise TypeError("input_dim or input_length is not set")
#         self.input_dim = input_dim
#         self.input_length = input_length
#         self.embedder = layers.Lambda(self._one_hot, arguments={'num_classes': input_dim}, input_shape=(input_length, ))

#     # Helper method (not inlined for clarity)
#     def _one_hot(x, num_classes):
#         return K.one_hot(K.cast(x, tf.uint16), num_classes=num_classes)

#     def call(self, input):
#         # Final layer representation as a Lambda layer
#         return self.embedder(input)


class TokenEmbedderLayer(EmbedderLayer):
    def __init__(self, vocab_len, embed_dim, mask_zero=0, *args, **kwargs) -> None:
        print(__class__)
        super(TokenEmbedderLayer, self).__init__(vocab_len=vocab_len, embed_dim=embed_dim, mask_zero=mask_zero, *args, **kwargs)

    def call(self, inputs, **kwargs):
        indices = inputs
        features = self.embedder(indices)
        self.feature_len = features.shape[-1]
        return features


class HybridEmbedderLayer(EmbedderLayer):
    def __init__(self, vocab_len, embed_dim, mask_zero=0, *args, **kwargs) -> None:
        super(HybridEmbedderLayer, self).__init__(vocab_len=vocab_len, embed_dim=embed_dim, mask_zero=mask_zero, *args, **kwargs)
        self.concatenator = layers.Concatenate(name="concat_embedding_and_features")

    def call(self, inputs, **kwargs):
        indices, other_features = inputs
        embeddings = self.embedder(indices)
        features = self.concatenator([embeddings, other_features])
        self.feature_len = features.shape[-1]
        return features


class VectorEmbedderLayer(EmbedderLayer):
    def __init__(self, vocab_len, embed_dim, mask_zero=0) -> None:
        super(VectorEmbedderLayer, self).__init__(vocab_len, embed_dim, mask_zero)

    def call(self, inputs, **kwargs):
        features = inputs[0]
        self.feature_len = features.shape[-1]
        return features


class EmbedderConstructor():
    def __new__(cls, **kwargs) -> Any:
        ft_mode = kwargs.pop('ft_mode', None)
        input_mode = modes.InputModeType.type(ft_mode)
        if input_mode == modes.InputModeType.TOKEN_INPUT:
            return TokenEmbedderLayer(**kwargs)
        if input_mode == modes.InputModeType.VECTOR_INPUT:
            return VectorEmbedderLayer(**kwargs)
        if input_mode == modes.InputModeType.DUAL_INPUT:
            return HybridEmbedderLayer(**kwargs)
        print(f"Attention! Input mode is not specified -> ft_mode = {ft_mode} | input_mode = {input_mode}")
        return OnehotEmbedderLayer(**kwargs)


class LstmInputMixin(models.Model):
    def __init__(self, *args, **kwargs) -> None:
        print(__class__)
        super(LstmInputMixin, self).__init__(*args, **kwargs)


class LSTMTokenInputMixin(LstmInputMixin):
    def __init__(self, vocab_len, max_len, feature_len, embed_dim, mask_zero=0, *args, **kwargs) -> None:
        print(__class__)
        super(LSTMTokenInputMixin, self).__init__(vocab_len=vocab_len, max_len=max_len, feature_len=feature_len, *args, **kwargs)
        self.in_layer = TokenInputLayer(max_len, feature_len)
        self.embedder = TokenEmbedderLayer(vocab_len, embed_dim, mask_zero)


class LSTMVectorInputMixin(LstmInputMixin):
    def __init__(self, vocab_len, max_len, feature_len, embed_dim, mask_zero=0, *args, **kwargs) -> None:
        print(__class__)
        super(LSTMVectorInputMixin, self).__init__(vocab_len=vocab_len, max_len=max_len, feature_len=feature_len, *args, **kwargs)
        self.in_layer = VectorInputLayer(max_len, feature_len)
        self.embedder = VectorEmbedderLayer(vocab_len, embed_dim, mask_zero)


class LSTMHybridInputMixin(LstmInputMixin):
    def __init__(self, vocab_len, max_len, feature_len, embed_dim, mask_zero=0, *args, **kwargs) -> None:
        print(__class__)
        super(LSTMHybridInputMixin, self).__init__(vocab_len=vocab_len, max_len=max_len, feature_len=feature_len, *args, **kwargs)
        self.in_layer = HybridInputLayer(max_len, feature_len)
        self.embedder = HybridEmbedderLayer(vocab_len, embed_dim, mask_zero)


class InputInterface(abc.ABC):
    @classmethod
    def summary(self):
        raise NotImplementedError()


class TokenInput(InputInterface):
    input_type = InputModeType.TOKEN_INPUT

    def summary(self):
        x = tf.keras.layers.Input(shape=(self.max_len, ))
        summarizer = models.Model(inputs=[x], outputs=self.call(x))
        return summarizer.summary()


class HybridInput(InputInterface):
    input_type = InputModeType.DUAL_INPUT

    def summary(self):
        events = tf.keras.layers.Input(shape=(self.max_len, ))
        features = tf.keras.layers.Input(shape=(self.max_len, self.feature_len))
        inputs = [events, features]
        summarizer = models.Model(inputs=[inputs], outputs=self.call(inputs))
        return summarizer.summary()


class VectorInput(InputInterface):
    input_type = InputModeType.VECTOR_INPUT

    def summary(self):
        x = tf.keras.layers.Input(shape=(self.max_len, self.feature_len))
        summarizer = models.Model(inputs=[x], outputs=self.call(x))
        return summarizer.summary()
