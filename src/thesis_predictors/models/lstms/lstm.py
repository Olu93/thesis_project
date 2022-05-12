from typing import ClassVar, Generic, Type, TypeVar
import tensorflow as tf
from thesis_commons.constants import REDUCTION
from thesis_commons.modes import TaskModeType
from thesis_commons.libcuts import layers, K, losses
import thesis_generators.models.model_commons as commons
# TODO: import thesis_commons.model_commons as commons
from thesis_commons import metric

physical_devices = tf.config.list_physical_devices('GPU')
tf.config.experimental.set_memory_growth(physical_devices[0], enable=True)
DEBUG_SHOW_ALL_METRICS = False
# TODO: Think of double stream LSTM: One for features and one for events.
# Both streams are dependendant on previous features and events.
# Requires very special loss that takes feature differences and event categorical loss into account
T = TypeVar("T", bound=commons.EmbedderLayer)


class BaseLSTM(commons.HybridInput, commons.TensorflowModelMixin):
    task_mode_type = TaskModeType.FIX2FIX

    def __init__(self, embed_dim=15, ff_dim=11, **kwargs):
        super(BaseLSTM, self).__init__(name=kwargs.pop("name", type(self).__name__), **kwargs)
        ft_mode = kwargs.pop('ft_mode')
        self.embed_dim = embed_dim
        self.ff_dim = ff_dim
        self.embedder = commons.EmbedderConstructor(ft_mode=ft_mode, vocab_len=self.vocab_len, embed_dim=self.embed_dim, mask_zero=0)
        self.lstm_layer = layers.LSTM(self.ff_dim, return_sequences=True)
        self.logit_layer = layers.TimeDistributed(layers.Dense(self.vocab_len))
        self.activation_layer = layers.Activation('softmax')
        self.custom_loss = metric.JoinedLoss([metric.MSpCatCE()]) 
        self.custom_eval = metric.JoinedLoss([metric.MSpCatAcc(), metric.MEditSimilarity()])

    def train_step(self, data):
        if len(data) == 3:
            (events_input, features_input), events_target, class_weight = data
        else:
            sample_weight = None
            (events_input, features_input), events_target = data

        with tf.GradientTape() as tape:
            x = self.embedder([events_input, features_input])
            y_pred = self.compute_input(x)
            sample_weight = self.max_len/K.sum(tf.cast(events_input!=0, dtype=tf.float64), axis=-1)[..., None]
            train_loss = self.custom_loss.call(events_target, y_pred, sample_weight=sample_weight*class_weight)
            # train_loss = K.sum(tf.cast(train_loss, tf.float64)*class_weight)

        trainable_weights = self.trainable_weights
        grads = tape.gradient(train_loss, trainable_weights)
        self.optimizer.apply_gradients(zip(grads, trainable_weights))

        _ = self.custom_eval.call(events_target, y_pred)
        trainer_losses = self.custom_loss.composites
        sanity_losses = self.custom_eval.composites
        losses = {}
        # if DEBUG_SHOW_ALL_METRICS:
        losses.update(trainer_losses)
        losses.update(sanity_losses)
        return losses

    # def test_step(self, data):
    #     # Unpack the data
    #     if len(data) == 3:
    #         (events_input, features_input), (events_target, features_target), sample_weight = data
    #     else:
    #         sample_weight = None
    #         (events_input, features_input), (events_target, features_target) = data  # Compute predictions
    #     x = self.embedder([events_input, features_input])
    #     z_mean, z_logvar = self.encoder(x)
    #     z_sample = self.sampler([z_mean, z_logvar])
    #     x_evs, x_fts = self.decoder(z_sample)
    #     vars = [x_evs, x_fts, z_sample, z_mean, z_logvar]  # rec_ev, rec_ft, z_sample, z_mean, z_logvar        # Updates the metrics tracking the loss
    #     eval_loss = self.custom_eval(data[1], vars)
    #     # Return a dict mapping metric names to current value.
    #     # Note that it will include the loss (tracked in self.metrics).
    #     losses = {}
    #     sanity_losses = self.custom_eval.composites
    #     sanity_losses["loss"] = 1 - sanity_losses["edit_distance"] + sanity_losses["feat_mape"]
    #     losses.update(sanity_losses)
    #     return losses

    def compile(self, optimizer=None, loss=None, metrics=None, loss_weights=None, weighted_metrics=None, run_eagerly=None, steps_per_execution=None, **kwargs):
        loss = loss or self.custom_loss
        # metrics = metrics or self.metric
        return super().compile(optimizer, loss, metrics, loss_weights, weighted_metrics, run_eagerly, steps_per_execution, **kwargs)

    def call(self, inputs):
        events, features = inputs
        embeddings = self.embedder(inputs)
        y_pred = self.compute_input(embeddings)
        return y_pred

    def compute_input(self, x):
        x = self.lstm_layer(x)
        if self.logit_layer is not None:
            x = self.logit_layer(x)
        y_pred = self.activation_layer(x)
        return y_pred


class SimpleLSTM(BaseLSTM):
    def __init__(self, **kwargs):
        super(SimpleLSTM, self).__init__(name=type(self).__name__, **kwargs)
        self.embedder = commons.TokenEmbedderLayer(self.vocab_len, self.embed_dim, mask_zero=0)

    def call(self, inputs):
        events, features = inputs
        ev_onehot = self.embedder(events)
        x = self.combiner([ev_onehot, features])
        y_pred = self.compute_input(x)
        return y_pred


class EmbeddingLSTM(BaseLSTM):
    def __init__(self, **kwargs):
        super(EmbeddingLSTM, self).__init__(name=type(self).__name__, **kwargs)
        self.embedder = commons.HybridEmbedderLayer(self.vocab_len, self.embed_dim, mask_zero=0)
        del self.combiner

    def call(self, inputs):
        x = self.embedder(inputs)
        y_pred = self.compute_input(x)
        return y_pred


class OutcomeLSTM(BaseLSTM):
    def __init__(self, **kwargs):
        super(OutcomeLSTM, self).__init__(name=type(self).__name__, **kwargs)
        self.lstm_layer = layers.LSTM(self.ff_dim)
        self.logit_layer = layers.Dense(1)
        self.activation_layer = layers.Activation('softmax')
        self.custom_loss = metric.JoinedLoss([metric.MSpOutcomeCE()])
        self.custom_eval = metric.JoinedLoss([metric.MSpOutcomeAcc()])

