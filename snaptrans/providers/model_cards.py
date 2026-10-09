"""Verified NVIDIA model-specific output settings; context size is not output size."""
CARDS = {
    'deepseek-ai/deepseek-v4.1-flash': dict(tokens=262144, limit=1048576, limit_verified=False, extra={},
        url='https://build.nvidia.com/deepseek-ai/deepseek-v4.1-flash/build'),
    'nvidia/nemotron-3-super-120b-a12b': dict(tokens=16384, limit=32768,
        extra={'reasoning_effort': 'none'},
        url='https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-super-120b-a12b-infer'),
    'nvidia/nemotron-3.5-lightning-30b-a3b': dict(tokens=16384, limit=32768,
        extra={'chat_template_kwargs': {'enable_thinking': False}},
        url='https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-5-lightning-30b-a3b-infer'),
    'moonshotai/kimi-k3': dict(tokens=16384, limit=1048576, limit_verified=False,
        extra={'reasoning_effort': 'low'}, url='https://build.nvidia.com/moonshotai/kimi-k3'),
    'z-ai/glm-5.3-flash': dict(tokens=1024, limit=1048576, limit_verified=False,
        extra={'temperature': 0.5, 'top_p': 1}, url='https://build.nvidia.com/z-ai/glm-5-3-flash'),
    'nvidia/nemotron-3-nano-omni-30b-a3b-reasoning': dict(tokens=1024, limit=65536,
        extra={'chat_template_kwargs': {'enable_thinking': False}},
        url='https://build.nvidia.com/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning/modelcard'),
}
VISION_MODEL = 'nvidia/nemotron-3-nano-omni-30b-a3b-reasoning'
DEFAULT_MODEL = 'nvidia/nemotron-3-super-120b-a12b'


def model_card(model):
    return CARDS.get(model.strip(), dict(tokens=0, limit=1048576, extra={}, url='https://build.nvidia.com/models'))
