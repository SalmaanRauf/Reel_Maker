"""
B-Roll Engine - Auto-fetch relevant stock footage from Pexels
Uses free Pexels API to find and cache B-roll clips based on transcript keywords.
"""
import os
import re
import requests
from pathlib import Path
from typing import List, Optional, Dict
from dataclasses import dataclass
from rich.console import Console

console = Console()

# Free Pexels API - get key at https://www.pexels.com/api/
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
PEXELS_API_URL = "https://api.pexels.com/videos/search"

# Cache directory for downloaded B-roll
CACHE_DIR = Path(__file__).parent / "assets" / "broll_cache"


@dataclass
class BRollClip:
    """A B-roll video clip"""
    id: int
    query: str
    duration: float
    width: int
    height: int
    video_url: str
    local_path: Optional[Path] = None


# Keywords to B-roll search mappings
KEYWORD_MAPPINGS = {
    # Money/Business
    "money": "money cash dollars",
    "million": "luxury success",
    "dollar": "money currency",
    "business": "office business meeting",
    "invest": "stock market trading",
    "profit": "money growth chart",
    
    # Health
    "health": "healthy lifestyle",
    "exercise": "gym workout",
    "diet": "healthy food nutrition",
    "sleep": "sleeping peaceful",
    "stress": "meditation calm",
    "doctor": "medical healthcare",
    
    # Technology
    "tech": "technology innovation",
    "ai": "artificial intelligence robot",
    "computer": "computer coding",
    "phone": "smartphone mobile",
    
    # Emotions
    "success": "celebration victory",
    "failure": "sad disappointed",
    "happy": "joy happiness celebration",
    "angry": "frustration stress",
    
    # General
    "time": "clock time passing",
    "nature": "nature landscape beautiful",
    "city": "city urban skyline",
    "people": "crowd people walking",
}


def extract_keywords(text: str, min_length: int = 4) -> List[str]:
    """Extract potential B-roll keywords from text"""
    # Clean and split
    words = re.findall(r'\b[a-zA-Z]+\b', text.lower())
    
    # Filter short words and common ones
    stopwords = {'this', 'that', 'with', 'have', 'from', 'they', 'been', 'were', 'will'}
    keywords = [w for w in words if len(w) >= min_length and w not in stopwords]
    
    # Match against our mappings
    matched = []
    for word in keywords:
        if word in KEYWORD_MAPPINGS:
            matched.append(word)
    
    return list(set(matched))[:3]  # Top 3 unique keywords


def search_pexels_videos(
    query: str, 
    per_page: int = 5,
    orientation: str = "portrait"
) -> List[Dict]:
    """
    Search Pexels for videos matching query.
    
    Args:
        query: Search query
        per_page: Number of results
        orientation: portrait, landscape, or square
        
    Returns:
        List of video data dicts
    """
    if not PEXELS_API_KEY:
        console.print("[yellow]No PEXELS_API_KEY set - B-roll disabled[/yellow]")
        return []
    
    headers = {"Authorization": PEXELS_API_KEY}
    params = {
        "query": query,
        "per_page": per_page,
        "orientation": orientation,
        "size": "medium"
    }
    
    try:
        response = requests.get(PEXELS_API_URL, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("videos", [])
    except requests.RequestException as e:
        console.print(f"[red]Pexels API error: {e}[/red]")
        return []


def download_video(url: str, output_path: Path) -> bool:
    """Download video from URL to local path"""
    try:
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        return True
    except requests.RequestException as e:
        console.print(f"[red]Download failed: {e}[/red]")
        return False


def get_best_video_file(video_data: Dict, preferred_quality: str = "hd") -> Optional[str]:
    """Get the best video file URL from Pexels response"""
    video_files = video_data.get("video_files", [])
    
    # Try to find HD quality first
    for vf in video_files:
        if vf.get("quality") == preferred_quality:
            return vf.get("link")
    
    # Fall back to any available
    if video_files:
        return video_files[0].get("link")
    
    return None


class BRollEngine:
    """
    Engine for fetching and managing B-roll clips.
    
    Usage:
        engine = BRollEngine()
        clip = engine.get_broll_for_text("The secret to making money fast")
        if clip:
            # Use clip.local_path in your video
    """
    
    def __init__(self, cache_dir: Path = CACHE_DIR):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def get_cached_path(self, video_id: int) -> Path:
        """Get cache path for a video ID"""
        return self.cache_dir / f"{video_id}.mp4"
    
    def is_cached(self, video_id: int) -> bool:
        """Check if video is already cached"""
        return self.get_cached_path(video_id).exists()
    
    def fetch_broll(self, query: str) -> Optional[BRollClip]:
        """
        Fetch a B-roll clip for a search query.
        Downloads and caches the video.
        """
        # Search Pexels
        videos = search_pexels_videos(query, per_page=3)
        if not videos:
            return None
        
        # Try each video until we get one
        for video_data in videos:
            video_id = video_data.get("id")
            cache_path = self.get_cached_path(video_id)
            
            # Check cache first
            if cache_path.exists():
                return BRollClip(
                    id=video_id,
                    query=query,
                    duration=video_data.get("duration", 0),
                    width=video_data.get("width", 0),
                    height=video_data.get("height", 0),
                    video_url="",
                    local_path=cache_path
                )
            
            # Download
            video_url = get_best_video_file(video_data)
            if not video_url:
                continue
            
            console.print(f"[cyan]Downloading B-roll: {query}...[/cyan]")
            if download_video(video_url, cache_path):
                return BRollClip(
                    id=video_id,
                    query=query,
                    duration=video_data.get("duration", 0),
                    width=video_data.get("width", 0),
                    height=video_data.get("height", 0),
                    video_url=video_url,
                    local_path=cache_path
                )
        
        return None
    
    def get_broll_for_text(self, text: str) -> Optional[BRollClip]:
        """
        Get appropriate B-roll for a transcript segment.
        Extracts keywords and finds matching footage.
        """
        keywords = extract_keywords(text)
        
        for keyword in keywords:
            # Get the search query from our mappings
            search_query = KEYWORD_MAPPINGS.get(keyword, keyword)
            clip = self.fetch_broll(search_query)
            if clip:
                return clip
        
        return None
    
    def clear_cache(self):
        """Clear all cached B-roll videos"""
        import shutil
        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            console.print("[green]B-roll cache cleared[/green]")


if __name__ == "__main__":
    # Test
    engine = BRollEngine()
    
    test_text = "The secret to making money fast is consistency"
    print(f"Testing with: {test_text}")
    
    keywords = extract_keywords(test_text)
    print(f"Extracted keywords: {keywords}")
    
    if PEXELS_API_KEY:
        clip = engine.get_broll_for_text(test_text)
        if clip:
            print(f"Found B-roll: {clip.local_path}")
        else:
            print("No B-roll found")
    else:
        print("Set PEXELS_API_KEY to test downloading")
