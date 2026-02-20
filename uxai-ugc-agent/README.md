# UX·AI UGC Content Agent (uxai-ugc-agent)

A multi-agent automation system designed to research, write, and produce high-impact short-form video content specifically for the UX/AI talent recruitment space.

## Prerequisites
- **Python 3.11+**
- **FFmpeg**: Essential for video assembly and technical QA.
  - Ubuntu/Debian: `sudo apt update && sudo apt install -y ffmpeg libgl1`
  - macOS: `brew install ffmpeg`
- **Git**: To clone the repository.

## Quick Start

1. **Clone & Setup Environment**:
   ```bash
   git clone <repository-url>
   cd uxai-ugc-agent
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configure API Keys**:
   Copy `.env.example` to `.env` and fill in your keys:
   ```bash
   cp .env.example .env
   # Edit .env with your favorite editor
   ```

3. **Launch the Dashboard**:
   ```bash
   python main.py --web
   ```
   The browser will automatically open at `http://localhost:5000`.

## API Keys Guide

| Service | Purpose | Source |
| :--- | :--- | :--- |
| **OpenRouter** | LLM (Claude-3-Sonnet/Haiku) | [openrouter.ai](https://openrouter.ai/) |
| **ElevenLabs** | Ultra-realistic voice generation | [elevenlabs.io](https://elevenlabs.io/) |
| **HeyGen** | AI Avatar video generation | [heygen.com](https://heygen.com/) |
| **OpenAI** | DALL-E 3 background images | [platform.openai.com](https://platform.openai.com/) |
| **Reddit** | Researching trending pain points | [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) |

## VM Setup (Target: 4GB RAM)

This system is specifically optimized for low-memory environments:
- **Sequential Processing**: Agents process media clips one-by-one to keep RAM usage stable.
- **FFmpeg Assembly**: Direct subprocess calls are used instead of heavy python libraries for large video concatenations.
- **Memory Guard**: Internal monitoring pauses the pipeline if available RAM drops below 600MB.

**Recommended System Check**:
```bash
# Check available memory
free -h

# Ensure FFmpeg is available
ffmpeg -version
```

## Running Modes

- **Web Dashboard**: `python main.py --web` (Recommended)
- **Headless CLI**: `python main.py --run "The future of AI in UX Research"`
- **Health Check**: `curl http://localhost:5000/api/health`

## Customization

### Prompt Engineering
You can customize the "brain" of each agent without touching any Python code. Edit the JSON files in the `/prompts` directory:
- `researcher_prompts.json`: Market analysis and trend synthesis.
- `writer_prompts.json`: Viral ideation and script segment rules.
- `qa_prompts.json`: Quality thresholds and review criteria.

### Pipeline Behavior
Adjust thresholds in `.env` or via the web Settings modal:
- `QA_AUTO_APPROVE_THRESHOLD`: Set to 8.0+ for higher quality, 7.0 for faster output.
- `MAX_QA_ITERATIONS`: How many times the agent should try to fix a script before giving up.
- `HUMAN_REVIEW_TIMEOUT_SECONDS`: How long the dashboard waits for your input before auto-continuing.

## Troubleshooting

- **Memory Errors**: If a step fails with a memory error, ensure no other heavy processes are running on the VM. The assembly step requires at least 600MB of free RAM.
- **HeyGen Timeouts**: Generation can take 5-10 minutes. If it consistently times out, check your HeyGen credit balance.
- **Log Files**: Check `/output/{session_id}/pipeline.log` for a detailed audit trail of every agent's internal reasoning.
