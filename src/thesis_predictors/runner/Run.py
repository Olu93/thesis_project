import tensorflow as tf
from thesis_predictors.helper.constants import EVAL_RESULTS_FOLDER, MODEL_FOLDER

from thesis_readers.readers.DomesticDeclarationsLogReader import DomesticDeclarationsLogReader
from ..helper.runner import Runner
from ..helper.metrics import CrossEntropyLoss, CrossEntropyLossModified, SparseAccuracyMetric, SparseCrossEntropyLoss
from ..models.direct_data_lstm import FullLSTMModelOneWay
from ..models.lstm import SimpleLSTMModelOneWay, SimpleLSTMModelTwoWay
from ..models.seq2seq_lstm import SeqToSeqLSTMModelOneWay
from ..models.transformer import TransformerModelOneWay, TransformerModelTwoWay
from thesis_readers.readers.AbstractProcessLogReader import FeatureModes, TaskModes
from thesis_readers import RequestForPaymentLogReader

if __name__ == "__main__":
    reader = DomesticDeclarationsLogReader(debug=False, mode=TaskModes.NEXT_EVENT_EXTENSIVE)
    # data = data.init_log(save=True)
    reader = reader.init_data()
    results_folder = EVAL_RESULTS_FOLDER
    build_folder = MODEL_FOLDER
    prefix = "result"
    epochs = 5
    batch_size = 64
    adam_init = 0.001
    num_train = None
    num_val = None
    num_test = None    
    loss_fn = SparseCrossEntropyLoss()
    metric = SparseAccuracyMetric()
    r1 = Runner(
        reader,
        FullLSTMModelOneWay(reader.vocab_len, reader.max_len, reader.feature_len - 1),
        epochs,
        batch_size,
        adam_init,
        num_train=num_train,
        num_val=num_val,
        num_test=num_test,
        ft_mode=FeatureModes.FULL_SEP,
    ).train_model(loss_fn, [metric]).evaluate(results_folder, prefix)
    r1.save_model(build_folder, prefix)
    r3 = Runner(
        reader,
        SimpleLSTMModelOneWay(reader.vocab_len, reader.max_len),
        epochs,
        batch_size,
        adam_init,
        num_train=num_train,
        num_val=num_val,
        num_test=num_test,
        ft_mode=FeatureModes.EVENT_ONLY,
    ).train_model(loss_fn, [metric]).evaluate(results_folder, prefix)
    r3.save_model(build_folder, prefix)
    r5 = Runner(
        reader,
        TransformerModelOneWay(reader.vocab_len, reader.max_len),
        epochs,
        batch_size,
        adam_init,
        num_train=num_train,
        num_val=num_val,
        num_test=num_test,
        ft_mode=FeatureModes.EVENT_ONLY,
    ).train_model(loss_fn, [metric]).evaluate(results_folder, prefix)
    r5.save_model(build_folder, prefix)
