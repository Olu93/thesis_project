from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Tuple, Any, Dict, Sequence, Tuple, TypedDict
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


class GaussianParams():
    _mean: NDArray = None
    _cov: NDArray = None
    support: int = 0

    def __init__(self, mean: NDArray, cov: NDArray, support: NDArray, key: Any = None):
        self.key = key
        self._mean = mean
        self._cov = cov if support != 1 else np.zeros_like(cov)
        self.cov_mask = self.compute_cov_mask(self._cov)
        self.support = support
        # self._dim = self.mean.shape[0]

    def compute_cov_mask(self, cov: NDArray) -> NDArray:
        row_sums = cov.sum(0)[None,...] == 0
        col_sums = cov.sum(1)[None,...] == 0
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

    def __repr__(self) -> str:
        return f"@GaussianParams[len={self.support}]"

    @property
    def dim(self) -> int:
        return self.mean.shape[0]

    @property
    def cov(self) -> NDArray:
        d = self.dim
        return self._cov[self.cov_mask].reshape((d,d))

    @property
    def mean(self) -> NDArray:
        return self._mean[np.diag(self.cov_mask)]

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


class ApproximateMultivariateNormal():
    class FallbackableException(Exception):
        def __init__(self, e: Exception) -> None:
            super().__init__(*e.args)

    def __init__(self, params: GaussianParams, fallback_params: GaussianParams = None, eps: float = None):
        self.event = params.key
        self.params = params
        self.fallback_params = fallback_params
        self.eps = eps
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

        # for i, eps in enumerate([no_eps, diagonal_eps, everywhere_eps]):
        #     dist = self._create_multivariate(mean, fallback_params.cov + eps)
        #     j = 3
        #     state, is_error, str_result = self._process_dist_result(dist, str_event, i, j)
        #     print(str_result)
        #     if not is_error:
        #         return dist, state

        state = ApproximationLevel(2, 4)
        print(f"WARNING {str_event}: Could not any approx for event {self.event} -- {state}")
        return stats.multivariate_normal(np.zeros_like(params.mean)), state

    def _process_dist_result(self, dist, str_event, i, j):
        state = ApproximationLevel(i, j)
        is_error = (type(dist) == ApproximateMultivariateNormal.FallbackableException)
        str_result = f"WARNING {str_event}: {state} -- Could not create because {dist}" if is_error else f"SUCCESS {str_event}: {state}"
        return state, is_error, str_result

    def _create_multivariate(self, mean: NDArray, cov: NDArray) -> Union[FallbackableException, MultivariateNormal]:
        
        try:
            return stats.multivariate_normal(mean, cov)
        except LinAlgError as e:
            return ApproximateMultivariateNormal.FallbackableException(e)
        except ValueError as e:
            if e.args[0] == "the input matrix must be positive semidefinite":
                return ApproximateMultivariateNormal.FallbackableException(e)
            else:
                raise e

    def pdf(self, x: NDArray):
        # _len_feature_set = len(x)
        # results = np.zeros(_len_feature_set)
        # if self.event == 0:
        #     is_zero_fts = (x.sum(-1) == 0)[..., None].flatten()
        #     results = np.where(is_zero_fts, 1, results)
        #     results = np.where(~is_zero_fts, self.dist.pdf(x), results)
        #     return results
        if self.params.dim == 0 :
            return self.dist.pdf(x)
        variables = self.params.cov_mask[0]
        constants = ~variables
        const_mean = self.params._mean[constants]
        
        x_variables = x[:, variables]
        x_constants = x[:, constants]

        close_to_mean = np.isclose(const_mean[None], x_constants)
        not_deviating = np.all(close_to_mean, axis=1)
        probs = self.dist.pdf(x_variables)
        
        
        return probs * not_deviating

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
        return np.zeros((len(x),))

    @property
    def mean(self):
        return None

    @property
    def cov(self):
        return None


class PFeaturesGivenActivity():
    def __init__(self, all_dists: Dict[int, ApproximateMultivariateNormal]):
        self.all_dists = all_dists
        self.none_existing_dists = NoneExistingMultivariateNormal()

    def __getitem__(self, key) -> ApproximateMultivariateNormal:
        if key in self.all_dists:
            return self.all_dists.get(key)
        else:
            return self.none_existing_dists

    def __repr__(self):
        return f"@{type(self).__name__}{self.all_dists}"