"""
Viral Clip Analyzer - LLM-powered clip selection
Uses AI to identify the most engaging moments based on topic and virality criteria.
"""
import json
import re
import requests
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from rich.console import Console
from rich.table import Table

# Ollama - always available (local, no API key needed)
OLLAMA_URL = "http://localhost:11434"

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

try:
    import google.generativeai as genai
    HAS_GEMINI = True  
except ImportError:
    HAS_GEMINI = False

from transcriber import Transcript

console = Console()


@dataclass
class ClipCandidate:
    """A potential viral clip identified by the AI"""
    start_time: float
    end_time: float
    title: str
    hook: str  # The attention-grabbing opening
    summary: str
    virality_score: float  # 0-100
    reasoning: str
    topic_relevance: float  # 0-100
    

@dataclass
class AnalysisResult:
    """Results from the viral analysis"""
    clips: List[ClipCandidate]
    topic: str
    total_segments_analyzed: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "clips": [asdict(c) for c in self.clips],
            "topic": self.topic,
            "total_segments_analyzed": self.total_segments_analyzed
        }
    
    def save(self, path: Path):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2)
    
    @classmethod
    def load(cls, path: Path) -> 'AnalysisResult':
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        clips = [ClipCandidate(**c) for c in data["clips"]]
        return cls(
            clips=clips,
            topic=data["topic"],
            total_segments_analyzed=data["total_segments_analyzed"]
        )


VIRAL_ANALYSIS_PROMPT = """You are an expert viral content strategist who specializes in identifying clip-worthy moments from podcasts and interviews for TikTok, Instagram Reels, and YouTube Shorts.

Your task is to analyze this podcast transcript and identify the TOP {num_clips} most viral-worthy segments about the topic: "{topic}"

## WHAT MAKES A CLIP GO VIRAL:

1. **HOOK (0-3 seconds)**: Must grab attention IMMEDIATELY
   - Shocking statement or statistic
   - Provocative question
   - Bold claim or hot take
   - "Wait, what?" moment

2. **EMOTIONAL RESONANCE**: Content that triggers strong emotions
   - Inspiration / Motivation
   - Outrage / Controversy  
   - Humor / Relatability
   - Fear / Urgency
   - Awe / Mind-blown moments

3. **VALUE DELIVERY**: Gives the viewer something tangible
   - Actionable advice
   - Little-known information
   - Perspective shift
   - "I need to share this" moments

4. **COMPLETE THOUGHT**: The clip must:
   - Start at a natural beginning (not mid-sentence)
   - End at a natural conclusion
   - Be self-contained (understandable without context)
   - Be between 15-90 seconds ideally

## TRANSCRIPT TO ANALYZE:

{transcript_text}

## YOUR TASK:

Find the {num_clips} best clips about "{topic}". For EACH clip, provide:

1. **start_time**: Exact start time in seconds (use the timestamps provided)
2. **end_time**: Exact end time in seconds  
3. **title**: A catchy, scroll-stopping title (like a YouTube thumbnail text)
4. **hook**: The exact opening line that grabs attention
5. **summary**: What makes this clip valuable in 1-2 sentences
6. **virality_score**: 0-100 score based on viral potential
7. **topic_relevance**: 0-100 score for how relevant it is to "{topic}"
8. **reasoning**: Why this will perform well on social media

## OUTPUT FORMAT (JSON ARRAY):

```json
[
  {{
    "start_time": 125.5,
    "end_time": 178.2,
    "title": "This One Thing Changed Everything",
    "hook": "Here's what nobody tells you about...",
    "summary": "Speaker reveals surprising insight about...",
    "virality_score": 85,
    "topic_relevance": 92,
    "reasoning": "Strong hook with unexpected twist, delivers clear value..."
  }}
]
```

IMPORTANT: 
- Only return the JSON array, no other text
- Ensure timestamps are accurate based on the transcript
- Prioritize clips that start with a HOOK
- Each clip should be self-contained
"""


def chunk_transcript_for_analysis(
    transcript: Transcript, 
    chunk_duration: float = 300.0  # 5 minutes per chunk
) -> List[str]:
    """
    Break transcript into analyzable chunks with timestamps.
    """
    chunks = []
    current_chunk = []
    chunk_start = 0.0
    
    for seg in transcript.segments:
        current_chunk.append(f"[{seg.start:.1f}s] {seg.text}")
        
        # Check if we've exceeded chunk duration
        if seg.end - chunk_start >= chunk_duration:
            chunks.append("\n".join(current_chunk))
            current_chunk = []
            chunk_start = seg.end
    
    # Don't forget the last chunk
    if current_chunk:
        chunks.append("\n".join(current_chunk))
    
    return chunks


def analyze_with_claude(
    transcript_text: str,
    topic: str,
    num_clips: int = 5,
    api_key: Optional[str] = None
) -> List[ClipCandidate]:
    """Use Claude to analyze transcript and find viral clips"""
    if not HAS_ANTHROPIC:
        raise ImportError("anthropic package not installed. Run: pip install anthropic")
    
    client = anthropic.Anthropic(api_key=api_key)
    
    prompt = VIRAL_ANALYSIS_PROMPT.format(
        transcript_text=transcript_text,
        topic=topic,
        num_clips=num_clips
    )
    
    console.print("[cyan]Analyzing with Claude...[/cyan]")
    
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    
    response_text = message.content[0].text
    return parse_clip_response(response_text)


def analyze_with_gemini(
    transcript_text: str,
    topic: str,
    num_clips: int = 5,
    api_key: Optional[str] = None
) -> List[ClipCandidate]:
    """Use Gemini to analyze transcript and find viral clips"""
    if not HAS_GEMINI:
        raise ImportError("google-generativeai package not installed")
    
    if api_key:
        genai.configure(api_key=api_key)
    
    model = genai.GenerativeModel('gemini-pro')
    
    prompt = VIRAL_ANALYSIS_PROMPT.format(
        transcript_text=transcript_text,
        topic=topic,
        num_clips=num_clips
    )
    
    console.print("[cyan]Analyzing with Gemini...[/cyan]")
    
    response = model.generate_content(prompt)
    return parse_clip_response(response.text)


def analyze_with_ollama(
    transcript_text: str,
    topic: str,
    num_clips: int = 5,
    model: str = "llama3.1:8b"
) -> List[ClipCandidate]:
    """
    Use Ollama for 100% free local LLM analysis.
    Supports: llama3.1:8b, gemma2:9b, mistral:7b, etc.
    """
    # Check if Ollama is running
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        r.raise_for_status()
    except requests.exceptions.RequestException:
        raise ConnectionError(
            "Ollama not running! Start with: ollama serve\n"
            f"Then pull a model: ollama pull {model}"
        )
    
    prompt = VIRAL_ANALYSIS_PROMPT.format(
        transcript_text=transcript_text[:15000],  # Limit for context window
        topic=topic,
        num_clips=num_clips
    )
    
    console.print(f"[cyan]Analyzing with Ollama ({model})...[/cyan]")
    console.print("[dim]This runs locally - no API costs![/dim]")
    
    response = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "num_predict": 4096
            }
        },
        timeout=300  # 5 min timeout for long transcripts
    )
    response.raise_for_status()
    
    result = response.json()
    return parse_clip_response(result["response"])


def parse_clip_response(response_text: str) -> List[ClipCandidate]:
    """Parse the JSON response from LLM into ClipCandidate objects"""
    # Extract JSON from response (handle markdown code blocks)
    json_match = re.search(r'\[[\s\S]*\]', response_text)
    if not json_match:
        console.print(f"[red]Failed to parse response: {response_text[:500]}[/red]")
        raise ValueError("Could not find JSON array in response")
    
    try:
        clips_data = json.loads(json_match.group())
    except json.JSONDecodeError as e:
        console.print(f"[red]JSON parse error: {e}[/red]")
        raise
    
    clips = []
    for clip in clips_data:
        clips.append(ClipCandidate(
            start_time=float(clip["start_time"]),
            end_time=float(clip["end_time"]),
            title=clip["title"],
            hook=clip["hook"],
            summary=clip["summary"],
            virality_score=float(clip["virality_score"]),
            topic_relevance=float(clip.get("topic_relevance", 50)),
            reasoning=clip["reasoning"]
        ))
    
    return clips


def analyze_transcript(
    transcript: Transcript,
    topic: str,
    num_clips: int = 5,
    llm_provider: str = "claude",  # or "gemini"
    api_key: Optional[str] = None
) -> AnalysisResult:
    """
    Main analysis function - finds viral clips in a transcript.
    
    Args:
        transcript: The Transcript object to analyze
        topic: Topic to focus on for clip selection
        num_clips: Number of clips to find
        llm_provider: Which LLM to use ("claude" or "gemini")
        api_key: API key for the LLM service
    
    Returns:
        AnalysisResult with ranked clip candidates
    """
    console.print(f"\n[bold cyan]🎯 Analyzing transcript for viral clips about: '{topic}'[/bold cyan]")
    
    # Build full transcript text with timestamps
    transcript_text = "\n".join([
        f"[{seg.start:.1f}s - {seg.end:.1f}s] {seg.text}"
        for seg in transcript.segments
    ])
    
    # For very long transcripts, we may need to chunk
    # For now, let's try full text (most models handle ~100k tokens now)
    
    if llm_provider == "claude":
        clips = analyze_with_claude(transcript_text, topic, num_clips, api_key)
    elif llm_provider == "gemini":
        clips = analyze_with_gemini(transcript_text, topic, num_clips, api_key)
    elif llm_provider == "ollama":
        clips = analyze_with_ollama(transcript_text, topic, num_clips)
    else:
        raise ValueError(f"Unknown LLM provider: {llm_provider}. Use: ollama, claude, or gemini")
    
    # Sort by virality score
    clips.sort(key=lambda c: c.virality_score, reverse=True)
    
    result = AnalysisResult(
        clips=clips,
        topic=topic,
        total_segments_analyzed=len(transcript.segments)
    )
    
    # Display results
    display_analysis_results(result)
    
    return result


def display_analysis_results(result: AnalysisResult):
    """Pretty print the analysis results"""
    console.print(f"\n[bold green]✓ Found {len(result.clips)} viral clip candidates![/bold green]\n")
    
    table = Table(title=f"🔥 Viral Clips for '{result.topic}'")
    table.add_column("#", style="cyan", width=3)
    table.add_column("Time", style="magenta", width=12)
    table.add_column("Title", style="green", width=30)
    table.add_column("Score", style="yellow", width=8)
    table.add_column("Hook", style="white", width=40)
    
    for i, clip in enumerate(result.clips, 1):
        duration = clip.end_time - clip.start_time
        time_str = f"{clip.start_time:.0f}s ({duration:.0f}s)"
        score_str = f"🔥 {clip.virality_score:.0f}"
        
        table.add_row(
            str(i),
            time_str,
            clip.title[:28] + "..." if len(clip.title) > 30 else clip.title,
            score_str,
            clip.hook[:38] + "..." if len(clip.hook) > 40 else clip.hook
        )
    
    console.print(table)


if __name__ == "__main__":
    # Test
    import sys
    if len(sys.argv) > 2:
        transcript_path = Path(sys.argv[1])
        topic = sys.argv[2]
        
        transcript = Transcript.load(transcript_path)
        result = analyze_transcript(transcript, topic)
        result.save(Path("./temp/analysis_result.json"))
