import tensorflow as tf
from thesis_predictors.helper.evaluation import Evaluator
from thesis_predictors.helper.constants import EVAL_RESULTS_FOLDER, MODEL_FOLDER

from thesis_readers.readers.DomesticDeclarationsLogReader import DomesticDeclarationsLogReader
from ..helper.runner import Runner
from ..models.direct_data_lstm import FullLSTMModelOneWayExtensive, FullLSTMModelOneWaySimple
from ..models.lstm import SimpleLSTMModelOneWayExtensive, SimpleLSTMModelOneWaySimple, SimpleLSTMModelTwoWay
from ..models.seq2seq_lstm import SeqToSeqSimpleLSTMModelOneWay, SeqToSeqSimpleLSTMModelTwoWay
from ..models.transformer import Seq2SeqTransformerModelOneWay, TransformerModelOneWaySimple, TransformerModelTwoWay
from thesis_readers.helper.modes import FeatureModes, TaskModes
from thesis_readers import RequestForPaymentLogReader

if __name__ == "__main__":
    # Parameters
    results_folder = EVAL_RESULTS_FOLDER
    build_folder = MODEL_FOLDER
    prefix = "result_encdec"
    epochs = 10
    batch_size = 64
    adam_init = 0.01
    num_train = None
    num_val = None
    num_test = None    

    # Setup Reader and Evaluator
    task_mode = TaskModes.ENCODER_DECODER_PADDED
    reader = DomesticDeclarationsLogReader(debug=False, mode=task_mode)
    data = reader.init_log(save=True)
    reader = reader.init_data()
    evaluator = Evaluator(reader)


    r1 = Runner(
        reader,
        Seq2SeqTransformerModelOneWay(reader.vocab_len, reader.max_len, reader.feature_len),
        epochs,
        batch_size,
        adam_init,
        num_train=num_train,
        num_val=num_val,
        num_test=num_test,
        ft_mode=FeatureModes.EVENT_ONLY, # Make it part of the model
    ).train_model().evaluate(evaluator, results_folder, prefix)
    r1.save_model(build_folder, prefix)
