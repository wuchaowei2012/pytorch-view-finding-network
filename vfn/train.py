import argparse
import torch
import torch.cuda
from ignite.engine import Events, Engine
from ignite.handlers import ModelCheckpoint
from tqdm import tqdm

from configs.parser import ConfigParser


def run(configs):
    device = configs.parse_device()
    num_epochs = configs.configs['train']['num_epochs']
    model_name = configs.get_model_name()
    model = configs.parse_model().to(device)
    data_loaders = configs.parse_dataloader()
    optimizer = configs.parse_optimizer()
    optimizer = optimizer(model.parameters())
    loss_fn = configs.parse_loss_function()

    desc = 'EPOCH - loss: {:.4f}'
    pbar = tqdm(initial=0, leave=False, total=len(data_loaders['train']), desc=desc.format(0), ascii=True)
    log_interval = 1

    def step(engine, batch):
        # initialize
        optimizer.zero_grad()

        # fetch inputs and transfer to specific device
        image_raw, image_crop = batch
        image_raw, image_crop = image_raw.to(device), image_crop.to(device)

        # forward
        score_I = model(image_raw)
        score_C = model(image_crop)

        # backward
        loss = loss_fn(score_I, score_C)
        loss.backward()
        optimizer.step()

        return dict(
            score_I=score_I,
            score_C=score_C,
            loss=loss.item()
        )

    trainer = Engine(step)

    # for validation
    def inference(engine, batch):
        model.eval()
        with torch.no_grad():
            # fetch inputs and transfer to specific device
            image_raw, image_crop = batch
            image_raw, image_crop = image_raw.to(device), image_crop.to(device)

            # forward
            score_I = model(image_raw)
            score_C = model(image_crop)

            loss = loss_fn(score_I, score_C)
            loss = loss.sum()

            return dict(
                score_I=score_I,
                score_C=score_C,
                sum_loss=loss.item()
            )

    evaluator = Engine(inference)

    # for evaluator
    @evaluator.on(Events.EPOCH_STARTED)
    def init_sum_loss(engine):
        engine.state.sum_loss = 0

    @evaluator.on(Events.ITERATION_COMPLETED)
    def compute_sum_loss(engine):
        engine.state.sum_loss += engine.state.output['sum_loss']

    @evaluator.on(Events.EPOCH_COMPLETED)
    def compute_average_loss(engine):
        engine.state.average_loss = engine.state.sum_loss / len(data_loaders['val'])

    # for trainer
    @trainer.on(Events.ITERATION_COMPLETED)
    def log_training_loss(engine):
        iter = (engine.state.iteration - 1) % len(data_loaders['train']) + 1

        if iter % log_interval == 0:
            pbar.desc = desc.format(engine.state.output['loss'])
            pbar.update(log_interval)

    @trainer.on(Events.EPOCH_COMPLETED)
    def log_training_results(engine):
        pbar.refresh()
        tqdm.write(
            'Training Results - Epoch: {}\n'
            'Loss: {:.4f}\n'.format(engine.state.epoch, engine.state.average_loss))

    ckpt_handler = ModelCheckpoint(
        dirname=configs.configs['checkpoint']['root_dir'],
        filename_prefix=configs.configs['checkpoint']['prefix'],
        save_interval=1,
        n_saved=configs.configs['train']['num_epochs'],
    )
    trainer.add_event_handler(Events.EPOCH_COMPLETED, ckpt_handler, {model_name: model})

    @trainer.on(Events.EPOCH_COMPLETED)
    def log_validation_results(engine):
        evaluator.run(data_loaders['val'])
        tqdm.write(
            'Validation Results - Epoch: {}\n'
            'Loss: {:.4f}\n'.format(engine.state.epoch, evaluator.state.average_loss))

        pbar.n = pbar.last_print_n = 0

    trainer.run(data_loaders['train'], num_epochs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config_file', type=str, help='Path to config file (.yml)', default='../configs/DEFAULT.yml')
    args = parser.parse_args()

    configs = ConfigParser(args.config_file)
    run(configs)


if __name__ == '__main__':
    main()
