import argparse
import os

from libs.core import load_config
from libs.model import *
from libs.model.COmnivore_V import COmnivore_V
from libs.model.COmnivore_G import COmnivore_G
from libs.model.LF import LF
from libs.utils import *
from libs.utils.logger import log, set_log_path
from libs.utils.metrics import shd

import numpy as np
from datetime import datetime
import networkx as nx
import torch

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
    
    log_config(lr, l2, bs)

    model_cfg = cfg['model']['output_model']
    model = select_model(model_cfg)

    ##################################################################################
    # load params for pipline
    pipline = cfg['pipeline']

    if pipline['baseline']:
        log("Training baseline....")
        baseline_accs = train_and_evaluate_end_model(samples_dict, valdata, metadata_val, testdata, metadata_test,rng, \
                                                     epochs, lr, bs, l2, model=model)

    if pipline['indiv_training']:
        log("Training using individual LF estimates...")
        for lf in G_estimates:
            log(lf)
            train_and_evaluate_end_model(samples_dict, valdata, metadata_val, testdata, metadata_test,rng, \
                                         epochs, lr, bs, l2, model=model, G_estimates=G_estimates[lf])

    log("Training with fused causal estimates...")

    #################################################################################
    # load params for COmnivore
    

    #################################################################################

    
    log(f"FUSE ALGORITHM: {fuser}")
    
    if fuser == 'COmnivore_V':
        COmnivore_params = opt['comnivore_v']
        all_negative_balance = np.arange(COmnivore_params['all_negative_balance'][0],COmnivore_params['all_negative_balance'][1],COmnivore_params['all_negative_balance'][2])
        snorkel_ep = COmnivore_params['snorkel_ep']
        snorkel_lr = COmnivore_params['snorkel_lr']
        COmnivore = COmnivore_V(G_estimates, snorkel_lr, snorkel_ep)
        for cb in all_negative_balance:
            log(f"###### {cb} ######")
            g_hats = COmnivore.fuse_estimates(cb, n_pca_features)
            train_and_evaluate_end_model(samples_dict, valdata, metadata_val, testdata, metadata_test,rng, \
                                        epochs, lr, bs, l2, model=model, G_estimates=g_hats)
    
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
            train_and_evaluate_end_model(samples_dict, valdata, metadata_val, testdata, metadata_test,rng, \
                epochs, lr, bs, l2, model=model, G_estimates=g_hats)
        
        
    return 0

    #################################################################################

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', type=str, help='config file path')
    parser.add_argument('-lr', '--learning_rate', type=float, help='end model training learning rate')
    parser.add_argument('-l2', '--l2_regularizer', type=float, help='end model l2 regularizer')
    parser.add_argument('-bs', '--batch_size', type=int, help='end model training batch size')
    parser.add_argument('-s_lr', '--snorkel_lr', type=float, help='snorkel learning rate')
    parser.add_argument('-s_ep', '--snorkel_epochs', type=float, help='snorkel epochs')
    args = parser.parse_args()
    print(args)
    main(args)
    os._exit(os.EX_OK)