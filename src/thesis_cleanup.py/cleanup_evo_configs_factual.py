# %%
import glob
import io
import pathlib
import os
from thesis_commons.constants import PATH_RESULTS_MODELS_OVERALL, PATH_RESULTS_MODELS_SPECIFIC
import pandas as pd
# %%
config_name = "evolutionary_configs_factual"
all_directories = glob.glob(str((PATH_RESULTS_MODELS_SPECIFIC/ config_name /"EvoGeneratorWrapper/*.csv").absolute()))
all_csvs = []
for directory in all_directories:
    dirpath = pathlib.Path(directory)
    df = pd.read_csv(directory)
    filename = dirpath.name
    wrapper_type = dirpath.parent.name
    experiment_name = dirpath.parent.parent.name 
    df["filename"] = filename
    df["wrapper_type"] = wrapper_type
    df["experiment_name"] = experiment_name
    all_csvs.append(df)
# %%    
major_df = pd.concat(all_csvs)
major_df.to_csv(PATH_RESULTS_MODELS_SPECIFIC/ f"grouped_{config_name}_specifics.csv")    
print(major_df)
