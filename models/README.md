# 本地大模型权重目录

本目录用于存放本地大模型权重文件，**不纳入版本控制**（见 `.gitignore`）。

## 支持的命名方式

加载时 `local_model.py` 会按以下顺序查找匹配的子目录：

| 优先级 | 命名方式 | 示例 |
|--------|---------|------|
| 1 | 短名（SUPPORTED_MODELS 键名） | `qwen2-5-7b/` |
| 2 | 短名横杠转点 | `qwen2.5-7b/` |
| 3 | HF 名（去掉组织前缀） | `Qwen2.5-7B-Instruct/` |
| 4 | HF 缓存名 | `Qwen__Qwen2.5-7B-Instruct/` |

命中任一目录且**包含 `config.json`** 即视为有效，使用本地路径加载（`local_files_only=True`，不联网）。

## 目录结构示例

```
models/
├── qwen2.5-7b/                    # 短名目录
│   ├── config.json                # 必需
│   ├── model.safetensors          # 或分片 pytorch_model-0000X-of-0000Y.bin
│   ├── tokenizer.json
│   ├── tokenizer_config.json
│   ├── generation_config.json
│   └── ...
├── Qwen2.5-VL-7B-Instruct/        # VL 视觉模型
│   ├── config.json
│   ├── model.safetensors
│   ├── preprocessor_config.json   # VL 模型专用
│   └── ...
└── README.md                      # 本文件（纳入版本控制）
```

## 获取模型权重

### 方式一：从 HuggingFace 下载（推荐）

```bash
# 安装 huggingface-cli
pip install huggingface_hub

# 下载到本地目录
huggingface-cli download Qwen/Qwen2.5-7B-Instruct \
    --local-dir ./models/qwen2.5-7b \
    --local-dir-use-symlinks False
```

### 方式二：从 ModelScope 下载（国内更快）

```bash
pip install modelscope
modelscope download --model Qwen/Qwen2.5-7B-Instruct \
    --local_dir ./models/qwen2.5-7b
```

### 方式三：从现有 HF 缓存复制

```bash
# HF 缓存默认路径
# Windows: %USERPROFILE%\.cache\huggingface\hub\models--Qwen--Qwen2.5-7B-Instruct\snapshots\<hash>\
# 将快照目录内容复制到 models/qwen2.5-7b/
```

## 支持的预设模型

| 短名 | HF ID | 类型 | 最小显存 |
|------|-------|------|---------|
| `qwen-7b` | Qwen/Qwen-7B-Chat | 文本 | 8GB |
| `qwen2-7b` | Qwen/Qwen2-7B-Instruct | 文本 | 8GB |
| `qwen2-5-7b` | Qwen/Qwen2.5-7B-Instruct | 文本 | 8GB |
| `glm4-9b` | THUDM/glm-4-9b-chat | 文本 | 10GB |
| `qwen2-5-vl-7b` | Qwen/Qwen2.5-VL-7B-Instruct | 视觉 | 12GB |
| `qwen2-5-vl-3b` | Qwen/Qwen2.5-VL-3B-Instruct | 视觉 | 6GB |

## 注意事项

- 模型文件体积大（7B 约 14GB），**不会被 git 跟踪**（已在 `.gitignore` 排除）
- 移植项目时需单独携带 `models/` 目录
- 如使用 4bit 量化，`bitsandbytes` 可用时会从原始模型动态量化（推荐），无需单独下载量化版
