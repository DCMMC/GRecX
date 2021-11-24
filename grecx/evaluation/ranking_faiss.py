# coding=utf-8
from itertools import chain

from tqdm import tqdm
import tensorflow as tf
import numpy as np

from grecx.metrics.ranking import ndcg_score


def pred2ndcg_dict(pred_match, num_items, k_list):
    ndcg_dict = {}
    for k in k_list:
        gold = [1] * num_items
        if len(gold) > k:
            gold = gold[:k]
        else:
            gold = gold + [0] * (k - len(gold))

        ndcg = ndcg_score(gold, pred_match[:k])
        ndcg_dict["ndcg@{}".format(k)] = ndcg
    return ndcg_dict


def ndcg2mean_ndcg_dict(results, k_list):
    metrics = ["ndcg@{}".format(K) for K in k_list]
    mean_ndcg_dict = {}
    for metric in metrics:
        scores = [result[metric] for result in results]
        mean_ndcg = np.mean(scores)
        mean_ndcg_dict[metric] = mean_ndcg
    return mean_ndcg_dict


def evaluate_mean_global_ndcg_score(user_items_dict, user_mask_items_dict, num_items,
                                    ranking_score_func,
                                    k_list=[5, 10, 15, 20], user_batch_size=1000, item_batch_size=5000):

    results = []
    test_users = list(user_items_dict.keys())
    for batch_user_indices in tqdm(tf.data.Dataset.from_tensor_slices(test_users).batch(user_batch_size)):

        user_rank_score_matrix = []

        for batch_item_indices in tf.data.Dataset.range(num_items).batch(item_batch_size):
            user_batch_rank_score_matrix = ranking_score_func(batch_user_indices.numpy(), batch_item_indices.numpy())
            user_rank_score_matrix.append(user_batch_rank_score_matrix)

        user_rank_score_matrix = np.concatenate(user_rank_score_matrix, axis=1)

        for user, user_rank_scores in zip(batch_user_indices, user_rank_score_matrix):

            result = {}
            results.append(result)

            user = user.numpy()
            # train_items = train_user_items_dict[user_index]
            items = user_items_dict[user]

            mask_items = user_mask_items_dict[user]

            # candidate_items = np.array(list(items) + list(user_neg_items_dict[user_index]))
            pred_items = np.argsort(user_rank_scores)[::-1][:k_list[-1] + len(mask_items)]

            pred_items = [item for item in pred_items if item not in mask_items][:k_list[-1]]

            pred_match = [1.0 if item in items else 0.0 for item in pred_items]

            results.append(pred2ndcg_dict(pred_match, len(items), k_list))

        return ndcg2mean_ndcg_dict(results, k_list)



def evaluate_mean_candidate_ndcg_score(user_items_dict, user_neg_items_dict,
                                    ranking_score_func,
                                    k_list=[5, 10, 15, 20], user_batch_size=1000, item_batch_size=5000, num_items=None):

    if num_items is None:
        num_items = max(max(items) for items in tqdm(chain(user_items_dict.values(), user_neg_items_dict.values())))+1
        print(num_items)

    results = []
    test_users = list(user_items_dict.keys())
    for batch_user_indices in tqdm(tf.data.Dataset.from_tensor_slices(test_users).batch(user_batch_size)):

        user_rank_score_matrix = []

        for batch_item_indices in tf.data.Dataset.range(num_items).batch(item_batch_size):
            user_batch_rank_score_matrix = ranking_score_func(batch_user_indices.numpy(), batch_item_indices.numpy())
            user_rank_score_matrix.append(user_batch_rank_score_matrix)

        user_rank_score_matrix = np.concatenate(user_rank_score_matrix, axis=1)

        for user, user_rank_scores in zip(batch_user_indices, user_rank_score_matrix):

            user = user.numpy()
            # train_items = train_user_items_dict[user_index]
            items = user_items_dict[user]

            candidate_items = np.array(list(items) + list(user_neg_items_dict[user]))
            candidate_scores = user_rank_scores[candidate_items]
            candidate_rank = np.argsort(candidate_scores)[::-1][:k_list[-1]]
            pred_items = candidate_items[candidate_rank]

            pred_match = [1.0 if item in items else 0.0 for item in pred_items]

            results.append(pred2ndcg_dict(pred_match, len(items), k_list))

    return ndcg2mean_ndcg_dict(results, k_list)



#
# def evaluate_mean_global_ndcg_score_with_faiss(user_items_dict, user_mask_items_dict,
#                                                user_embedding, item_embedding,
#                                                k_list=[5, 10, 15, 20]):
#     user_embedding = np.array(user_embedding)
#     item_embedding = np.array(item_embedding)
#     results = []
#     user_indices = list(user_items_dict.keys())
#     embedded_users = user_embedding[user_indices]
#     embedding_size = user_embedding.shape[-1]
#
#     import faiss  # make faiss available
#     index = faiss.IndexFlatIP(embedding_size)
#     index.add(item_embedding)
#
#     max_mask_items_length = max(len(user_mask_items_dict[user]) for user in user_indices)
#     _, user_rank_pred_items = index.search(embedded_users, k_list[-1]+max_mask_items_length)
#
#     for user, pred_items in tqdm(zip(user_indices, user_rank_pred_items)):
#
#         items = user_items_dict[user]
#         mask_items = user_mask_items_dict[user]
#         pred_items = [item for item in pred_items if item not in mask_items][:k_list[-1]]
#
#         pred_match = [1.0 if item in items else 0.0 for item in pred_items]
#
#         results.append(pred2ndcg_dict(pred_match, len(items), k_list))
#
#     return ndcg2mean_ndcg_dict(results, k_list)


from grecx.vector_search.vector_search import VectorSearch

def evaluate_mean_global_ndcg_score_with_faiss(user_items_dict, user_mask_items_dict,
                                               user_embedding, item_embedding,
                                               k_list=[5, 10, 15, 20]):

    v_search = VectorSearch(item_embedding)

    if isinstance(user_embedding, tf.Tensor):
        user_embedding = np.asarray(user_embedding)

    user_indices = list(user_items_dict.keys())
    embedded_users = user_embedding[user_indices]
    max_mask_items_length = max(len(user_mask_items_dict[user]) for user in user_indices)

    _, user_rank_pred_items = v_search.search(embedded_users, k_list[-1] + max_mask_items_length)

    results = []
    for user, pred_items in tqdm(zip(user_indices, user_rank_pred_items)):

        items = user_items_dict[user]
        mask_items = user_mask_items_dict[user]
        pred_items = [item for item in pred_items if item not in mask_items][:k_list[-1]]

        pred_match = [1.0 if item in items else 0.0 for item in pred_items]

        results.append(pred2ndcg_dict(pred_match, len(items), k_list))

    return ndcg2mean_ndcg_dict(results, k_list)

# user_items_dict = {
#     0: [1, 2],
#     1: [2, 3]
# }
# user_neg_items_dict = {
#     0: [5, 6],
#     1: [1, 5]
# }
#
# user_mask_items_dict = {
#     0: [4, 6],
#     1: [1, 8]
# }
#
#
#
# def random_score_func(batch_user_indices, batch_item_indices):
#
#     batch_user_indices = batch_user_indices
#     batch_item_indices = batch_item_indices
#
#     score_matrix = []
#     for user_index in batch_user_indices:
#         item_indices = user_items_dict[user_index]
#         mask_item_indices = user_mask_items_dict[user_index]
#         # scores = [1.0 if item_index in item_indices else 0.0 for item_index in batch_item_indices]
#         scores = [0.0 if item_index in mask_item_indices + item_indices else 1.0 for item_index in batch_item_indices]
#         print(scores)
#         score_matrix.append(scores)
#
#     return np.array(score_matrix)
#
# # print(evaluate_mean_candidate_ndcg_score(user_items_dict, user_neg_items_dict, random_score_func))
# print(evaluate_mean_global_ndcg_score(user_items_dict, user_mask_items_dict, num_items=13, ranking_score_func=random_score_func))
