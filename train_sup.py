import argparse
import os

import numpy as np
from torch.utils.data import DataLoader
from augmentloader import AugmentLoader
import torch.optim as optim
import torch.optim.lr_scheduler as lr_scheduler

import train_func as tf
from loss import MaximalCodingRateReduction
import utils
import math
import torch
import math
import pytorch_warmup as warmup


parser = argparse.ArgumentParser(description='Supervised Learning')
parser.add_argument('--arch', type=str, default='resnet18',
                    help='architecture for deep neural network (default: resnet18)')
parser.add_argument('--fd', type=int, default=128,
                    help='dimension of feature dimension (default: 128)')
parser.add_argument('--data', type=str, default='cifar10',
                    help='dataset for training (default: CIFAR10)')
parser.add_argument('--epo', type=int, default=805,
                    help='number of epochs for training (default: 800)')
parser.add_argument('--bs', type=int, default=1000,
                    help='input batch size for training (default: 1000)')
parser.add_argument('--lr', type=float, default=0.005,
                    help='learning rate (default: 0.001)')
parser.add_argument('--mom', type=float, default=0.9,
                    help='momentum (default: 0.9)')
parser.add_argument('--wd', type=float, default=5e-4,
                    help='weight decay (default: 5e-4)')
parser.add_argument('--gam1', type=float, default=1.,
                    help='gamma1 for tuning empirical loss (default: 1.)')
parser.add_argument('--gam2', type=float, default=1.,
                    help='gamma2 for tuning empirical loss (default: 1.)')
parser.add_argument('--eps', type=float, default=0.5,
                    help='eps squared (default: 0.5)')
parser.add_argument('--corrupt', type=str, default="default",
                    help='corruption mode. See corrupt.py for details. (default: default)')
parser.add_argument('--lcr', type=float, default=0.,
                    help='label corruption ratio (default: 0)')
parser.add_argument('--lcs', type=int, default=10,
                    help='label corruption seed for index randomization (default: 10)')
parser.add_argument('--tail', type=str, default='',
                    help='extra information to add to folder name')
parser.add_argument('--transform', type=str, default='default',
                    help='transform applied to trainset (default: default')
parser.add_argument('--save_dir', type=str, default='./saved_models/',
                    help='base directory for saving PyTorch model. (default: ./saved_models/)')
parser.add_argument('--data_dir', type=str, default='./data/',
                    help='base directory for saving PyTorch model. (default: ./data/)')
parser.add_argument('--pretrain_dir', type=str, default=None,
                    help='load pretrained checkpoint for assigning labels')
parser.add_argument('--pretrain_epo', type=int, default=None,
                    help='load pretrained epoch for assigning labels')
args = parser.parse_args()


## Pipelines Setup
model_dir = os.path.join(args.save_dir,
               'sup_{}+{}_{}_epo{}_bs{}_lr{}_mom{}_wd{}_gam1{}_gam2{}_eps{}_lcr{}{}'.format(
                    args.arch, args.fd, args.data, args.epo, args.bs, args.lr, args.mom, 
                    args.wd, args.gam1, args.gam2, args.eps, args.lcr, args.tail))
utils.init_pipeline(model_dir)

## Prepare for Training
if args.pretrain_dir is not None:
    net, _ = tf.load_checkpoint(args.pretrain_dir, args.pretrain_epo)
    # utils.update_params(model_dir, args.pretrain_dir)
else:
    net = tf.load_architectures(args.arch, args.fd)
transforms = tf.load_transforms(args.transform)
trainset = tf.load_trainset(args.data, transforms, path=args.data_dir)
# trainset = tf.corrupt_labels(args.corrupt)(trainset, args.lcr, args.lcs)
trainloader = DataLoader(trainset, batch_size=args.bs, drop_last=True, num_workers=4)

criterion = MaximalCodingRateReduction(gam1=args.gam1, gam2=args.gam2, eps=args.eps)

# Example usage:
warmup_steps = 200
total_steps = args.epo + 1

optimizer = torch.optim.AdamW(net.parameters(), lr=args.lr, betas=(0.9, 0.999), weight_decay=args.wd)
lr_scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=total_steps)
warmup_scheduler = warmup.LinearWarmup(optimizer, warmup_period=warmup_steps)

utils.save_params(model_dir, vars(args))

## Training
for epoch in range(args.epo):
    for step, (batch_imgs, batch_lbls) in enumerate(trainloader):
        features = net(batch_imgs.cuda())
        loss, loss_empi, loss_theo = criterion(features, batch_lbls, num_classes=trainset.num_classes)
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        utils.save_state(model_dir, epoch, step, loss.item(), *loss_empi, *loss_theo)
    print('===================== epoch=', epoch, ' loss=', loss.item(), 'loss_theo=', loss_theo, '===================== ')
    with warmup_scheduler.dampening():
        lr_scheduler.step()
    current_lr = optimizer.param_groups[0]['lr']
    print(f'Epoch {epoch+1}: LR = {current_lr:.6f}')
    if epoch % 100 == 0:
        utils.save_ckpt(model_dir, net, epoch)
print("training complete.")
