from thesis_readers import MockReader as Reader
from thesis_commons.constants import PATH_MODELS_GENERATORS
from thesis_commons.callbacks import CallbackCollection
from thesis_generators.helper.wrapper import GenerativeDataset
from thesis_commons.modes import DatasetModes, GeneratorModes, TaskModes
from thesis_generators.models.encdec_vae.vae_seq2seq import SimpleGeneratorModel as GModel

if __name__ == "__main__":
    task_mode = TaskModes.NEXT_EVENT_EXTENSIVE
    epochs = 50
    reader = None
    reader = Reader(mode=task_mode).init_meta()
    generative_reader = GenerativeDataset(reader)
    train_data = generative_reader.get_dataset(20, DatasetModes.TRAIN, gen_mode=GeneratorModes.HYBRID, flipped_target=True)
    val_data = generative_reader.get_dataset(20, DatasetModes.VAL, gen_mode=GeneratorModes.HYBRID, flipped_target=True)

    DEBUG = True
    model = GModel(
        embed_dim=12,
        ff_dim=5,
        vocab_len=generative_reader.vocab_len,
        max_len=generative_reader.max_len,
        feature_len=generative_reader.current_feature_len,
    )

    model.compile(run_eagerly=DEBUG)
    x_pred, y_true = next(iter(train_data))
    y_pred = model(x_pred)
    model.summary()
    model.fit(train_data, validation_data=val_data, epochs=epochs, callbacks=CallbackCollection(model.name, PATH_MODELS_GENERATORS, DEBUG).build())
    print("stuff")
    # TODO: NEEDS BILSTM
