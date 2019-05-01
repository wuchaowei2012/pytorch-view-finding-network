from functools import partial

import torch
import torch.optim as optim
import yaml

from gulpio.loader import DataLoader
from torch.utils.data import random_split
from torchvision import transforms

import viewfinder_benchmark.network.backbones as backbones
import viewfinder_benchmark.network.losses as losses
import viewfinder_benchmark.network.models as models

from viewfinder_benchmark.data.FlickrPro import FlickrPro
from viewfinder_benchmark.data.FCDB import FCDB
from viewfinder_benchmark.data.ICDB import ICDB
from viewfinder_benchmark.data.dataset import ImagePairDataset


class ConfigParser:

    def __init__(self, config_file):
        self._load(config_file)
        self._init_name()
        self.input_dim = 0

    def _init_name(self):
        # All `*_name` are disposable because the `pop()` operation will modify the origin `configs`.
        self.backbone_name = self.configs['model']['backbone'].pop('name')
        self.optimizer_name = self.configs['train']['optimizer'].pop('name')
        self.loss_name = self.configs['train']['loss'].pop('name')
        self.dataset_name = self.configs['train']['dataset'].pop('name')

    def _load(self, config_file):
        with open(config_file, 'r') as f:
            self.configs = yaml.load(f)

    def get_model_name(self):
        return self.backbone_name

    def parse_model(self):
        backbone_model = None
        if self.backbone_name == 'AlexNet':
            backbone_model = backbones.AlexNet

        backbone = backbone_model(**self.configs['model']['backbone'])
        model = models.ViewFindingNet(backbone=backbone)
        self.input_dim = backbone.input_dim()
        return model

    def parse_optimizer(self):
        optimizer_fn = None

        if self.optimizer_name == 'SGD':
            optimizer_fn = optim.SGD
        elif self.optimizer_name == 'Adam':
            optimizer_fn = optim.Adam

        optimizer = partial(optimizer_fn, **self.configs['train']['optimizer'])
        return optimizer

    def parse_loss_function(self):
        loss_fn = None

        if self.loss_name == 'hinge':
            loss_fn = losses.hinge_loss
        elif self.loss_name == 'ranknet':
            loss_fn = losses.ranknet_loss

        return loss_fn

    def parse_dataloader(self):
        dataset_cls = None
        if self.dataset_name == 'FlickrPro':
            dataset_cls = FlickrPro

        data_transform = transforms.Compose([
            transforms.ToPILImage(),
            transforms.Resize((self.input_dim, self.input_dim)),
            transforms.ToTensor(),
        ])

        # src_dataset = dataset_cls(root_dir=self.configs['train']['dataset']['root_dir'],
        #                       transforms=data_transform)
        dataset = ImagePairDataset(self.configs['train']['dataset']['gulpio_dir'],
                                   data_transform)
        train_size = self.configs['train']['dataset']['train_size']
        print('train_size:', train_size)
        val_size = len(dataset) - train_size
        print('val_size:', val_size)

        train_dataset, val_dataset = random_split(dataset, [train_size, val_size])

        data_loaders = dict(
            train=DataLoader(train_dataset, **self.configs['train']['dataloader'], num_workers=8),
            val=DataLoader(val_dataset, **self.configs['validation']['dataloader'], num_workers=8),
        )
        return data_loaders

    def parse_device(self):
        return torch.device(self.configs['device'])

    def parse_FCDB(self):
        return FCDB(**self.configs['evaluate']['FCDB'])

    def parse_ICDB(self):
        return ICDB(**self.configs['evaluate']['ICDB'])