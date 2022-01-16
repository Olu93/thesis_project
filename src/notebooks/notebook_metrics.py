# %%
import tensorflow as tf
import tensorflow.keras as keras
from tensorflow.keras import layers
import numpy as np
from tensorflow.python.keras.utils import losses_utils

y_true = tf.constant([[1, 2, 1, 0, 0], [1, 2, 1, 1, 0], [1, 2, 1, 1, 2], [1, 2, 0, 0, 0]], dtype=tf.float32)
y_pred = tf.constant(
    [
        [
            [0.04, 0.95, 0.01],
            [0.10, 0.10, 0.80],
            [0.20, 0.70, 0.10],
            [0.20, 0.10, 0.70],
            [0.90, 0.00, 0.10],
        ],
        [
            [0.04, 0.01, 0.95],
            [0.10, 0.10, 0.80],
            [0.95, 0.03, 0.02],
            [0.90, 0.05, 0.05],
            [0.90, 0.00, 0.10],
        ],
        [
            [0.95, 0.04, 0.01],
            [0.10, 0.80, 0.10],
            [0.95, 0.03, 0.02],
            [0.90, 0.05, 0.05],
            [0.90, 0.00, 0.10],
        ],
        [
            [0.95, 0.04, 0.01],
            [0.10, 0.80, 0.10],
            [0.05, 0.93, 0.02],
            [0.90, 0.05, 0.05],
            [0.90, 0.00, 0.10],
        ],
    ],
    dtype=tf.float32,
)
print(y_true.shape)
print(y_pred.shape)

# %%
cce = tf.keras.losses.SparseCategoricalCrossentropy(from_logits=False, reduction=losses_utils.ReductionV2.AUTO)
print(cce(y_true, y_pred).numpy())
print(tf.keras.losses.sparse_categorical_crossentropy(y_true, y_pred, from_logits=False))


# %%
class EditDistanceLoss(keras.losses.Loss):
    """
    Args:
      reduction: Type of tf.keras.losses.Reduction to apply to loss.
      name: Name of the loss function.
    """
    def __init__(self, reduction=keras.losses.Reduction.AUTO):
        super().__init__(reduction=reduction)
        self.loss = tf.keras.losses.SparseCategoricalCrossentropy()

    def call(self, y_true, y_pred):
        y_true_end = tf.argmax(tf.cast(tf.equal(y_true, 0), tf.float32), axis=-1)
        y_pred_end = tf.argmax(tf.equal(tf.argmax(y_pred, axis=-1), 0), axis=-1)

        result = self.loss(y_true, y_pred)
        return result

class EditDistanceMetric(tf.keras.metrics.Metric):
    def __init__(self, **kwargs):
        super(EditDistanceMetric, self).__init__(**kwargs)
        self.acc_value = tf.constant(0)

    def update_state(self, y_true, y_pred, sample_weight=None):
        # y_true = tf.cast(y_true[0], tf.int32)
        # y_pred = tf.cast(y_pred, tf.int32)
        hypothesis = tf.cast(tf.argmax(y_pred, -1), tf.int64)
        tf.print(hypothesis)
        truth =  tf.cast(y_true, tf.int64)
        tf.print(truth)
        edit_distance = tf.edit_distance(tf.sparse.from_dense(hypothesis),tf.sparse.from_dense(truth))
        self.acc_value = tf.reduce_mean(edit_distance)

    def result(self):
        return self.acc_value

    def reset_states(self):
        self.acc_value = tf.constant(0)

    def get_config(self):
        return super().get_config()

    @classmethod
    def from_config(cls, config):
        return cls(**config)


cce = EditDistanceMetric()
cce(tf.constant(y_true), tf.constant(y_pred))

# %%
