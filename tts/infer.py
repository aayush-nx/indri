import numpy as np
import torch
from pathlib import Path

from encodec.utils import save_audio

from tts.gpt2_model import get_model
from tts.train import DataLoader
from common import SEMANTIC, TEXT, ACOUSTIC, device, ctx
from common import Config as cfg
from datalib.tokenlib import get_tokenizer


def load_model(path):
    model = get_model(vocab_size=cfg.VOCAB_SIZE, 
                      device=device, 
                      compile=False, 
                      path=path)

    model.eval()
    return model

def extract_new_tokens(y, target):
    start_idx = np.where(y == cfg.INFER_TOKEN[target])[0]
    end_idx = np.where(y == cfg.STOP_TOKEN[target])[0]
    if end_idx.any():
        y = y[start_idx[0] + 1: end_idx[0]]
    else:
        y = y[start_idx[0] + 1:]

    return y

def generate(model, source, target, source_tokens):
    source_tokens = DataLoader.prepare_source(source_tokens,
                                            source=source,
                                            max_source_tokens=cfg.max_source_tokens)
    
    prompt_arr = DataLoader.prepare_prompt(prompt=None,
                                            target=target,
                                            prompt_length=0)
    
    source_tokens = np.hstack([source_tokens, prompt_arr, cfg.INFER_TOKEN[target]])
    input_tokens = (torch.tensor(source_tokens,
                                dtype=torch.long,
                                device=device)[None, ...])
    
    
    with torch.no_grad():
        with ctx:
            target_tokens = model.generate(input_tokens, 
                                1024, 
                                temperature=0.8,
                                top_k=100, 
                                stop_token=cfg.STOP_TOKEN[target])
            
            target_tokens = target_tokens.detach().cpu().numpy()[0]

    target_tokens = extract_new_tokens(target_tokens, target=target)
        
    target_tokens = target_tokens - cfg.OFFSET[target]
    return target_tokens

def run_tts():
    Path('samples').mkdir(exist_ok=True)
    
    from huggingface_hub import snapshot_download
    snapshot_download('cmeraki/tts_en_xl_30m', local_dir='data/models/tts_en_xl_30m/')

    text_semantic_model = load_model(path='data/models/tts_en_xl_30m/text_semantic/gpt_last.pt')

    semantic_acoustic_model = load_model(path='data/models/tts_en_xl_30m/semantic_acoustic/gpt_last.pt')

    text = "MIGHT ACTUALLY BE A TREATMENT FOR AILING HEARTS <PERIOD>".lower()
    text_tokenizer = get_tokenizer(TEXT, device='cpu')
    text_tokens = np.asarray(text_tokenizer.encode(text))

    acoustic_tokenizer = get_tokenizer(ACOUSTIC, device='cpu')
    
    for i in range(100):
        semantic_tokens = generate(model=text_semantic_model, 
                                   source_tokens=text_tokens, 
                                   source=TEXT, 
                                   target=SEMANTIC)
        
        acoustic_tokens = generate(model=semantic_acoustic_model, 
                                   source_tokens=semantic_tokens, 
                                   source=SEMANTIC, 
                                   target=ACOUSTIC)

        wav = acoustic_tokenizer.decode(torch.tensor(acoustic_tokens))
        
        save_audio(wav[0], f'samples/tts_{i}.wav', sample_rate=24000)


if __name__ == "__main__":
    run_tts()