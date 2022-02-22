from thesis_readers import DomesticDeclarationsLogReader as Reader
from thesis_generators.helper.wrapper import GenerativeDataset
from thesis_commons.constants import PATH_MODELS_GENERATORS
from thesis_commons.callbacks import CallbackCollection
from thesis_generators.models.vec2act_decoder import SimpleInterpretorModel
from thesis_generators.models.model_commons import HybridEmbedderLayer
from thesis_generators.models.joint_trainer import MultiTrainer
from thesis_generators.helper.wrapper import GenerativeDataset
from thesis_commons.modes import DatasetModes
from thesis_generators.models.vae.vae_simple import SimpleSeqVAEGeneratorModel
from thesis_generators.models.vae.vae_dmm_stepwise import DMMModel
from thesis_commons.modes import TaskModes

if __name__ == "__main__":
    task_mode = TaskModes.NEXT_EVENT_EXTENSIVE
    epochs = 50
    reader = None
    reader = Reader(mode=task_mode).init_meta()
    generative_reader = GenerativeDataset(reader)
    train_data = generative_reader.get_dataset(16, DatasetModes.TRAIN)
    val_data = generative_reader.get_dataset(16, DatasetModes.VAL)
    
    DEBUG = True
    # model = MultiTrainer(
    #     Embedder=HybridEmbedderLayer,
    #     GeneratorModel=SimpleSeqVAEGeneratorModel,
    #     InterpretorModel=SimpleInterpretorModel,
    #     embed_dim=10,
    #     ff_dim=10,
    #     vocab_len=generative_reader.vocab_len,
    #     max_len=generative_reader.max_len,
    #     feature_len=generative_reader.current_feature_len,
    # )
    model = DMMModel(
        embed_dim=10,
        ff_dim=10,
        vocab_len=generative_reader.vocab_len,
        max_len=generative_reader.max_len,
        feature_len=generative_reader.current_feature_len,
    )
    model.compile(run_eagerly=DEBUG)
    x_pred, y_true = next(iter(train_data))
    y_pred = model(x_pred)
    model.summary()
    # model.fit(training_data[0], training_data[1])
    # loss_fn = VAELoss()
    # loss = loss_fn(y_true, y_pred)
    model.fit(train_data, validation_data=val_data, epochs=epochs, callbacks=CallbackCollection(model.name, PATH_MODELS_GENERATORS, DEBUG).build())
    # tf.stack([tf.cast(tmp[0][:,1], tf.int32),tmp[1]], axis=1)
    print("stuff")
    # TODO: NEEDS BILSTM
