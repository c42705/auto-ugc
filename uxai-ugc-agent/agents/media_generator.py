"""
Media Generator Agent responsible for creating audio, images, and videos.
Optimized for low-memory environments (4GB RAM VM) using sequential processing
and FFmpeg subprocesses for assembly.
"""

import os
import json
import time
import subprocess
import requests
from typing import List, Dict, Any, Optional
from PIL import Image, ImageDraw, ImageFont
from openai import OpenAI
from elevenlabs.client import ElevenLabs
from config import config
from utils.llm_client import LLMClient
from utils.notifier import notifier
from utils.memory_guard import memory_guard
from utils.logger import log

class MediaGeneratorAgent:
    def __init__(self):
        self.log = log
        self.notifier = notifier
        self.memory_guard = memory_guard
        
        # API Keys & IDs
        self.heygen_api_key = config.HEYGEN_API_KEY
        self.heygen_avatar_id = config.HEYGEN_AVATAR_ID
        self.resolution = config.PROCESSING_RESOLUTION
        
        # Client Initialization
        self.el_client = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)
        self.openai_client = OpenAI(api_key=config.OPENAI_API_KEY)
        
        self._check_ffmpeg()

    def generate_voiceover(self, script_segments: List[Dict[str, Any]], session_path: str) -> List[str]:
        """
        Generate one MP3 per segment using ElevenLabs.
        """
        self.log.info("Generating voiceovers with ElevenLabs...", context="MediaGeneratorAgent")
        audio_dir = os.path.join(session_path, "audio")
        os.makedirs(audio_dir, exist_ok=True)
        
        audio_paths = []
        for i, segment in enumerate(script_segments):
            text = segment.get("text", "")
            if not text:
                continue
                
            output_path = os.path.join(audio_dir, f"segment_{i}.mp3")
            
            try:
                audio_it = self.el_client.text_to_speech.convert(
                    voice_id=config.ELEVENLABS_VOICE_ID,
                    text=text,
                    model_id="eleven_multilingual_v2",
                    output_format="mp3_44100_128"
                )
                
                with open(output_path, "wb") as f:
                    for chunk in audio_it:
                        f.write(chunk)
                
                audio_paths.append(output_path)
                self.log.info(f"Generated audio for segment {i}", context="MediaGeneratorAgent")
            except Exception as e:
                self.log.error(f"Failed to generate audio for segment {i}: {e}", context="MediaGeneratorAgent")
                raise

        self.notifier.send(title="Audio Complete", message=f"Generated {len(audio_paths)} voiceover segments.", tags=["speaker"])
        return audio_paths

    def generate_background_images(self, script_segments: List[Dict[str, Any]], session_path: str) -> List[str]:
        """
        Generate vertical background images using DALL-E 3.
        """
        self.log.info("Generating background images with DALL-E 3...", context="MediaGeneratorAgent")
        img_dir = os.path.join(session_path, "images")
        os.makedirs(img_dir, exist_ok=True)
        
        image_paths = []
        prefix = "Professional B2B social media visual, clean modern design, corporate minimal LinkedIn aesthetic, no people, no text, subtle tech/design mood. Scene: "
        
        for i, segment in enumerate(script_segments):
            visual_note = segment.get("visual_suggestion", "Modern tech office background")
            output_path = os.path.join(img_dir, f"bg_{i}.png")
            
            try:
                response = self.openai_client.images.generate(
                    model="dall-e-3",
                    prompt=f"{prefix}{visual_note}",
                    size="1024x1792",
                    quality="standard",
                    n=1
                )
                
                img_url = response.data[0].url
                img_data = requests.get(img_url).content
                with open(output_path, "wb") as f:
                    f.write(img_data)
                
                image_paths.append(output_path)
                self.log.info(f"Generated image for segment {i}", context="MediaGeneratorAgent")
            except Exception as e:
                self.log.warning(f"DALL-E failed for segment {i}: {e}. Using fallback color.", context="MediaGeneratorAgent")
                # Create a solid color fallback image
                fallback_img = Image.new('RGB', (1024, 1792), color='#1a1a2e')
                fallback_img.save(output_path)
                image_paths.append(output_path)

        return image_paths

    def generate_avatar_clips(self, script_segments: List[Dict[str, Any]], audio_paths: List[str], session_path: str) -> List[str]:
        """
        Generate video clips using HeyGen API v2. Processes segments ONE AT A TIME.
        """
        self.log.info("Generating avatar clips with HeyGen (Sequential)...", context="MediaGeneratorAgent")
        clips_dir = os.path.join(session_path, "clips")
        os.makedirs(clips_dir, exist_ok=True)
        
        clip_paths = []
        headers = {
            "X-Api-Key": self.heygen_api_key,
            "Content-Type": "application/json"
        }

        for i, (segment, audio_path) in enumerate(zip(script_segments, audio_paths)):
            self.log.info(f"Processing HeyGen clip {i+1}/{len(script_segments)}", context="MediaGeneratorAgent")
            
            # 1. Upload audio to HeyGen
            try:
                # HeyGen v2 audio upload
                upload_url = "https://api.heygen.com/v1/asset.upload" # v1 still used for assets often
                with open(audio_path, "rb") as f:
                    files = {'file': (os.path.basename(audio_path), f, 'audio/mpeg')}
                    resp = requests.post(upload_url, headers={"X-Api-Key": self.heygen_api_key}, files=files)
                    asset_id = resp.json().get("data", {}).get("id")
                    if not asset_id:
                         raise Exception(f"Failed to upload audio: {resp.text}")
                
                # 2. Generate Video
                gen_url = "https://api.heygen.com/v2/video/generate"
                payload = {
                    "video_inputs": [{
                        "character": {
                            "type": "avatar", 
                            "avatar_id": self.heygen_avatar_id,
                            "avatar_style": "normal"
                        },
                        "voice": {
                            "type": "audio", 
                            "audio_asset_id": asset_id
                        },
                        "background": {"type": "color", "value": "#1a1a2e"}
                    }],
                    "dimension": {"width": 720, "height": 1280},
                    "aspect_ratio": "9:16"
                }
                
                gen_resp = requests.post(gen_url, headers=headers, json=payload)
                video_id = gen_resp.json().get("data", {}).get("video_id")
                if not video_id:
                    raise Exception(f"Failed to trigger video generation: {gen_resp.text}")

                # 3. Poll for completion
                self.log.info(f"Polling for video {video_id}...", context="MediaGeneratorAgent")
                status_url = f"https://api.heygen.com/v1/video_status.get?video_id={video_id}"
                
                start_time = time.time()
                clip_file = os.path.join(clips_dir, f"clip_{i}.mp4")
                completed = False
                
                while time.time() - start_time < 900: # 15 mins timeout
                    status_resp = requests.get(status_url, headers=headers)
                    status_data = status_resp.json().get("data", {})
                    status = status_data.get("status")
                    
                    if status == "completed":
                        video_url = status_data.get("video_url")
                        video_data = requests.get(video_url).content
                        with open(clip_file, "wb") as f:
                            f.write(video_data)
                        clip_paths.append(clip_file)
                        completed = True
                        break
                    elif status == "failed":
                        raise Exception(f"HeyGen generation failed: {status_data.get('error')}")
                    
                    time.sleep(15)
                
                if not completed:
                    raise Exception(f"HeyGen generation timed out for segment {i}")

                self.notifier.send(title="HeyGen Progress", message=f"Clip {i+1}/{len(script_segments)} done.", tags=["movie_camera"])

            except Exception as e:
                self.log.error(f"Error in HeyGen segment {i}: {e}", context="MediaGeneratorAgent")
                # Fallback or re-raise? Re-raising to block pipeline if core media fails
                raise

        return clip_paths

    def assemble_final_video(self, clips: List[str], images: List[str], script: Dict[str, Any], session_path: str) -> Dict[str, Any]:
        """
        Assemble final video using FFmpeg. Sequential and memory-safe.
        """
        self.log.info("Starting FFmpeg assembly...", context="MediaGeneratorAgent")
        self.memory_guard.require(600, context="FFmpeg Assembly")
        
        ffmpeg_log_path = os.path.join(session_path, "ffmpeg.log")
        
        # 1. Create Concat List
        concat_file = os.path.join(session_path, "concat_list.txt")
        with open(concat_file, "w") as f:
            for clip in clips:
                f.write(f"file '{clip}'\n")
        
        # 2. Concat
        raw_output = os.path.join(session_path, "assembled_raw.mp4")
        concat_cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26",
            "-c:a", "aac", "-b:a", "128k", "-threads", "3", raw_output
        ]
        
        with open(ffmpeg_log_path, "a") as log_file:
            subprocess.run(concat_cmd, stdout=log_file, stderr=log_file, check=True)

        # 3. Add Text Overlays
        # For simplicity in this scaffold, we'll apply one main filter string
        # Real implementation would calculate timestamps based on segment durations
        final_720p = os.path.join(session_path, "final_720p.mp4")
        
        filter_complex = []
        current_time = 0.0
        for segment in script.get("segments", []):
            text = segment.get("on_screen_text", "").replace("'", "\\'").replace(":", "\\:")
            duration = segment.get("duration_seconds", 0)
            if text:
                drawtext = f"drawtext=text='{text}':fontcolor=white:fontsize=48:box=1:boxcolor=black@0.5:boxborderw=5:x=(w-text_w)/2:y=h-200:enable='between(t,{current_time},{current_time+duration})'"
                filter_complex.append(drawtext)
            current_time += duration

        overlay_cmd = ["ffmpeg", "-y", "-i", raw_output]
        if filter_complex:
            overlay_cmd += ["-vf", ",".join(filter_complex)]
        overlay_cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-c:a", "copy", final_720p]
        
        with open(ffmpeg_log_path, "a") as log_file:
            subprocess.run(overlay_cmd, stdout=log_file, stderr=log_file, check=True)

        # 4. Create Square Version
        final_square = os.path.join(session_path, "final_square.mp4")
        square_cmd = [
            "ffmpeg", "-y", "-i", final_720p,
            "-vf", "scale=720:720:force_original_aspect_ratio=decrease,pad=720:720:(ow-iw)/2:(oh-ih)/2:color=#1a1a2e",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26", final_square
        ]
        with open(ffmpeg_log_path, "a") as log_file:
            subprocess.run(square_cmd, stdout=log_file, stderr=log_file, check=True)

        # Output resolution scaling if requested
        vertical_1080p = None
        if self.resolution == 1080:
            vertical_1080p = os.path.join(session_path, "final_1080p.mp4")
            scale_cmd = ["ffmpeg", "-y", "-i", final_720p, "-vf", "scale=1080:1920", "-c:v", "libx264", "-preset", "slow", "-crf", "23", vertical_1080p]
            with open(ffmpeg_log_path, "a") as log_file:
                subprocess.run(scale_cmd, stdout=log_file, stderr=log_file, check=True)

        return {
            "vertical_720p": final_720p,
            "vertical_1080p": vertical_1080p,
            "square": final_square,
            "duration_seconds": current_time,
            "file_sizes_mb": {
                "720p": os.path.getsize(final_720p) / (1024*1024),
                "square": os.path.getsize(final_square) / (1024*1024)
            }
        }

    def create_thumbnail(self, image_path: str, text: str, session_path: str) -> str:
        """
        Create a high-impact thumbnail using Pillow.
        """
        self.log.info("Creating thumbnail...", context="MediaGeneratorAgent")
        try:
            img = Image.open(image_path).convert("RGB")
            img = img.resize((1080, 1920), Image.Resampling.LANCZOS)
            
            draw = ImageDraw.Draw(img, "RGBA")
            
            # Dark gradient at the bottom for text readability
            gradient = Image.new("RGBA", (1080, 600), (0, 0, 0, 0))
            g_draw = ImageDraw.Draw(gradient)
            for y in range(600):
                alpha = int((y / 600) * 180)
                g_draw.line([(0, y), (1080, y)], fill=(0, 0, 0, alpha))
            img.paste(gradient, (0, 1320), gradient)
            
            # Add text (simplified - would normally load a specific font)
            # draw.text((540, 1600), text, fill="white", anchor="mm")
            
            output_path = os.path.join(session_path, "thumbnail.jpg")
            img.save(output_path, "JPEG", quality=85)
            return output_path
        except Exception as e:
            self.log.warning(f"Failed to create thumbnail: {e}", context="MediaGeneratorAgent")
            return ""

    def _check_ffmpeg(self) -> bool:
        """Check if ffmpeg is installed."""
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
            subprocess.run(["ffprobe", "-version"], capture_output=True, check=True)
            return True
        except Exception:
            self.log.error("FFmpeg or FFprobe not found! Media assembly will fail.", context="MediaGeneratorAgent")
            return False
