# gpt-image

Generate and edit images from the terminal with **GPT Image 2.5** through your ChatGPT account. The default is `gpt-image-2.5-sunburst`. No OpenAI API key is required for this CLI.

The project is a small Python CLI for people who already use ChatGPT Plus, Pro, Business, or Enterprise. It authenticates with ChatGPT OAuth and sends image-generation requests through the ChatGPT Codex backend.

> **Important:** This CLI's ChatGPT OAuth route is separate from the public OpenAI API. The public API uses an API key and `api.openai.com`. The CLI uses a local OAuth token and `chatgpt.com/backend-api/codex/responses`.

## GPT Image 2.5 models

| Model | Role | Model ID | Snapshot |
| --- | --- | --- | --- |
| **Sunburst** | Default. Highest capability and editing precision. | `gpt-image-2.5-sunburst` | `gpt-image-2.5-sunburst-2026-09-08` |
| **Flare** | Secondary option. Fastest high-quality everyday generation. | `gpt-image-2.5-flare` | `gpt-image-2.5-flare-2026-09-08` |

Both models accept text and image inputs and return image outputs. They support generation, editing, inpainting, transparent PNG/WebP output, flexible dimensions, and quality levels from `low` through `max`.

GPT Image 2.5 quality levels:

- `low`
- `medium`
- `high`
- `xhigh`
- `max`
- `auto`

This CLI defaults to `auto`, matching the current API guidance. Use `high`, `xhigh`, or `max` when you want to choose the quality explicitly.

## What you need

- Python 3.10 or newer
- A ChatGPT Plus, Pro, Business, or Enterprise account
- About two minutes for the first login

## Install

Clone the repository and install it locally:

```bash
git clone https://github.com/hffmnnj/gpt-image-cli.git
cd gpt-image-cli
pip install -e .
```

To make the command available globally from the local environment:

```bash
ln -sf "$(pwd)/.venv/bin/gpt-image" ~/.local/bin/gpt-image
```

## Authenticate

Browser login:

```bash
gpt-image login --open-browser
```

Without `--open-browser`, the CLI prints the authorization URL. On a headless machine, use the device-code flow:

```bash
gpt-image login --device-code
```

The OAuth token is stored at `~/.gpt-image/auth.json` with restrictive file permissions. Set `GPT_IMAGE_AUTH_FILE` to use another location.

Check local authentication without making an image request:

```bash
gpt-image auth-status
```

## Generate images

The default call uses Sunburst:

```bash
gpt-image generate \
  --prompt "a titanium smart ring on dark marble" \
  --out ring.png
```

Use Flare for faster everyday generation:

```bash
gpt-image generate \
  --model gpt-image-2.5-flare \
  --prompt "a watercolor fox reading in a library" \
  --out fox.png
```

Pin the dated Sunburst snapshot for reproducible behavior:

```bash
gpt-image generate \
  --model gpt-image-2.5-sunburst-2026-09-08 \
  --quality high \
  --prompt "a clean studio photograph of a titanium ring" \
  --out ring.png
```

Use a higher quality level for a final asset:

```bash
gpt-image generate \
  --quality max \
  --prompt "a cinematic product photograph of a titanium smart ring on black stone" \
  --out final.png
```

## Edit and reference images

Edit an existing image:

```bash
gpt-image generate \
  --image ./sketch.png \
  --action edit \
  --prompt "turn this into a clean vector illustration with flat colors" \
  --out final.png
```

Use one or more images as references for a new generation:

```bash
gpt-image generate \
  --reference-image ./style.png \
  --reference-image ./subject.png \
  --action generate \
  --prompt "a portrait of a corgi using the subject identity and the style of the reference" \
  --out corgi.png
```

The CLI serializes input and reference images as standard `input_image` content parts. `--reference-image` is a clearer CLI name for the same underlying image-input mechanism. Up to five input images are accepted.

## Transparent backgrounds and output formats

GPT Image 2.5 supports transparent output. Use PNG or WebP:

```bash
gpt-image generate \
  --background transparent \
  --output-format png \
  --prompt "a simple red circle sticker" \
  --out circle.png
```

Supported output formats are `png`, `jpeg`, and `webp`. JPEG and WebP can use `--output-compression 0-100`.

## Sizes

GPT Image 2.5 supports the recommended sizes `1024x1024`, `1536x1024`, and `1024x1536`, plus custom dimensions.

For custom dimensions:

- Width and height must be multiples of 16
- The long-to-short ratio must be at most 3:1
- Neither edge may exceed 3840 pixels
- Total pixels must be between 655,360 and 8,294,400
- Resolutions above 2560x1440 are experimental

Example:

```bash
gpt-image generate \
  --size 1536x864 \
  --prompt "a wide editorial illustration of a quiet desert road" \
  --out desert.png
```

## Preview a request without sending it

Use `--dry-run` to inspect the request shape and selected model without using your account:

```bash
gpt-image generate \
  --quality xhigh \
  --prompt "test" \
  --dry-run
```

The dry-run output includes the ChatGPT backend URL, conversation model, image model, size, quality, output format, input count, and requested image count.

## Commands

- `gpt-image login` authenticates through ChatGPT OAuth
- `gpt-image login --device-code` uses a copy-and-paste device code
- `gpt-image auth-status` checks local authentication
- `gpt-image generate` generates or edits images

## `generate` flags

| Flag | Description |
| --- | --- |
| `--prompt`, `-p` | Prompt text. Required unless `--prompt-file` is used. |
| `--prompt-file` | Read the prompt from a file. |
| `--image`, `-i` | Input image for editing or context. Repeatable. |
| `--reference-image`, `-r` | Reference image for style or content guidance. Repeatable. |
| `--action` | `generate`, `edit`, or `auto`. |
| `--model` | Defaults to `gpt-image-2.5-sunburst`. Flare, dated 2.5 snapshots, `gpt-image-2`, and `gpt-image-1.5` are supported. |
| `--responses-model` | Conversation model used by the Responses request. Defaults to `gpt-5.5`. |
| `--detail` | Input image detail: `low`, `high`, `auto`, or `original`. |
| `--quality` | `low`, `medium`, `high`, `xhigh`, `max`, or `auto`. Defaults to `auto`. |
| `--size` | `auto`, a recommended size, or a valid custom `WIDTHxHEIGHT`. |
| `--output-format` | `png`, `jpeg`, or `webp`. |
| `--output-compression` | Compression level from 0 to 100 for JPEG and WebP. |
| `--background` | `transparent`, `opaque`, or `auto`. |
| `--moderation` | `auto` or `low`. |
| `--partial-images` | Stream 0 to 3 partial previews. |
| `--input-image-mask` | Mask file for inpainting or editing. |
| `--count` | Number of images from 1 to 4. |
| `--out`, `-o` | Output path. Defaults to `output.png`. |
| `--timeout` | Request timeout in seconds. Defaults to 180. |
| `--dry-run` | Print the request shape without sending it. |
| `--login-if-missing` | Start login if local auth is unavailable. |

## Environment variables

- `GPT_IMAGE_AUTH_FILE`: custom OAuth auth file path
- `GPT_IMAGE_BASE_URL`: alternate ChatGPT backend base URL
- `GPT_IMAGE_MODEL`: default image model override
- `GPT_IMAGE_RESPONSES_MODEL`: default Responses conversation model override

## How the CLI calls GPT Image 2.5

The CLI sends a streaming Responses request to the ChatGPT Codex backend. The conversation model and image model are separate:

```json
{
  "model": "gpt-5.5",
  "input": [
    {
      "role": "user",
      "content": [
        {"type": "input_text", "text": "a titanium smart ring on dark marble"}
      ]
    }
  ],
  "tools": [
    {
      "type": "image_generation",
      "model": "gpt-image-2.5-sunburst",
      "size": "1024x1024",
      "quality": "auto"
    }
  ],
  "tool_choice": {"type": "image_generation"},
  "stream": true,
  "store": false
}
```

The response contains an `image_generation_call` item with a base64 image result. The CLI decodes that result and writes it to the requested output path.

This backend path is the same general image-generation mechanism used by Codex, but the current upstream Codex source still hardcodes `gpt-image-2`. This project explicitly selects the documented GPT Image 2.5 model in the tool payload instead of inheriting that older constant.

## Calling GPT Image 2.5 through the public OpenAI API

For applications using API-key billing, call the public Images API directly. Sunburst is the precision-oriented model and Flare is the faster secondary option.

Python:

```python
from openai import OpenAI
import base64

client = OpenAI()
result = client.images.generate(
    model="gpt-image-2.5-sunburst",
    prompt="A children's book drawing of a veterinarian listening to a baby otter's heartbeat",
)

with open("otter.png", "wb") as f:
    f.write(base64.b64decode(result.data[0].b64_json))
```

HTTP:

```bash
curl -X POST "https://api.openai.com/v1/images/generations" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-image-2.5-sunburst",
    "prompt": "A watercolor robot reading in a library",
    "quality": "high",
    "size": "1024x1024",
    "output_format": "png"
  }'
```

For an existing image, use `POST /v1/images/edits`. The Responses API can also attach GPT Image 2.5 as a tool model while a supported mainline model handles the conversation:

```python
response = client.responses.create(
    model="<supported-mainline-model>",
    input="Generate a gray tabby cat hugging an otter with an orange scarf",
    tools=[
        {
            "type": "image_generation",
            "model": "gpt-image-2.5-sunburst",
        }
    ],
)
```

The public API models are billed by tokens. Current documented GPT Image 2.5 rates are $8 per million image input tokens, $2 per million cached image input tokens, and $30 per million image output tokens. That pricing does not apply to the ChatGPT OAuth usage path in this CLI.

## Official references

- [GPT Image 2.5 Sunburst model](https://developers.openai.com/api/docs/models/gpt-image-2.5-sunburst)
- [GPT Image 2.5 Flare model](https://developers.openai.com/api/docs/models/gpt-image-2.5-flare)
- [Image generation guide](https://developers.openai.com/api/docs/guides/image-generation)
- [OpenAI API pricing](https://developers.openai.com/api/docs/pricing)
- [Codex image-generation implementation](https://github.com/openai/codex/blob/main/codex-rs/ext/image-generation/src/tool.rs)

## License

MIT
