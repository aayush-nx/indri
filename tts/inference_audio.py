import os
import json

os.environ["SUNO_OFFLOAD_CPU"] = "True"

import numpy as np
import bark
import torch
from contextlib import nullcontext
from pathlib import Path

from encodec.utils import save_audio

from tts.gpt2_model import get_model

from datalib.tokenlib import get_tokenizer
from tts.train_tts import cfg
from common import SEMANTIC, TEXT, ACOUSTIC

seed = 1337
torch.manual_seed(seed)
torch.cuda.manual_seed(seed)
torch.backends.cuda.matmul.allow_tf32 = True
torch.backends.cudnn.allow_tf32 = True
device = 'cuda:0'
dtype = 'bfloat16' if torch.cuda.is_available() and torch.cuda.is_bf16_supported() else 'float16'

device_type = 'cuda' if 'cuda' in device else 'cpu'
ptdtype = {'float32': torch.float32, 'bfloat16': torch.bfloat16, 'float16': torch.float16}[dtype]
ctx = nullcontext() if device_type == 'cpu' else torch.amp.autocast(device_type=device_type, dtype=ptdtype)


class GPTModel:
    def __init__(self, path, source, target, device='cuda:0'):
        self.device = device

        self.path = Path(path)/'gpt_100.pt'
        self.vocab_size = cfg.VOCAB_SIZE
        self.model = self.load(self.path)

        self.source = source
        self.target = target

    def load(self, path):
        saved_model = torch.load(path)['model']
        model = get_model(vocab_size=self.vocab_size, device=self.device)
        model.load_state_dict(saved_model)
        model.eval()
        return model

    def generate(self, tokens, max_new_tokens=1024, temperature=0.8, top_k=100):
        with torch.no_grad():
            with ctx:
                y = self.model.generate(tokens, max_new_tokens, temperature=temperature, top_k=top_k)
                y = y.detach().cpu().numpy()[0]
                start_idx = np.where(y == cfg.PAD_TOKEN[self.source])[0][0]
                end_idx = np.where(y == cfg.PAD_TOKEN[self.target])[0][0]
                y = y[start_idx + 1: end_idx]
        
        return y


def run_tts():

    text_semantic_model = GPTModel(path='data/models/out_400b_ft_xs/text_semantic/',
                                   source=TEXT,
                                   target=SEMANTIC,
                                   device=device)

    semantic_acoustic_model = GPTModel(path='data/models/out_400b_ft_xs/semantic_acoustic/',
                                       source=SEMANTIC,
                                       target=ACOUSTIC,
                                       device=device)

    text = "THIS WAS THE BEST OF TIMES <PERIOD>"
    text_tokenizer = get_tokenizer(TEXT, device='cpu')
    text_tokens = np.asarray(text_tokenizer.encode(text)) + cfg.OFFSET[TEXT]
    
    text_tokens = np.append(text_tokens, cfg.PAD_TOKEN[TEXT])
    text_tokens = (torch.tensor(text_tokens, dtype=torch.long, device=device)[None, ...])
    semantic_tokens = text_semantic_model.generate(text_tokens)
    
    semantic_tokens = np.append(semantic_tokens, cfg.PAD_TOKEN[SEMANTIC])
    semantic_tokens = (torch.tensor(semantic_tokens, dtype=torch.long, device=device)[None, ...])
    acoustic_tokens = semantic_acoustic_model.generate(semantic_tokens)
    
    acoustic_tokenizer = get_tokenizer(ACOUSTIC, device='cpu')
    wav = acoustic_tokenizer.decode(torch.tensor(acoustic_tokens))
    save_audio(wav[0], f'tts.wav', sample_rate=24000)


if __name__ == "__main__":
    run_tts()