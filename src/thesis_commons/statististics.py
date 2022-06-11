from __future__ import annotations
from numbers import Number
from typing import Any, Callable, Dict, List, Mapping, Sequence, TypedDict

import pandas as pd
from numpy.typing import NDArray
from thesis_commons.functions import decode_sequences, decode_sequences_str, remove_padding

from thesis_commons.model_commons import GeneratorMixin
from thesis_commons.representations import Cases, EvaluatedCases
from thesis_viability.viability.viability_function import MeasureMask


# TODO: Move evolutionary statistics here
# TODO: Represent other statistics here: ViabilityMeasure, EvoluationaryStrategy, counterfactual Wrappers
class UpdateSet(TypedDict):
    model: GeneratorMixin
    results: Sequence[EvaluatedCases]
    measure_mask: MeasureMask


class ResultStatistics():
    def __init__(self, idx2vocab: Dict[int, str], pad_id: int = 0) -> None:
        self._data: Mapping[str, UpdateSet] = {}
        self._digested_data = None
        self.idx2vocab = idx2vocab
        self.pad_id = pad_id

    # num_generation, num_population, num_survivors, fitness_values
    def update(self, model: GeneratorMixin, data: Cases, measure_mask: MeasureMask = None):
        model = model.set_measure_mask(measure_mask)
        results = model.generate(data)
        self._data[model.name] = {"model": model, "results": results, 'measure_mask': model.measure_mask}
        return self

    def _digest(self):
        all_digested_results = [
            {
                **self._transform(dict_result),
                "mask": v['measure_mask'].to_binstr(),
                # **v['measure_mask'].to_dict(),
            } for k, v in self._data.items() for result in v["results"] for dict_result in result.to_dict_stream()
        ]

        cf_events = [item.pop('cf_events') for item in all_digested_results]
        fa_events = [item.pop('fa_events') for item in all_digested_results]

        cf_events_no_padding = remove_padding(cf_events, self.pad_id)
        fa_events_no_padding = remove_padding(fa_events, self.pad_id)

        cf_events_decoded = decode_sequences(cf_events_no_padding, self.idx2vocab)
        fa_events_decoded = decode_sequences(fa_events_no_padding, self.idx2vocab)

        all_results = [{**item, "cf_ev_str": cf, "fa_ev_str": fa} for item, cf, fa in zip(all_digested_results, cf_events_decoded, fa_events_decoded)]

        self._digested_data = pd.DataFrame(all_results)
        return self

    @property
    def data(self) -> pd.DataFrame:
        self._digest()
        return self._digested_data

    def _transform(self, result: Dict[str, Any]) -> Dict[str, Any]:

        return {
            "model_name": result.get("creator"),
            "instance_num": result.get("instance_num"),
            "rank": result.get("rank"),
            "likelihood": result.get("likelihood"),
            "outcome": result.get("outcome"),
            "viability": result.get("viability"),
            "sparcity": result.get("sparcity"),
            "similarity": result.get("similarity"),
            "dllh": result.get("dllh"),
            "ollh": result.get("ollh"),
            "cf_events": result.get("cf_events"),
            "fa_events": result.get("fa_events"),
        }

    def _add_global_vals(self, result: Dict[str, Any], mask_settings: Dict[str, bool]) -> Dict[str, NDArray]:

        return {**result, **mask_settings}

    def __repr__(self):
        return repr(self.data.groupby(["model_name", "instance_num"]).agg({'viability': ['mean', 'min', 'max', 'median'], 'likelihood': ['mean', 'min', 'max', 'median']}))


class RowData():
    def __init__(self) -> None:
        self.base_store = {}
        self.complex_store = {}
        self._digested_data = None
        self._combined_data = None

    # num_generation, num_population, num_survivors, fitness_values
    def update_base(self, stat_name: str, val: Number):
        self.base_store[stat_name] = val

    def update_complex(self, stat_name: str, val: Number, transform: Callable):
        self.complex_store[stat_name] = transform(val)

    def __repr__(self):
        dict_copy = dict(self.base_store)
        return f"@IterationStats[{repr(dict_copy)}]"

    def _digest(self) -> RowData:
        self._combined_data = {**self.base_store, **{stat_name: self.complex_store[stat_name] for stat_name in self.complex_store}}
        return self

    @property
    def data(self) -> pd.DataFrame:
        self._digest()
        return self._combined_data

class IterationData():
    
    def __init__(self,):
        self.store: Dict[int, RowData] = {}
        self._stats: List[Dict[str, Any]] = None
    
    def update(self, data_row:RowData) -> IterationData:
        self.store[len(self.store)] = data_row
    
    def _digest(self) -> IterationData:
        self._stats = [{"iteration":k, **v.data} for k, v in self.store.items()]
        return self
        
    @property
    def data(self) -> pd.DataFrame:
        return self._digest()._stats


class InstanceData():
    def __init__(self) -> None:
        self.store: Dict[int, IterationData] = {}
        self._stats: pd.DataFrame = None

    def update(self, iteration_data:IterationData) -> IterationData:
        self.store[len(self.store)] = iteration_data

    def _digest(self) -> IterationData:
        self._stats = [{"instance":k, **v.data} for k, v in self.store.items()]
        return self

    @property
    def data(self) -> pd.DataFrame:
        return self._digest()._stats


class RunData():
    def __init__(self) -> None:
        self.store: Dict[int, InstanceData] = {}
        self._stats: pd.DataFrame = None

    def update(self, instance_data:InstanceData) -> InstanceData:
        self.store[len(self.store)] = instance_data

    def _digest(self) -> InstanceData:
        self._stats = [{"run":k, **v.data} for k, v in self.store.items()]
        return self

    @property
    def data(self) -> pd.DataFrame:
        return self._digest()._stats


class ExperimentStatistics():
    def __init__(self, ):
        self._data: pd.DataFrame = pd.DataFrame()

    def update(self, mask_round: int, results_stats: ResultStatistics):
        temp_data = results_stats.data
        temp_data['mask_round'] = mask_round
        self._data = pd.concat([self._data, temp_data])
        return self

    @property
    def data(self):
        return self._data.reset_index()

    def __repr__(self):
        return repr(self._data)