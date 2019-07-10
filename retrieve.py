import numpy as np
import argparse
import spacy
import configparser
import pickle

import torch
import torchvision
import torchtext

import datasets
import models
from build_vocab import Vocab


config = configparser.ConfigParser()
spacy_en = spacy.load('en')


def tokenize(text):
    return [tok.text for tok in spacy_en.tokenizer(text)]


def encode_candidate(sen_encoder, img_encoder, dataloader, device):
    s_list = []
    s_ids = []
    i_list = []
    i_ids = []

    with torch.no_grad():
        for imgs, sens, lengths, img_ids, ids in dataloader:
            imgs = imgs.to(device)
            img_embedded = img_encoder(imgs).to(torch.device("cpu"))
            sens = torch.transpose(sens, 0, 1)
            sens = sens.to(device)
            sen_embedded = sen_encoder(sens, lengths).to(torch.device("cpu"))

            i_list.append(img_embedded)
            s_list.append(sen_embedded)
            i_ids.append(img_ids)
            s_ids.append(ids)

    s_vectors = torch.cat(tuple(s_list)).numpy()
    s_ids = torch.cat(tuple(s_ids)).numpy()
    i_vectors = torch.cat(tuple(i_list)).numpy()
    i_ids = torch.cat(tuple(i_ids)).numpy()

    used_ids = set()
    mask = []
    for i, id in enumerate(i_ids):
        if id not in used_ids:
            used_ids.add(id)
            mask.append(True)
        else:
            mask.append(False)
    mask = np.array(mask, dtype=bool)

    i_vectors = i_vectors[mask]
    i_ids = i_ids[mask]

    return s_vectors, s_ids, i_vectors, i_ids


def main(args):
    gpu = args.gpu
    config_path = args.config
    vocab_path = args.vocab
    img2vec_path = args.img2vec
    val_json_path = args.val_json
    sentence_encoder_path = args.sentence_encoder
    image_encoder_path = args.image_encoder
    name = args.name
    mode = args.mode

    print("[args] gpu=%d" % gpu)
    print("[args] config_path=%s" % config_path)
    print("[args] word2vec_path=%s" % vocab_path)
    print("[args] img2vec_path=%s" % img2vec_path)
    print("[args] val_json_path=%s" %val_json_path)
    print("[args] sentence_encoder_path=%s" % sentence_encoder_path)
    print("[args] image_encoder_path=%s" % image_encoder_path)
    print("[args] name=%s" % name)
    print("[args] mode=%s" % mode)

    device = torch.device("cuda:" + str(gpu) if torch.cuda.is_available() else "cpu")

    config.read(config_path)

    # Model parameters
    modelparams = config["modelparams"]
    image_encoder_name = modelparams.get("image_encoder")
    sentence_encoder_name = modelparams.get("sentence_encoder")
    n_layers = modelparams.getint("n_layers")
    word_size = modelparams.getint("word_size")
    img_size = modelparams.getint("img_size")
    img_hidden_size = modelparams.getint("img_hidden_size")
    embed_size = modelparams.getint("embed_size")

    print("[modelparames] image_encoder_name=%s" % image_encoder_name)
    print("[modelparames] sentence_encoder_name=%s" % sentence_encoder_name)
    print("[modelparames] n_layers=%d" % n_layers)
    print("[modelparames] word_size=%d" % word_size)
    print("[modelparames] img_size=%d" % img_size)
    print("[modelparames] img_hidden_size=%d" % img_hidden_size)
    print("[modelparames] embed_size=%d" % embed_size)

    hyperparams = config["hyperparams"]
    batch_size = hyperparams.getint("batch_size")

    print("[hyperparames] batch_size=%d" % batch_size)

    # Data preparation
    print("[info] Loading vocabulary ...")
    with open(vocab_path, 'rb') as f:
        vocab = pickle.load(f)
    dataloader_val = datasets.coco.get_loader(img2vec_path, val_json_path, vocab, batch_size)

    # Model preparation
    img_encoder = models.ImageEncoder(img_size, img_hidden_size, embed_size).to(device)
    if sentence_encoder_name == 'GRU':
        sen_encoder = models.GRUEncoder(vocab, word_size, embed_size, n_layers).to(device)
    elif sentence_encoder_name == 'LSTM':
        sen_encoder = models.LSTMEncoder(vocab, word_size, embed_size, n_layers).to(device)
    else:
        raise ValueError
    # Load params
    img_encoder.load_state_dict(torch.load(image_encoder_path))
    sen_encoder.load_state_dict(torch.load(sentence_encoder_path))
    img_encoder.eval()
    sen_encoder.eval()

    # Evaluate
    print("[info] Encoding candidate ...")
    s_vectors, s_ids, i_vectors, i_ids = encode_candidate(sen_encoder, img_encoder, dataloader_val, device)

    if mode == 's2i':
        print('[info] Retrieving image')
        caption_id = input("input caption id: ")
        caption_id = int(caption_id)
        coco = dataloader_val.dataset.coco
        print("Caption: %s" % coco.anns[caption_id]['caption'])
        target = s_vectors[s_ids == caption_id]
        target = target.flatten()

        scores = i_vectors.dot(target)
        sorted_ids = i_ids[np.argsort(scores)[::-1]]
        for i in range(9):
            print(sorted_ids[i])

    elif mode == 'i2s':
        print('[info] Retrieving caption')
        image_id = input("input image id: ")
        image_id = int(image_id)
        coco = dataloader_val.dataset.coco
        target = i_vectors[i_ids == image_id]
        target = target.flatten()

        scores = s_vectors.dot(target)
        sorted_ids = s_ids[np.argsort(scores)[::-1]]
        for i in range(9):
            print("Caption: %s" % coco.anns[sorted_ids[i]]['caption'])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--gpu", type=int, default=0)
    parser.add_argument("--config", type=str, required=True)
    parser.add_argument("--vocab", type=str, default=None)
    parser.add_argument("--img2vec", type=str, default=None)
    parser.add_argument("--val_json", type=str, default=None)
    parser.add_argument("--sentence_encoder", type=str, required=True)
    parser.add_argument("--image_encoder", type=str, required=True)
    parser.add_argument("--name", type=str, required=True)
    parser.add_argument("--mode", type=str, required=True)

    args = parser.parse_args()
    main(args)