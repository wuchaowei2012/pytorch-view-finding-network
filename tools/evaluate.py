import argparse
import torch
from PIL import Image
from torchvision import transforms
from tqdm import trange
from visdom import Visdom

from viewfinder_benchmark.config.parser import ConfigParser
from viewfinder_benchmark.network import backbones
from viewfinder_benchmark.network.models import ViewFindingNet
from viewfinder_benchmark.data.evaluation import ImageCropperEvaluator
from viewfinder_benchmark.utils.visualization import ColorType, plot_bbox


def generate_crop_annos_by_sliding_window(image):
    crop_annos = []
    max_width, max_height = image.size

    for scale in range(5, 10):
        scale /= 10
        w, h = max_width * scale, max_height * scale
        dw, dh = max_width - w, max_height - h
        dw, dh = dw / 5, dh / 5

        for w_idx in range(5):
            for h_idx in range(5):
                x, y = w_idx * dw, h_idx * dh
                crop_annos.append([x, y, w, h])

    return crop_annos


def evaluate_on(dataset, model, device, env, examples=5):
    print('Evaluate on {}.'.format(dataset))

    vis = Visdom()
    data_transforms = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
    ])
    ground_truth, img_sizes, pred = [], [], []
    for i in trange(len(dataset), ascii=True):
        data = dataset[i]
        filename, size, crop = data[0:3]
        img_sizes.append(size)
        ground_truth.append(crop)

        with Image.open(filename) as image:
            image = image.convert('RGB')
            crop_annos = generate_crop_annos_by_sliding_window(image)

            # add groundtruth
            crop_annos.append(crop)

            scores = []
            for crop_anno in crop_annos:
                x, y, w, h = crop_anno
                crop_image = image.crop((x, y, x+w, y+h))
                crop_image = data_transforms(crop_image)
                crop_image = crop_image.view((1, *crop_image.size()))
                crop_image = crop_image.to(device)

                score = model(crop_image)
                scores.append(score)

            scores = torch.tensor(scores)
            idx = scores.argmax().item()
            pred.append(crop_annos[idx])

            if i < examples:
                image = plot_bbox(image, crop_annos, ColorType.SLIDING_WINDOWS)
                image = plot_bbox(image, [ground_truth[-1]], ColorType.GROUNDTRUTH)
                image = plot_bbox(image, [crop_annos[idx]], ColorType.PREDICT)
                image_tensor = transforms.ToTensor()(image)
                vis.image(
                    image_tensor,
                    env=env,
                    opts=dict(
                        title='First {} example on {}'.format(i+1, dataset)
                    )
                )

    evaluator = ImageCropperEvaluator()
    evaluator.evaluate(ground_truth, pred, img_sizes)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config_file', type=str, help='Path to config file (.yml)', default='../configs/example.yml')
    args = parser.parse_args()

    configs = ConfigParser(args.config_file)

    testsets = [
        configs.parse_FCDB(),
        # configs.parse_ICDB(),
    ]
    device = configs.parse_device()
    backbone = backbones.AlexNet()
    weight = torch.load(configs.configs['weight'], map_location=lambda storage, loc: storage)
    model = ViewFindingNet(backbone).to(device)
    model.load_state_dict(weight)

    for testset in testsets:
        evaluate_on(testset, model, device, configs.configs['checkpoint']['prefix'])


if __name__ == '__main__':
    main()