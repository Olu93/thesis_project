from thesis_generators.models.vec2act_decoder import SimpleInterpretorModel
from thesis_generators.models.model_commons import HybridEmbedderLayer
from thesis_generators.models.joint_trainer import MultiTrainer
from thesis_generators.helper.wrapper import GenerativeDataset
from thesis_commons.modes import DatasetModes
from thesis_generators.models.vae.vae_lstm_adhoc import GeneratorVAEModel
from thesis_readers import MockReader as Reader
from thesis_commons.modes import TaskModes

if __name__ == "__main__":
    task_mode = TaskModes.NEXT_EVENT_EXTENSIVE
    epochs = 50
    bsize= 8
    reader = None
    reader = Reader(mode=task_mode).init_meta()
    generative_reader = GenerativeDataset(reader)
    train_data = generative_reader.get_dataset(bsize, DatasetModes.TRAIN)
    val_data = generative_reader.get_dataset(bsize, DatasetModes.VAL)

    model = MultiTrainer(
        Embedder=HybridEmbedderLayer,
        GeneratorModel=GeneratorVAEModel,
        InterpretorModel=SimpleInterpretorModel,
        embed_dim=10,
        ff_dim=10,
        vocab_len=generative_reader.vocab_len,
        max_len=generative_reader.max_len,
        feature_len=generative_reader.current_feature_len,
    )

    model.compile(run_eagerly=True)
    x_pred, y_true = next(iter(train_data))
    y_pred = model(x_pred)
    model.summary()
    # model.fit(training_data[0], training_data[1])
    # loss_fn = VAELoss()
    # loss = loss_fn(y_true, y_pred)
    model.fit(train_data, validation_data=val_data, epochs=epochs)
    # tf.stack([tf.cast(tmp[0][:,1], tf.int32),tmp[1]], axis=1)
    print("stuff")
    # TODO: NEEDS BILSTM