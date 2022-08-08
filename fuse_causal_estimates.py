import argparse
import os

from libs.core import load_config
from libs.model import *
from libs.model.COmnivore_V import COmnivore_V
from libs.model.COmnivore_G import COmnivore_G
from libs.model.LF import LF
from libs.utils import *
from libs.utils.logger import log, set_log_path

import numpy as np
from datetime import datetime
import torch

from libs.utils.wilds_utils import WILDS_utils
from libs.utils.domainbed_utils import DomainBed_utils
from libs.datasets import WILDS_DATASETS, DOMAINBED_DATASETS

cuda = True if torch.cuda.is_available() else False
LongTensor = torch.cuda.LongTensor if cuda else torch.LongTensor

def main(args):
    # may be we need to implement load from checkpoint function here

    #load config
    cfg = load_config(args.config)
    rng = fix_random_seed(cfg.get('seed', 2022))

    # load tasks params
    dataset_cfg = cfg['data']['dataset']
    dataset_name = dataset_cfg['dataset_name']
    load_path = dataset_cfg['load_path']
    
    n_orig_features = dataset_cfg['n_orig_features']
    n_pca_features = dataset_cfg['n_pac_features']
    global tasks
    tasks = dataset_cfg['tasks']
    fuser = cfg['model']['fuser']


    #########################################################
    # create log folder
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if 'log_path' in args and args.log_path is not None:
        log_path = os.path.join('log',args.log_path,dataset_name, fuser,timestamp)
    else:
        log_path = os.path.join('log', dataset_name, fuser, timestamp)
    ensure_path(log_path)
    set_log_path(log_path)


    lf_factory = LF()
    samples_dict = get_samples_dict(load_path,n_orig_features,n_pca_features,tasks)

    active_lfs = cfg['model']['active_lfs']


    G_estimates = {}
    for lf in active_lfs['notears']:
        log(f"Running {lf}...")
        G_estimates[lf] = run_notears_lfs(samples_dict,tasks, lf_factory.lf_dict[lf], lf, False)

    for lf in active_lfs['classic']:
        log(f"Running {lf}...")
        G_estimates[lf] = run_classic_lfs(samples_dict,tasks, lf_factory.lf_dict[lf], lf, False)

    for lf in active_lfs['pycausal']:
        log(f"Running {lf}...")
        G_estimates[lf] = run_classic_lfs(samples_dict, tasks,lf_factory.lf_dict['pycausal'], lf, False, pycausal=True)

    metadata_test = np.load(os.path.join(load_path, "metadata_test.npy"))
    testdata = np.load(os.path.join(load_path, f"orig_full_test_{n_orig_features}.npy"))

    metadata_val = np.load(os.path.join(load_path, "metadata_val.npy"))
    valdata = np.load(os.path.join(load_path, f"orig_full_val_{n_orig_features}.npy"))

    ##################################################################################
    # set up optimizer
    opt = cfg['opt']
    epochs = opt['epochs']
    if 'learning_rate' in args and not isinstance(args.learning_rate,type(None)):
        lr = args.learning_rate
    else:
        lr = opt['lr']
    if 'l2_regularizer' in args and not isinstance(args.l2_regularizer,type(None)):
        l2 = args.l2_regularizer
    else:
        l2 = opt['l2']
    if 'batch_size' in args and not isinstance(args.batch_size,type(None)):
        bs = args.batch_size
    else:
        bs = cfg['data']['batch_size']
    if 'alpha' in args and not isinstance(args.alpha,type(None)):
        alpha = args.alpha
    else:
        alpha = cfg['model']['alpha']
    log_config(lr, l2, bs, alpha)

    model_cfg = cfg['model']['output_model']
    model = select_model(model_cfg)

    ##################################################################################
    # load params for pipline
    pipline = cfg['pipeline']
    
    evaluate_func = None
    if dataset_name in WILDS_DATASETS:
        evaluate_func = WILDS_utils(dataset_name).evaluate_wilds
    elif dataset_name in DOMAINBED_DATASETS:
        evaluate_func = DomainBed_utils(dataset_name).evaluate_domainbed
    
    baseline_accs = None
    utils_cfg = cfg['utils']
    log_freq = utils_cfg['log_freq']
    if pipline['baseline']:
        log("Training baseline....")
        traindata, valdata, testdata, _ = get_data_from_feat_label_array(samples_dict, valdata, testdata, G_estimates=None, scale=False)
        baseline_accs = train_and_evaluate_end_model(traindata, valdata, metadata_val, testdata, metadata_test,rng, \
                                                     dataset_name, epochs, lr, bs, l2, model=model, alpha=alpha, evaluate_func=evaluate_func, log_freq=log_freq)

    if pipline['indiv_training']:
        log("Training using individual LF estimates...")
        for lf in G_estimates:
            log(lf)
            traindata, valdata, testdata, _ = get_data_from_feat_label_array(samples_dict, valdata, testdata, G_estimates=G_estimates[lf], scale=False)
            train_and_evaluate_end_model(traindata, valdata, metadata_val, testdata, metadata_test,rng, \
                                         dataset_name, epochs, lr, bs, l2, model=model, G_estimates=G_estimates[lf], alpha=alpha, evaluate_func=evaluate_func, \
                                             log_freq=log_freq)

    log("Training with fused causal estimates...")

    #################################################################################
    # load params for COmnivore
    #################################################################################

    
    log(f"FUSE ALGORITHM: {fuser}")
    eval_accs_all = {}
    cache_nodes = []
    if fuser == 'COmnivore_V':
        COmnivore_params = opt['comnivore_v']
        all_negative_balance = np.arange(COmnivore_params['all_negative_balance'][0],COmnivore_params['all_negative_balance'][1],COmnivore_params['all_negative_balance'][2])
        if 'snorkel_lr' in args and args.snorkel_lr is not None:
            snorkel_lr = args.snorkel_lr
        else:
            snorkel_lr = COmnivore_params['snorkel_lr']
        if 'snorkel_epochs' in args and args.snorkel_epochs is not None:
            snorkel_ep = args.snorkel_epochs
        else:
            snorkel_ep = COmnivore_params['snorkel_ep']
        log(f"SNORKEL PARAMS: lr {snorkel_lr} | ep {snorkel_ep}")
        COmnivore = COmnivore_V(G_estimates, snorkel_lr, snorkel_ep)
        
        for cb in all_negative_balance:
            log(f"###### {cb} ######")
            g_hats = COmnivore.fuse_estimates(cb, n_pca_features)
            traindata, valdata, testdata, pca_nodes = get_data_from_feat_label_array(samples_dict, valdata, testdata, G_estimates=g_hats, scale=False)
            print("PCA NODES", pca_nodes)
            if not test_duplicate_nodes(pca_nodes, cache_nodes):
                eval_accs = train_and_evaluate_end_model(traindata, valdata, metadata_val, testdata, metadata_test,rng, \
                                            dataset_name, epochs, lr, bs, l2, model=model, alpha=alpha, evaluate_func=evaluate_func, \
                                                log_freq=log_freq)
                eval_accs_all[cb] = eval_accs
                cache_nodes.append(pca_nodes)
            else:
                print("Nodes cached, skipping training on these nodes")
    
    elif fuser == 'COmnivore_G':
        COmnivore_params = opt['comnivore_g']
        n_triplets = COmnivore_params['n_triplets']
        min_iters = COmnivore_params['min_iters']
        max_iters = COmnivore_params['max_iters']
        step = COmnivore_params['step']
        COmnivore = COmnivore_G(G_estimates, n_triplets, min_iters, max_iters, step)
        g_hats_per_task = COmnivore.fuse_estimates()
        n_iters = np.array([i for i in range(min_iters, max_iters+step, step)])
        for i, iter_ in enumerate(n_iters):
            log(f"##### ITER: {iter_} #####")
            g_hats = {}
            for task in g_hats_per_task:
                g_hats[task] = g_hats_per_task[task][i]
            traindata, valdata, testdata, pca_nodes = get_data_from_feat_label_array(samples_dict, valdata, testdata, G_estimates=g_hats, scale=False)
            if not test_duplicate_nodes(pca_nodes, cache_nodes):
                eval_accs = train_and_evaluate_end_model(traindata, valdata, metadata_val, testdata, metadata_test,rng, \
                                dataset_name, epochs, lr, bs, l2, model=model, G_estimates=g_hats, alpha=alpha, evaluate_func=evaluate_func, \
                                    log_freq=log_freq)
                eval_accs_all[iter_] = eval_accs
                cache_nodes.append(pca_nodes)
            else:
                print("Nodes cached, skipping training on these nodes")
    best_val_acc, best_test = get_best_model_acc(eval_accs_all)
        
    return baseline_accs, best_val_acc, best_test

    #################################################################################

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', type=str, help='config file path', required=True)
    parser.add_argument('-lr', '--learning_rate', type=float, help='end model training learning rate')
    parser.add_argument('-l2', '--l2_regularizer', type=float, help='end model l2 regularizer')
    parser.add_argument('-bs', '--batch_size', type=int, help='end model training batch size')
    parser.add_argument('-s_lr', '--snorkel_lr', type=float, help='snorkel learning rate')
    parser.add_argument('-a', '--alpha', type=int, help='hidden neurons alpha')
    parser.add_argument('-s_ep', '--snorkel_epochs', type=int, help='snorkel epochs')
    parser.add_argument('-log', '--log_path', type=str, help='log path', default=None)
    args = parser.parse_args()
    # print(args)
    baseline_accs, best_val_acc, best_test = main(args)
    if baseline_accs is not None:
        print("Baseline test accuracy: {:.3f}".format(baseline_accs['test']['acc_wg']))
    print("Best validation set accuracy: {:.3f}".format(best_val_acc))
    print("Best model test accuracy: {:.3f}".format(best_test))
    os._exit(os.EX_OK)