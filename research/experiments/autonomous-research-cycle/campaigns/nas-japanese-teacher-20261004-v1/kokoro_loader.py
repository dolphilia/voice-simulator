"""既存load_teacherの算術を保持し旧budget importだけを除く。"""
from paths import *
import sys,os,types
def load_teacher():
    packages = PILOT / '.cache/packages'
    sys.path.insert(0, str(packages))
    os.environ['HF_HUB_OFFLINE'] = '1'
    package = types.ModuleType('kokoro')
    package.__path__ = [str(packages / 'kokoro')]
    sys.modules['kokoro'] = package
    from kokoro.model import KModel
    from misaki.ja import JAG2P
    import torch
    from loguru import logger
    logger.disable('kokoro')
    torch.set_num_threads(4)
    model = KModel(repo_id='hexgrad/Kokoro-82M', config=str(PILOT / '.cache/teacher/config.json'), model=str(PILOT / '.cache/teacher/kokoro-v1_0.pth')).cpu().eval()
    checkpoint = torch.load(PILOT / '.cache/teacher/kokoro-v1_0.pth', map_location='cpu', weights_only=True)
    load_audit = {}
    for name, state in checkpoint.items():
        if all((key.startswith('module.') for key in state)):
            state = {key[7:]: value for key, value in state.items()}
        actual = getattr(model, name).state_dict()
        missing = sorted(set(state) - set(actual))
        extra = sorted(set(actual) - set(state))
        changed = [key for key in state.keys() & actual.keys() if not torch.equal(state[key], actual[key])]
        identity = []
        for key in extra:
            module_name, field = key.rsplit('.', 1)
            module = getattr(model, name).get_submodule(module_name)
            if isinstance(module, torch.nn.InstanceNorm1d) and field in ('weight', 'bias'):
                expected = torch.ones_like(actual[key]) if field == 'weight' else torch.zeros_like(actual[key])
                if torch.equal(actual[key], expected):
                    identity.append(key)
        if missing or changed or set(extra) != set(identity):
            raise ValueError(f'教師の重み読込が完全一致しません: {name}, missing={missing}, extra={extra}, changed={changed}')
        load_audit[name] = {'checkpoint_tensors_equal': len(state), 'added_identity_affine': identity}
    model.load_audit = load_audit
    voice = torch.load(PILOT / '.cache/teacher/voices/jf_alpha.pt', map_location='cpu', weights_only=True)
    return (model, voice, JAG2P())
