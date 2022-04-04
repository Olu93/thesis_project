from typing import Any, Callable
from unicodedata import is_normalized
import numpy as np
from thesis_readers import MockReader as Reader
from thesis_generators.helper.wrapper import GenerativeDataset
from thesis_commons.modes import DatasetModes, GeneratorModes
from thesis_commons.modes import TaskModes
from scipy.spatial import distance

DEBUG_SLOW = False


def levenshtein(s1, s2):
    d = {}
    s1_ev, s1_ft = s1
    s2_ev, s2_ft = s2
    lenstr1 = len(s1_ev)
    lenstr2 = len(s2_ev)
    s1_default_dist = num_changes_distance(s1_ft, np.zeros_like(s1_ft))
    s2_default_dist = num_changes_distance(s2_ft, np.zeros_like(s2_ft))
    for i in range(-1, lenstr1 + 1):
        d[(i, -1)] = (i + 1) * s1_default_dist
    for j in range(-1, lenstr2 + 1):
        d[(-1, j)] = (j + 1) * s2_default_dist
    # print("START")
    # tmp=to_matrix(d, lenstr1, lenstr2)
    # print(tmp[:-1, :-1])
    for i in range(lenstr1):
        for j in range(lenstr2):
            if s1_ev[i] == s2_ev[j]:
                cost = num_changes_distance(s1_ft[i], s2_ft[j])
            else:
                cost = s1_default_dist + s2_default_dist
            d[(i, j)] = min(
                d[(i - 1, j)] + s1_default_dist,  # deletion
                d[(i, j - 1)] + s2_default_dist,  # insertion
                d[(i - 1, j - 1)] + cost,  # substitution
            )
            if i and j and s1_ev[i] == s2_ev[j - 1] and s1_ev[i - 1] == s2_ev[j]:
                d[(i, j)] = min(d[(i, j)], d[i - 2, j - 2] + cost)  # transposition
    if DEBUG_SLOW:
        print("------")
        tmp = to_matrix(d, lenstr1, lenstr2)
        print(tmp)
    return float(d[lenstr1 - 1, lenstr2 - 1])


def to_matrix(d, lenstr1, lenstr2):
    d_tmp = np.zeros((lenstr1 + 1, lenstr2 + 1))
    for (k, l), val in d.items():
        d_tmp[k, l] = val
    return d_tmp


class DamerauLevenshstein():

    def __init__(self, vocab_len: int, distance_func: Callable):
        self.dist = distance_func
        self.vocab_len = vocab_len

    def __call__(self, s1, s2, is_normalized=False):
        s1_ev, s1_ft = s1
        s2_ev, s2_ft = s2
        mask_cond = (s1_ev != 0) & (s1_ev != 0)
        s1_default_dist = self.dist(s1_ft, np.zeros_like(s1_ft))
        s2_default_dist = self.dist(s2_ft, np.zeros_like(s2_ft))
        lenstr1 = len(s1_ev)
        lenstr2 = len(s2_ev)
        d = np.zeros((lenstr1 + 1, lenstr2 + 1))

        d[:, 0] = np.arange(0, lenstr1 + 1) * s1_default_dist
        d[0, :] = np.arange(0, lenstr2 + 1) * s2_default_dist

        for i in range(1, lenstr1 + 1):
            for j in range(1, lenstr2 + 1):
                if s1_ev[i - 1] == s2_ev[j - 1]:
                    cost = self.dist(s1_ft[i - 1], s2_ft[j - 1])
                else:
                    cost = s1_default_dist + s2_default_dist

                d[i, j] = min(
                    d[i - 1, j] + s1_default_dist,  # deletion
                    d[i, j - 1] + s2_default_dist,  # insertion
                    d[i - 1, j - 1] + cost,  # substitution
                )
                if i > 1 and j > 1:
                    if i and j and s1_ev[i - 1] == s2_ev[j - 2] and s1_ev[i - 2] == s2_ev[j - 1]:
                        d[(i, j)] = min(d[(i, j)], d[i - 2, j - 2] + cost)  # transposition
                # print("------")
                # print(d)
        if DEBUG_SLOW:
            print("------")
            print(d)

        return d[lenstr1, lenstr2] if not is_normalized else 1 - d[lenstr1, lenstr2] / max(lenstr1, lenstr2)


class DamerauLevenshsteinParallel():

    def __init__(self, vocab_len: int, max_len: int, distance_func: Callable):
        self.dist = distance_func
        self.vocab_len = vocab_len
        self.max_len = max_len

    def __call__(self, s1, s2, is_normalized=False):
        lenstr1 = self.max_len
        lenstr2 = self.max_len
        num_instances = len(s1)
        d = np.zeros((num_instances, lenstr1 + 1, lenstr2 + 1))
        max_dist = lenstr1 + lenstr2
        for i in range(self.max_len + 1):
            d[:, :, i] = i
            d[:, i, :] = i
        mask_s1 = np.ma.masked_equal(s1, 0)
        mask_s2 = np.ma.masked_equal(s2, 0)
        # mask = mask_s1 & mask_s2
        for i in range(1, lenstr1 + 1):
            for j in range(1, lenstr2 + 1):
                cost = (mask_s1[:, i - 1] != mask_s2[:, j - 1]) * 1
                deletion = d[:, i - 1, j] + 1
                insertion = d[:, i, j - 1] + 1
                substitution = d[:, i - 1, j - 1] + cost
                transposition = np.ones_like(d[:, i, j]) * np.inf
                if i > 1 and j > 1:
                    one_way = mask_s1[:, i - 1] == mask_s2[:, j - 2]
                    bck_way = mask_s1[:, i - 2] == mask_s2[:, j - 1]
                    is_transposed = one_way & bck_way
                    prev_d = d[:, i - 2, j - 2]
                    prev_d[~is_transposed] = np.inf
                    transposition = prev_d + 1
                cases = np.array([
                    deletion,
                    insertion,
                    substitution,
                    transposition,
                ])

                min_d = np.min(cases, axis=0)
                d[:, i, j] = min_d

        if not is_normalized:
            return d[:, lenstr1, lenstr2]
        all_lengths = (~np.ma.getmask(mask_s1) & ~np.ma.getmask(mask_s2)).sum(axis=1)
        return 1 - d[:, lenstr1, lenstr2] / all_lengths


def num_changes_distance(a, b):
    differences = a != b
    num_differences = differences.sum(axis=-1)
    total_differences_in_sequence = num_differences.sum(axis=-1)
    return total_differences_in_sequence


if __name__ == "__main__":
    task_mode = TaskModes.NEXT_EVENT_EXTENSIVE
    epochs = 50
    reader = None
    reader = Reader(mode=task_mode).init_meta()

    generative_reader = GenerativeDataset(reader)
    train_data = generative_reader.get_dataset(1, DatasetModes.TRAIN, gen_mode=GeneratorModes.HYBRID, flipped_target=True)

    generative_reader2 = GenerativeDataset(reader)
    train_data2 = generative_reader2.get_dataset(1, DatasetModes.TRAIN, gen_mode=GeneratorModes.HYBRID, flipped_target=True).shuffle(10)
    # train_data2 = generative_reader2.get_dataset(1, DatasetModes.TRAIN, gen_mode=GeneratorModes.HYBRID, flipped_target=True)#.shuffle(10)

    a = [instances for tmp in train_data for instances in tmp]
    b = [instances for tmp in train_data2 for instances in tmp]

    loss_singular = DamerauLevenshstein(reader.vocab_len, num_changes_distance)
    distances_singular = []
    sanity_ds_singular = []
    for a_i, b_i in zip(a, b):
        a_i = a_i[0][0].numpy().astype(int), a_i[1][0].numpy()
        b_i = b_i[0][0].numpy().astype(int), b_i[1][0].numpy()
        r_my = loss_singular(a_i, b_i)
        r_sanity = levenshtein(a_i, b_i)
        if (r_my != r_sanity):
            DEBUG_SLOW = True
            print(f"Hm... {r_my} is not {r_sanity}")
            print("rerun start...")
            r_my = loss_singular(a_i, b_i)
            r_sanity = levenshtein(a_i, b_i)
            print("rerun end...")
            DEBUG_SLOW = False
        distances_singular.append(r_my)
        sanity_ds_singular.append(r_sanity)

    loss = DamerauLevenshsteinParallel(reader.vocab_len, reader.max_len, num_changes_distance)
    bulk_distances = loss(a, b)
    all_results = np.array([distances_singular, sanity_ds_singular, bulk_distances])
    print(f"All results\n{all_results}")
    if all_results.sum() == 0:
        print("Hmm...")