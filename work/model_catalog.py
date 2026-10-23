"""Audited model files, pinned to a specific upstream revision; no remote Python."""
CATALOG = {
    'qwen35-4b': {
        'id': 'qwen35-4b', 'name': 'Qwen3.5 4B · 4-bit',
        'description': '补充画面描述、主题和内容标签。约 3.1 GB，适合 Apple Silicon Mac。',
        'repo': 'lmstudio-community/Qwen3.5-4B-MLX-4bit',
        'revision': 'c43ee1d65576a5d98de1e8405cac93c371a655c1',
        'directory': 'Qwen3.5-4B-MLX-4bit', 'license': 'Apache-2.0',
        'files': [
            ('README.md', 2253, 'git-sha1', '76b09d566439f90b3fc8c03b79b328983a938281'),
            ('chat_template.jinja', 7756, 'git-sha1', 'a585dec894e63da457d9440ec6aa7caa16d20860'),
            ('config.json', 3366, 'git-sha1', 'cb3e1a878a5c4a0505e0c9967da45820b2ca6bd3'),
            ('model.safetensors', 3034301037, 'sha256', '52dc943eaf6093a2313271a7a0abc36d127b2a16609a0a7c54ee1b4e4ed06cb8'),
            ('model.safetensors.index.json', 101944, 'git-sha1', '40196ba58595ef9b3fad25a8a6daf3288b953c19'),
            ('preprocessor_config.json', 390, 'git-sha1', '2ea84a437d448ff71b08df68fdd949d5cc4ebb64'),
            ('processor_config.json', 991, 'git-sha1', '8f29fe38a79a9d8367009ebebd25c35b1f3c4e40'),
            ('tokenizer.json', 19989325, 'sha256', '06b9509352d2af50381ab2247e083b80d32d5c0aba91c272ca9ff729b6a0e523'),
            ('tokenizer_config.json', 9187, 'git-sha1', '803283d87369d6d9ff8d970a8a49a602ca306544'),
            ('video_preprocessor_config.json', 385, 'git-sha1', '3ba673a5ad7d4d13f54155ecd38b2a94a6dac8fe'),
            ('vocab.json', 6722759, 'git-sha1', '0aa0ce0658d60ac4a5d609f4eadb0e8e43514176'),
        ],
    },
}
