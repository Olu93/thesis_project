from __future__ import annotations
from abc import ABC, abstractmethod
import itertools as it
from typing import TYPE_CHECKING, Callable, List, Tuple, Any, Dict, Sequence, Tuple, TypedDict

from thesis_commons.functions import sliding_window
from thesis_commons.random import matrix_sample
from thesis_commons.representations import BetterDict, Cases, ConfigurableMixin, ConfigurationSet
if TYPE_CHECKING:
    pass

from collections import Counter, defaultdict
from ctypes import Union
from enum import IntEnum, auto

import numpy as np
import pandas as pd
import scipy.stats as stats
from numpy.typing import NDArray
from numpy.linalg import LinAlgError
from scipy.stats._multivariate import \
    multivariate_normal_frozen as MultivariateNormal

EPS = np.finfo(float).eps


class ResultTransitionProb():
    def __init__(self, seq_probs: NDArray):
        self.pnt_p = seq_probs
        self.pnt_log_p = np.log(self.pnt_p + EPS)
        # self.seq_log_p = self.pnt_log_p.cumsum(-1)
        # self.seq_p = np.exp(self.pnt_log_p)
        # self.jnt_pnt_p = self.pnt_p.prod(-1)
        # self.jnt_pnt_log_p = self.pnt_log_p.sum(-1)
        # self.jnt_seq_p = self.seq_p.prod(-1)
        # self.jnt_seq_log_p = self.seq_log_p.sum(-1)


class ProbabilityMixin:
    def set_vocab_len(self, vocab_len: int) -> TransitionProbability:
        self.vocab_len = vocab_len
        return self

    def set_max_len(self, max_len: int) -> TransitionProbability:
        self.max_len = max_len
        return self

    def set_data(self, cases: Cases) -> TransitionProbability:
        self.events = cases.events
        self.features = cases.features
        return self


class TransitionProbability(ProbabilityMixin, ABC):
    def compute_probs(self, events, logdomain=False, joint=False, cummulative=True, **kwargs) -> NDArray:
        res = ResultTransitionProb(self._compute_p_seq(events, **kwargs))
        result = res.pnt_log_p
        if not (cummulative or joint or logdomain):
            return np.exp(result)
        result = np.cumsum(result, -1) if cummulative else result
        result = np.sum(result, -1) if joint else result
        result = result if logdomain else np.exp(result)
        return result

    @abstractmethod
    def init(self, events, **kwargs):
        pass

    @abstractmethod
    def _compute_p_seq(self, events: NDArray) -> NDArray:
        return None

    @abstractmethod
    def extract_transitions_probs(self, num_events: int, flat_transistions: NDArray) -> NDArray:
        pass

    @abstractmethod
    def extract_transitions(self, events: NDArray) -> NDArray:
        pass

    @abstractmethod
    def sample(self, sample_size: int) -> NDArray:
        pass

    @abstractmethod
    def __call__(self, xt: NDArray, xt_prev: NDArray) -> NDArray:
        pass


class DistParams(ABC):
    def __init__(self, data: pd.DataFrame, support: NDArray, key: Any = None):
        self.data = None
        self.support = None
        self.key = None
        self.init(data, support, key)

    @abstractmethod
    def init(self, data: pd.DataFrame, support: int, key: str):
        pass
    
    @abstractmethod
    def __len__(self) -> int:
        pass


class GaussianParams(DistParams):
    def __init__(self, data: pd.DataFrame, support: NDArray, key: Any = None):
        self.init(data, support, key)

    def init(self, data: pd.DataFrame, support: int, key: str):
        self._mean: NDArray = data.mean().values
        self._cov: NDArray = data.cov().values if support != 1 else np.zeros_like(data.cov())
        self.support: int = 0
        self.key = key
        self.cov_mask = self.compute_cov_mask(self._cov)
        self.support = support

    def compute_cov_mask(self, cov: NDArray) -> NDArray:
        row_sums = cov.sum(0)[None, ...] == 0
        col_sums = cov.sum(1)[None, ...] == 0
        masking_pos = ~((row_sums).T | (col_sums))
        return masking_pos

    def set_cov(self, cov: NDArray) -> GaussianParams:
        self._cov = cov
        return self

    def set_mean(self, mean: NDArray) -> GaussianParams:
        self._mean = mean
        return self

    def set_support(self, support: int) -> GaussianParams:
        self.support = support
        return self

    def __len__(self) -> int:
        return len(self._cov)

    def __repr__(self) -> str:
        return f"@GaussianParams[len={self.support}]"

    @property
    def dim(self) -> int:
        return self.mean.shape[0]

    @property
    def cov(self) -> NDArray:
        d = self.dim
        return self._cov[self.cov_mask].reshape((d, d))

    @property
    def mean(self) -> NDArray:
        return self._mean[np.diag(self.cov_mask)]


class IndependentGaussianParams(GaussianParams):
    def init(self, data: pd.DataFrame, support: int, key: str):
        self._mean: NDArray = data.mean().values
        self._cov: NDArray = data.cov().values * np.eye(*data.cov().shape) if support != 1 else np.zeros_like(data.cov())
        self.support: int = 0
        self.key = key
        self.cov_mask = self.compute_cov_mask(self._cov)
        self.support = support


class ApproximationLevel():
    def __init__(self, is_eps: int, approx_type: int):
        self.eps_type = is_eps
        self.approx_type = approx_type
        self._mapping_eps = {
            0: "EPS_FALSE",
            1: "EPS_TRUE",
            2: "NONE",
        }
        self._mapping_apprx = {
            0: "DEFAULT",
            1: "FILL",
            2: "SAMPLE",
            3: "ONLY_MEAN",
            4: "LAST_RESORT",
            5: "ALLOW_DEGNRT",
        }
        self._justification_eps = max([len(s) for s in self._mapping_eps.values()])
        self._justification_apprx = max([len(s) for s in self._mapping_apprx.values()])

    def __repr__(self):
        eps_string = self._mapping_eps.get(self.eps_type, "UNDEFINED")
        approx_string = self._mapping_apprx.get(self.approx_type, "UNDEFINED")
        # https://www.geeksforgeeks.org/pad-or-fill-a-string-by-a-variable-in-python-using-f-string/
        return f"{self.eps_type}{self.approx_type}_{eps_string:_<{self._justification_eps}}_{approx_string:<{self._justification_apprx}}"


class FallbackableException(Exception):
    def __init__(self, e: Exception) -> None:
        super().__init__(*e.args)


class Dist:
    def __init__(self, params: DistParams, fallback_params: DistParams = None, eps: float = None):
        self.event = params.key
        self.params = params
        self.fallback_params = fallback_params
        self.eps = eps


class ApproximateMultivariateNormal(Dist):
    def __init__(self, params: GaussianParams, fallback_params: GaussianParams = None, eps: float = None):
        super().__init__(params, fallback_params, eps)
        self.cov_mask = params.cov_mask
        self.feature_len = len(params.cov_mask)
        self.dist, self.approximation_level = self.init_dists(self.params, self.fallback_params, self.eps)

    def init_dists(self, params: GaussianParams, fallback_params: GaussianParams, eps: float) -> Tuple[MultivariateNormal, ApproximationLevel]:
        dist = None
        str_event = f"Event {self.event:02d}"
        dim = params.dim

        if dim == 0:
            i = 2
            j = 5
            dist = stats.multivariate_normal(params._mean, params._cov, allow_singular=True)
            state, is_error, str_result = self._process_dist_result(dist, str_event, i, j)
            print(str_result)
            if not is_error:
                return dist, state

        cov = params.cov
        mean = params.mean
        no_eps = np.zeros_like(cov)
        diagonal_eps = np.identity(dim) * eps
        everywhere_eps = np.ones_like(cov) * eps
        for i, eps in enumerate([no_eps, diagonal_eps, everywhere_eps]):
            cov_unchanged = params.cov + eps
            # cov_filled = np.where(cov == 0, fallback_params.cov, cov) + eps
            # for j, cov in enumerate([cov_unchanged, cov_filled]):
            for j, cov in enumerate([cov_unchanged]):
                dist = self._create_multivariate(mean, cov)
                state, is_error, str_result = self._process_dist_result(dist, str_event, i, j)
                print(str_result)
                if not is_error:
                    return dist, state

        state = ApproximationLevel(2, 4)
        print(f"WARNING {str_event}: Could not any approx for event {self.event} -- {state}")
        return stats.multivariate_normal(np.zeros_like(params.mean)), state

    def rvs(self, size: int) -> NDArray:
        return self.dist.rvs(size)

    def _process_dist_result(self, dist, str_event, i, j):
        state = ApproximationLevel(i, j)
        is_error = (type(dist) == FallbackableException)
        str_result = f"WARNING {str_event}: {state} -- Could not create because {dist}" if is_error else f"SUCCESS {str_event}: {state}"
        return state, is_error, str_result

    def _create_multivariate(self, mean: NDArray, cov: NDArray) -> Union[FallbackableException, MultivariateNormal]:

        try:
            return stats.multivariate_normal(mean, cov)
        except LinAlgError as e:
            return FallbackableException(e)
        except ValueError as e:
            if e.args[0] == "the input matrix must be positive semidefinite":
                return FallbackableException(e)
            else:
                raise e

    def pdf(self, x: NDArray) -> NDArray:
        if self.params.dim == 0:
            return self.dist.pdf(x)
        variables = np.diag(self.params.cov_mask)
        constants = ~variables
        const_mean = self.params._mean[constants]

        x_variables = x[:, variables]
        x_constants = x[:, constants]

        probs = self.dist.pdf(x_variables)
        # Checks if all follow exact constant distribution. Otherwise it's a violation and thus 0 probability.
        close_to_mean = np.isclose(const_mean[None], x_constants)
        not_deviating = np.all(close_to_mean, axis=1)

        # Multiplies whether constant was hit for each case and then returning their probability
        return probs * not_deviating

    def rvs(self, size=1) -> NDArray:
        if self.params.dim == 0:
            return self.dist.rvs(size)
        variables = np.diag(self.params.cov_mask)
        constants = ~variables
        const_mean = self.params._mean[constants]

        result = np.zeros((size, len(np.diag(self.cov_mask))))
        samples = self.dist.rvs(size)

        result[:, variables] = samples
        result[:, constants] = const_mean

        return result

    @property
    def mean(self):
        return self.dist.mean

    @property
    def cov(self):
        return self.dist.cov

    def __repr__(self):
        return f"@{type(self).__name__}[Fallback {self.approximation_level} - Mean: {self.mean}]"


class NoneExistingMultivariateNormal(ApproximateMultivariateNormal):
    def __init__(self, params: GaussianParams = None, fallback_params: GaussianParams = None, eps: float = None):
        self.approximation_level = ApproximationLevel(-1, -1)

    def pdf(self, x: NDArray):
        return np.zeros((len(x), ))

    @property
    def mean(self):
        return None

    @property
    def cov(self):
        return None


# class MixedParams():
#     def __init__(self, params:List[DistParams], support: NDArray,  key: Any = None):
#         self._mean: NDArray = None
#         self._cov: NDArray = None
#         self.support: int = 0
#         self.key = key
#         self._mean = mean
#         self._cov = cov if support != 1 else np.zeros_like(cov)
#         self.cov_mask = self.compute_cov_mask(self._cov)
#         self.support = support


class PFeaturesGivenActivity():
    def __init__(self, all_dists: Dict[int, DistParams]):
        self.all_dists = all_dists
        self.none_existing_dists = NoneExistingMultivariateNormal()
        self.feature_len: int = self.all_dists[0].feature_len

    def __getitem__(self, key) -> DistParams:
        if key in self.all_dists:
            return self.all_dists.get(key)
        else:
            return self.none_existing_dists

    def __repr__(self):
        return f"@{type(self).__name__}{self.all_dists}"


class UnigramTransitionProbability(TransitionProbability):
    def init(self):
        events_slided = sliding_window(self.events, 2)
        self.trans_count_matrix: NDArray = np.zeros((self.vocab_len, self.vocab_len))
        self.trans_probs_matrix: NDArray = np.zeros((self.vocab_len, self.vocab_len))

        self.df_tra_counts = pd.DataFrame(events_slided.reshape((-1, 2)).tolist()).value_counts()
        self.trans_idxs = np.array(self.df_tra_counts.index.tolist(), dtype=int)
        self.trans_from = self.trans_idxs[:, 0]
        self.trans_to = self.trans_idxs[:, 1]
        self.trans_counts = np.array(self.df_tra_counts.values.tolist(), dtype=int)
        self.trans_count_matrix[self.trans_from, self.trans_to] = self.trans_counts
        self.trans_probs_matrix = self.trans_count_matrix / self.trans_count_matrix.sum(axis=1, keepdims=True)
        self.trans_probs_matrix[np.isnan(self.trans_probs_matrix)] = 0

        self.start_count_matrix = np.zeros((self.vocab_len, 1))
        self.start_events = self.events[:, 0]
        self.start_counts_counter = Counter(self.start_events)
        self.start_indices = np.array(list(self.start_counts_counter.keys()), dtype=int)
        self.start_counts = np.array(list(self.start_counts_counter.values()), dtype=int)
        self.start_count_matrix[self.start_indices, 0] = self.start_counts
        self.start_probs = self.start_count_matrix / self.start_counts.sum()

    def _compute_p_seq(self, events: NDArray) -> NDArray:
        flat_transistions = self.extract_transitions(events)
        probs = self.extract_transitions_probs(events.shape[0], flat_transistions)
        start_events = np.array(list(events[:, 0]), dtype=int)
        start_event_prob = self.start_probs[start_events, 0, None]
        return np.hstack([start_event_prob, probs])

    def extract_transitions_probs(self, num_events: int, flat_transistions: NDArray) -> NDArray:
        t_from = flat_transistions[:, 0]
        t_to = flat_transistions[:, 1]
        probs = self.trans_probs_matrix[t_from, t_to].reshape(num_events, -1)
        return probs

    def extract_transitions(self, events: NDArray) -> NDArray:
        events_slided = sliding_window(events, 2)
        events_slided_flat = events_slided.reshape((-1, 2))
        transistions = np.array(events_slided_flat.tolist(), dtype=int)
        return transistions

    def sample(self, sample_size: int) -> NDArray:
        # https://stackoverflow.com/a/40475357/4162265
        result = np.zeros((sample_size, self.max_len))
        pos_probs = np.repeat(self.start_probs.T, sample_size, axis=0)
        order_matrix = np.ones((sample_size, self.vocab_len)) * np.arange(0, self.vocab_len)[None]

        for curr_pos in range(self.max_len):
            starting_events = matrix_sample(pos_probs)
            result[..., curr_pos] = starting_events[..., 0]
            pos_matrix = (order_matrix == starting_events) * 1
            pos_probs = pos_matrix @ self.trans_probs_matrix
        return result

    def __call__(self, xt: NDArray, xt_prev: NDArray) -> NDArray:
        probs = self.trans_probs_matrix[xt_prev, xt]
        return probs


# class FaithfulEmissionProbability(ProbabilityMixin, ABC):


class EmissionProbability(ProbabilityMixin, ABC):
    def init(self):
        num_seq, seq_len, num_features = self.features.shape
        self.eps = 0.1
        self.events = self.events
        self.features = self.features
        events_flat = self.events.reshape((-1, ))
        features_flat = self.features.reshape((-1, num_features))
        sort_indices = events_flat.argsort()
        events_sorted = events_flat[sort_indices]
        features_sorted = features_flat[sort_indices]
        self.df_ev_and_ft: pd.DataFrame = pd.DataFrame(features_sorted)
        self.data_groups: Dict[int, pd.DataFrame] = {}
        self.df_ev_and_ft["event"] = events_sorted.astype(int)
        self.data_groups, self.dist_params, self.dists = self.estimate_params()

    def set_eps(self, eps=1) -> EmissionProbability:
        self.eps = eps
        return self

    def set_data_mapping(self, data_mapping: Dict) -> EmissionProbability:
        self.data_mapping = data_mapping
        return self

    def compute_probs(self, events: NDArray, features: NDArray, is_log=False) -> NDArray:
        num_seq, seq_len, num_features = features.shape
        events_flat = events.reshape((-1, )).astype(int)
        features_flat = features.reshape((-1, num_features))
        unique_events = np.unique(events_flat)
        emission_probs = np.zeros_like(events_flat, dtype=float)
        for ev in unique_events:
            # https://stats.stackexchange.com/a/331324
            ev_pos = events_flat == ev
            # if ev == 37: DELETE
            #     print("STOP")
            distribution = self.dists[ev]
            emission_probs[ev_pos] = distribution.pdf(features_flat[ev_pos])
            # distribution = self.gaussian_dists[ev]
            # emission_probs[ev_pos] = distribution.pdf(features_flat[ev_pos])

        result = emission_probs.reshape((num_seq, -1))
        return np.log(result) if is_log else result

    def estimate_params(self) -> Tuple[Dict[int, pd.DataFrame], Dict[int, DistParams], PFeaturesGivenActivity]:
        data = self.df_ev_and_ft.drop('event', axis=1)
        fallback = self.extract_fallback_params(data)
        data_groups = self.extract_data_groups(self.df_ev_and_ft)
        params = self.extract_params(data_groups)
        dists = self.extract_dists(params, fallback, self.eps)

        return data_groups, params, dists

    def extract_data_groups(self, dataset: pd.DataFrame) -> Dict[int, pd.DataFrame]:
        return {key: data.loc[:, data.columns != 'event'] for (key, data) in dataset.groupby("event")}

    @abstractmethod
    def extract_fallback_params(self, data: pd.DataFrame):
        pass

    @abstractmethod
    def extract_params(self, data_groups: Dict[int, pd.DataFrame]) -> Dict[int, DistParams]:
        pass

    def extract_dists(self, params: Dict[int, GaussianParams], fallback: GaussianParams, eps: float):
        return PFeaturesGivenActivity({activity: ApproximateMultivariateNormal(data, fallback, eps) for activity, data in params.items()})

    def sample(self, events: NDArray) -> NDArray:
        num_seq, seq_len = events.shape
        feature_len = self.dists[0].feature_len
        events_flat = events.reshape((-1, )).astype(int)
        unique_events = np.unique(events_flat)
        features = np.zeros((events_flat.shape[0], feature_len), dtype=float)
        for ev in unique_events:
            # https://stats.stackexchange.com/a/331324
            ev_pos = events_flat == ev
            # if ev == 37: DELETE
            #     print("STOP")
            distribution = self.dists[ev]
            features[ev_pos] = distribution.rvs(size=ev_pos.sum())
        result = features.reshape((num_seq, seq_len, -1))
        return result


class EmissionProbabilityIndependentGaussianFeatures(EmissionProbability):
    def extract_fallback_params(self, data: pd.DataFrame):
        fallback = IndependentGaussianParams(data, len(data))
        return fallback

    def extract_params(self, data_groups: Dict[int, pd.DataFrame]) -> Dict[int, DistParams]:
        return {activity: IndependentGaussianParams(data, len(data), activity) for activity, data in data_groups.items()}


class EmissionProbabilityGaussianFeatures(EmissionProbability):
    def extract_fallback_params(self, data: pd.DataFrame):
        fallback = GaussianParams(data, len(data))
        return fallback

    def extract_params(self, data_groups: Dict[int, pd.DataFrame]) -> Dict[int, DistParams]:
        return {activity: GaussianParams(data, len(data), activity) for activity, data in data_groups.items()}


class FaithfulEmissionProbability(EmissionProbability):
    def extract_fallback_params(self, data) -> GaussianParams:
        params = super().extract_fallback_params(data)
        return params.set_cov(params.cov * np.eye(*params.cov.shape))


class DistributionConfig(ConfigurationSet):
    def __init__(
        self,
        tprobs: TransitionProbability,
        eprobs: EmissionProbability,
    ):
        self.tprobs = tprobs
        self.eprobs = eprobs
        self._list: List[DistributionConfig] = [tprobs, eprobs]

    @staticmethod
    def registry(tprobs: List[TransitionProbability] = None, eprobs: List[EmissionProbability] = None, **kwargs) -> DistributionConfig:
        tprobs = tprobs or [UnigramTransitionProbability()]
        eprobs = eprobs or [EmissionProbabilityIndependentGaussianFeatures()]
        combos = it.product(tprobs, eprobs)
        result = [DistributionConfig(*cnf) for cnf in combos]
        return result

    def set_vocab_len(self, vocab_len: int, **kwargs) -> DistributionConfig:
        for distribution in self._list:
            distribution.set_vocab_len(vocab_len)
        return self

    def set_max_len(self, max_len: int, **kwargs) -> DistributionConfig:
        for distribution in self._list:
            distribution.set_max_len(max_len)
        return self

    def set_data(self, data: Cases, **kwargs) -> DistributionConfig:
        for distribution in self._list:
            distribution.set_data(data)
        return self

    def init(self, **kwargs) -> DistributionConfig:
        for distribution in self._list:
            distribution.init(**kwargs)
        return self


class DataDistribution(ConfigurableMixin):
    def __init__(self, data: Cases, vocab_len: int, max_len: int, data_mapping: Dict = None, config: DistributionConfig = None):
        events, features = data.cases
        self.events = events
        self.features = features
        self.vocab_len = vocab_len
        self.max_len = max_len
        self.data_mapping = data_mapping
        self.config = config.set_data(data)
        self.tprobs = self.config.tprobs
        self.eprobs = self.config.eprobs

    def init(self) -> DataDistribution:
        self.config = self.config.set_vocab_len(self.vocab_len).set_max_len(self.max_len).init()
        return self

    def pdf(self, data: Cases) -> Tuple[NDArray, NDArray]:
        events, features = data.cases
        transition_probs = self.tprobs.compute_probs(events)
        emission_probs = self.eprobs.compute_probs(events, features, is_log=False)
        return transition_probs, emission_probs

    def sample(self, size: int = 1) -> Cases:
        sampled_ev = self.tprobs.sample(size)
        sampled_ft = self.eprobs.sample(sampled_ev)
        return Cases(sampled_ev, sampled_ft)

    def get_config(self) -> BetterDict:
        return super().get_config()
