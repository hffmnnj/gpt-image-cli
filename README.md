# gpt-image

Generate images with GPT Image 2 from the terminal. No API key, no credits, no setup. Just your ChatGPT account.

I built this because I got tired of copy-pasting prompts into ChatGPT's web UI every time I needed a product shot or a quick illustration. The CLI is faster, and it bills against your existing Plus or Pro plan instead of burning through API credits.

## What you need

- Python 3.10 or newer
- A ChatGPT Plus, Pro, Business, or Enterprise account
- About two minutes for the one-time login

## Install

Clone the repo and install it locally:

```bash
git clone https://github.com/hffmnnj/gpt-image-cli.git
cd gpt-image-cli
pip install -e .
```

That's it. No PyPI package. If you want it globally available, link the binary:

```bash
ln -sf $(pwd)/.venv/bin/gpt-image ~/.local/bin/gpt-image
```

## First-time login

```bash
gpt-image login
```

This opens your browser, you click Connect, and the token comes back automatically. If you're on a headless server, add `--device-code` and paste the code instead.

Your token lives in `~/.gpt-image/auth.json`. If you already use Codex CLI, we can read from `~/.codex/auth.json` too. Point us anywhere with `GPT_IMAGE_AUTH_FILE`.

## Generating images

The simplest possible command:

```bash
gpt-image generate --prompt "a titanium smart ring on dark marble" --out ring.png
```

Edit an existing image:

```bash
gpt-image generate \
  --image ./sketch.png \
  --prompt "turn this into a clean vector illustration, flat colors" \
  --out final.png
```

Transparent background for stickers or overlays:

```bash
gpt-image generate \
  --model gpt-image-1.5 \
  --background transparent \
  --output-format png \
  --prompt "a simple red circle" \
  --out circle.png
```

See what the request will look like without actually sending it:

```bash
gpt-image generate --prompt "test" --dry-run
```

## Commands

- `gpt-image login` -- Authenticate via ChatGPT OAuth
- `gpt-image login --device-code` -- Same thing, but with a copy-paste code for headless machines
- `gpt-image auth-status` -- Check if your token is still valid
- `gpt-image generate` -- Generate or edit an image

## Flags for generate

- `--prompt`, `-p` -- What you want to see (required)
- `--prompt-file` -- Read the prompt from a file instead
- `--image`, `-i` -- Reference image for editing. You can pass this up to five times
- `--out`, `-o` -- Where to save the result. Defaults to `output.png`
- `--model` -- `gpt-image-2` (default) or `gpt-image-1.5`
- `--responses-model` -- Which model handles the conversation layer. Default is `gpt-5.5`
- `--size` -- `1024x1024` (default), `1536x1024`, `1024x1536`, or `auto`
- `--quality` -- `low`, `medium`, `high` (default), or `auto`
- `--output-format` -- `png` (default), `jpeg`, or `webp`
- `--background` -- `transparent`, `opaque`, or `auto`. Needs `gpt-image-1.5`
- `--count` -- How many images, from 1 to 4. Default is 1
- `--timeout` -- Seconds to wait for a response. Default is 180
- `--dry-run` -- Print the request shape and exit
- `--login-if-missing` -- Auto-trigger login if no token is found

## Environment variables

- `GPT_IMAGE_AUTH_FILE` -- Custom path to your auth JSON
- `GPT_IMAGE_BASE_URL` -- If you need to hit a different backend
- `GPT_IMAGE_MODEL` -- Default image model
- `GPT_IMAGE_RESPONSES_MODEL` -- Default responses model

## How it works

1. The login step uses OpenAI's OAuth flow with PKCE and a localhost callback. Same protocol Codex CLI uses.
2. Your access token gets written to `~/.gpt-image/auth.json` with `0600` permissions.
3. Generation calls `chatgpt.com/backend-api/codex/responses` with the `image_generation` tool.
4. The response streams back as SSE events. We pull out the base64 image data and write it to disk.

No API key ever touches the wire. Usage counts against your ChatGPT subscription.

## License

MIT
